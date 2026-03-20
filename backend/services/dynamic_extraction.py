"""
backend/services/dynamic_extraction.py — Dynamic label/value discovery.

Extracts *all* label → value pairs present in any PDF or image file without
requiring a fixed schema.  Supports:

- Text-based PDFs  : PyMuPDF ``get_text("words")`` for word-level bounding boxes.
- Image-based PDFs : PyMuPDF page render → EasyOCR with bounding boxes.
- PNG / JPG images : OpenCV load → EasyOCR with bounding boxes.

Public API
----------
extract_dynamic_fields(file_path, page_index=0, dpi=150) -> list[dict]
    Return a list of field dicts:
        label       — str  (e.g. "Present Address")
        value       — str  (e.g. "Anoop layout")
        page_number — int  (1-based)
        confidence  — float 0.0–1.0
        bbox        — dict {x, y, width, height} in PDF points or pixels

Label-detection heuristics (v2)
--------------------------------
A word/span is treated as a label candidate if:
  1. It ends with ``:`` (colon), OR
  2. It matches a keyword that commonly introduces a value on forms.
     The keyword list covers general form fields (Address, Name, Date, …)
     **and** insurance-specific terms (Occupation, Nominee, Proposer,
     Assured, Maturity, Mode, Plan, Term, Beneficiary, Rider, …).

Pairing strategy (v2 — line-based)
-------------------------------------
Word boxes are first grouped into physical text lines using
:func:`_group_into_lines` (Y-centre proximity within one font-height).

Each line is then scanned left-to-right.  Runs of consecutive label-keyword
words (optionally linked by connector words like "of", "to") form a single
label phrase.  All non-label words that immediately follow on the **same
line** become the value.  When no same-line value is found:

  * Strategy A — search the next few lines for a pure-value line (no
    labels).  Handles stacked "label then blank/fill-in line then value"
    layouts.
  * Strategy B — search preceding lines for a pure-value line.  Handles
    table-style forms where the value appears *above* its label.

Multiple label+value pairs on the same physical line are supported, which
covers two-column form layouts (e.g. ``Name: Alice   Age: 30``).

Troubleshooting — PDF files disguised as images
-----------------------------------------------
If ``file_path`` ends with ``.png`` / ``.jpg`` but actually starts with the
``%PDF`` magic bytes, a ``ValueError`` is raised with a clear message.
Use PyMuPDF / ``extract_dynamic_fields`` with a proper ``.pdf`` extension
for PDF content.

Per-document schema helpers
---------------------------
create_schema_from_pairs(pairs) -> list[str]
    Build an ordered, deduplicated list of label strings from discovered pairs.

map_pairs_to_schema(discovered_pairs, schema_labels, fuzzy_threshold=0.80) -> list[dict]
    Map discovered pairs to an existing schema using:
      1. Exact match (case-insensitive)
      2. Normalised match (strip colon / whitespace)
      3. Fuzzy similarity ≥ fuzzy_threshold (difflib.SequenceMatcher)
    Returns one dict per schema label (in schema order), with matched values
    or empty strings for unmatched labels.
"""

from __future__ import annotations

import io
import logging
import os
import re
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Magic byte signatures
# ---------------------------------------------------------------------------

_PDF_SIG = b"%PDF"
_PNG_SIG = b"\x89PNG"

# ---------------------------------------------------------------------------
# Label keyword pattern — matches even without trailing colon
# ---------------------------------------------------------------------------

_LABEL_KW_RE = re.compile(
    r"^(?:"
    r"Name|Address|Date|Amount|No|Number|ID|Email|Phone|Pin|Code|Type|"
    r"Net\s+Payable|Net|Total|Payable|Loan|Value|Bank|IFSC|"
    r"Account|Acct|Holder|Contact|Signature|Stamp|Witness|Reason|"
    r"Surrender|Premium|Policy|Sum|Insured|Present|Permanent|City|"
    r"State|Zip|District|Country|Nationality|DOB|Gender|Age|Salary|"
    r"Designation|Department|Employee|Customer|Invoice|Receipt|"
    r"Reference|Ref|Serial|Sr|Branch|Mobile|Fax|Website|Subject|"
    # Insurance / structured-form additions
    r"Occupation|Income|Mode|Nominee|Relation|Plan|Term|Cover|Risk|"
    r"Commencement|Anniversary|Proposer|Assured|Maturity|Frequency|"
    r"Payment|First|Last|Middle|Father|Mother|Spouse|Applicant|"
    r"Beneficiary|Rider|Benefit|Death|Survival|Pension|Fund|"
    r"Annuity|Proof|Declaration|Health|Medical|Height|Weight|"
    r"Habits|Residence|Birth|Marital|Status|Annual|Monthly|"
    r"Gross|Basic|Special|Table|Duration|Period|Currency|Rate|"
    r"Percentage|Pct|Tax|GST|PAN|Aadhaar|Voter|Passport|Driving|"
    r"License|Registration|Profession|Business|Company|Organization"
    r")$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Spatial thresholds (in image pixels; scale-independent relative to text height)
# ---------------------------------------------------------------------------

_LINE_THRESH_FACTOR = 1.2   # label box height × factor = vertical tolerance for "same line"
_BELOW_THRESH_FACTOR = 5.0  # label box height × factor = max vertical gap for "below" match
_RIGHT_MIN_GAP = 2          # minimum horizontal gap (px) to be considered "to the right"
_MULTI_WORD_LABEL_MAX_GAP = 150  # max horizontal gap (px) between consecutive label words


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_label_candidate(word: str) -> bool:
    """Return True if *word* looks like a form-field label."""
    w = word.strip().rstrip(":")
    if not w:
        return False
    if word.strip().endswith(":"):
        return True
    return bool(_LABEL_KW_RE.match(w))


def _box_center_y(box: dict) -> float:
    return box["y"] + box["height"] / 2.0


def _box_center_x(box: dict) -> float:
    return box["x"] + box["width"] / 2.0


def _merge_label_words(words: list[dict]) -> list[dict]:
    """Merge consecutive label-candidate words into multi-word labels.

    Words are merged when they share the same line AND have a small horizontal
    gap between them (≤ _MULTI_WORD_LABEL_MAX_GAP).  The merged word keeps the
    combined bounding box and the last word's trailing colon (if any).

    The returned list may contain both single-word and merged-multi-word items.
    Each item is a dict with: text, x, y, width, height, confidence.
    """
    if not words:
        return []

    merged: list[dict] = []
    current: Optional[dict] = None

    for w in words:
        if current is None:
            current = dict(w)
            continue

        # Check vertical alignment (same line)
        line_thresh = max(current["height"], w["height"]) * _LINE_THRESH_FACTOR
        cy_current = _box_center_y(current)
        cy_w = _box_center_y(w)
        same_line = abs(cy_current - cy_w) <= line_thresh

        # Check horizontal gap between boxes
        gap = w["x"] - (current["x"] + current["width"])
        close_enough = gap <= _MULTI_WORD_LABEL_MAX_GAP and gap >= -10

        if same_line and close_enough and _is_label_candidate(w["text"]):
            # Extend current with this word
            right = w["x"] + w["width"]
            top = min(current["y"], w["y"])
            bottom = max(current["y"] + current["height"], w["y"] + w["height"])
            current["text"] = current["text"].rstrip(":") + " " + w["text"]
            current["x"] = min(current["x"], w["x"])
            current["y"] = top
            current["width"] = right - current["x"]
            current["height"] = bottom - top
            current["confidence"] = min(current["confidence"], w["confidence"])
        else:
            merged.append(current)
            current = dict(w)

    if current is not None:
        merged.append(current)

    return merged


def _merge_adjacent_value_tokens(
    seed_box: dict,
    seed_idx: int,
    all_boxes: list[dict],
    used_idxs: set[int],
    lb_h: float,
) -> tuple[str, list[dict], set[int]]:
    """Collect and merge value tokens adjacent to *seed_box* on the same line.

    Starting from *seed_box*, scans *all_boxes* for additional tokens on the
    same horizontal line and merges them into a single value string when the
    gap between tokens is small enough.

    Parameters
    ----------
    seed_box:
        The initial value box (already selected as best candidate).
    seed_idx:
        Index of *seed_box* within *all_boxes*.
    all_boxes:
        Full list of word boxes (same page).
    used_idxs:
        Set of already-consumed box indices (updated in place on return).
    lb_h:
        Label box height, used to compute the gap tolerance.

    Returns
    -------
    (value_text, value_boxes_used, updated_used_idxs)
    """
    vb_cy = _box_center_y(seed_box)
    vb_line_thresh = seed_box["height"] * _LINE_THRESH_FACTOR
    value_parts: list[str] = [seed_box["text"]]
    value_boxes_used: list[dict] = [seed_box]
    used_idxs.add(seed_idx)
    prev_right_edge = seed_box["x"] + seed_box["width"]

    for j, wb in enumerate(all_boxes):
        if j == seed_idx or j in used_idxs:
            continue
        wb_cy = _box_center_y(wb)
        if abs(wb_cy - vb_cy) > vb_line_thresh:
            continue
        if wb["x"] < prev_right_edge - 4:
            continue
        gap = wb["x"] - prev_right_edge
        if gap > lb_h * 4:
            break
        if _is_label_candidate(wb["text"]):
            break
        value_parts.append(wb["text"])
        value_boxes_used.append(wb)
        prev_right_edge = wb["x"] + wb["width"]
        used_idxs.add(j)

    return " ".join(value_parts).strip(), value_boxes_used, used_idxs


def _make_bbox(boxes_used: list[dict]) -> dict:
    """Return a bbox dict that spans all boxes in *boxes_used*."""
    return {
        "x":      min(b["x"] for b in boxes_used),
        "y":      min(b["y"] for b in boxes_used),
        "width":  max(b["x"] + b["width"]  for b in boxes_used) - min(b["x"] for b in boxes_used),
        "height": max(b["y"] + b["height"] for b in boxes_used) - min(b["y"] for b in boxes_used),
    }


def _group_into_lines(boxes: list[dict]) -> list[list[dict]]:
    """Group word boxes into lines based on Y-centre proximity.

    Uses the median box height as the grouping tolerance so the function
    adapts automatically to the font size of the page being analysed.

    Parameters
    ----------
    boxes:
        Flat list of word-box dicts (text, x, y, width, height, confidence).

    Returns
    -------
    List of lines.  Each line is a list of boxes sorted left-to-right by
    their x coordinate.  Lines are ordered top-to-bottom.
    """
    if not boxes:
        return []

    sorted_boxes = sorted(boxes, key=lambda b: (b["y"], b["x"]))

    heights = sorted(b["height"] for b in sorted_boxes)
    n = len(heights)
    if n == 0:
        median_h = 12.0
    elif n % 2 == 0:
        median_h = (heights[n // 2 - 1] + heights[n // 2]) / 2.0
    else:
        median_h = heights[n // 2]
    tol = max(median_h * 1.0, 4.0)

    lines: list[list[dict]] = []
    current_line: list[dict] = [sorted_boxes[0]]
    line_cy = _box_center_y(sorted_boxes[0])

    for box in sorted_boxes[1:]:
        cy = _box_center_y(box)
        if abs(cy - line_cy) <= tol:
            current_line.append(box)
        else:
            lines.append(sorted(current_line, key=lambda b: b["x"]))
            current_line = [box]
            line_cy = cy

    if current_line:
        lines.append(sorted(current_line, key=lambda b: b["x"]))

    return lines


def _pair_labels_values(boxes: list[dict]) -> list[dict]:
    """Pair label boxes with their nearest value boxes.

    Uses :func:`_group_into_lines` to group word boxes into physical text
    lines first, then processes each line to find all label→value pairs.

    Supports:
    - Multiple label+value pairs on the same line (multi-column forms).
    - Label on one line with value on the next (stacked blank-line forms).
    - Label appearing *below* its value (some table-style insurance forms).
    - Connector words (``of``, ``to``, …) inside multi-word label phrases.

    Parameters
    ----------
    boxes:
        List of dicts with keys: text, x, y, width, height, confidence.
        All boxes should be from the same page/image.

    Returns
    -------
    list of dicts: {label, value, bbox, label_bbox, confidence}
        bbox       — value bounding box (x, y, width, height).  ``None`` when
                     no value is found.
        label_bbox — label bounding box (x, y, width, height).
    """
    if not boxes:
        return []

    lines = _group_into_lines(boxes)
    pairs: list[dict] = []
    line_consumed = [False] * len(lines)

    # Small function words that may appear *between* two label-keyword words
    # (e.g. "Date of Birth", "Mode of Payment") and should be treated as
    # part of the label phrase rather than as a value.
    _LABEL_CONNECTORS = {"of", "to", "the", "and", "or", "for", "in", "at", "by"}

    for li, line in enumerate(lines):
        if line_consumed[li]:
            continue

        # Walk left-to-right along the line.  Each run of label-candidate
        # words (possibly linked by connector words) forms one label.  The
        # non-label words that immediately follow it form its value.
        i = 0
        while i < len(line):
            # Skip non-label words until we find a label-keyword
            if not _is_label_candidate(line[i]["text"]):
                i += 1
                continue

            # ── Build label phrase ────────────────────────────────────────
            label_boxes: list[dict] = [line[i]]
            i += 1

            while i < len(line):
                w_text = line[i]["text"].strip().lower()
                if _is_label_candidate(line[i]["text"]):
                    # Another keyword: extend the label
                    label_boxes.append(line[i])
                    i += 1
                elif (
                    w_text in _LABEL_CONNECTORS
                    and i + 1 < len(line)
                    and _is_label_candidate(line[i + 1]["text"])
                ):
                    # Connector word followed by a keyword → include both
                    label_boxes.append(line[i])
                    label_boxes.append(line[i + 1])
                    i += 2
                else:
                    break

            label_text = " ".join(b["text"].rstrip(":").strip() for b in label_boxes)
            label_text = " ".join(label_text.split())   # normalise whitespace
            if not label_text:
                continue

            label_bbox = _make_bbox(label_boxes)
            label_conf = min(b.get("confidence", 1.0) for b in label_boxes)

            # ── Collect value words (same line, until next label) ─────────
            value_boxes: list[dict] = []
            while i < len(line):
                if _is_label_candidate(line[i]["text"]):
                    break   # next label starts; stop collecting value words
                value_boxes.append(line[i])
                i += 1

            if value_boxes:
                value_text = " ".join(b["text"] for b in value_boxes).strip()
                pairs.append({
                    "label":      label_text,
                    "value":      value_text,
                    "bbox":       _make_bbox(value_boxes),
                    "label_bbox": label_bbox,
                    "confidence": label_conf,
                })
                continue

            # ── No value on the same line ─────────────────────────────────
            # Strategy A: look at subsequent lines for a pure-value line.
            value_found = False
            for lj in range(li + 1, min(li + 4, len(lines))):
                if line_consumed[lj]:
                    continue
                next_line = lines[lj]
                has_labels = any(_is_label_candidate(b["text"]) for b in next_line)
                if not has_labels:
                    value_text = " ".join(b["text"] for b in next_line).strip()
                    if value_text:
                        pairs.append({
                            "label":      label_text,
                            "value":      value_text,
                            "bbox":       _make_bbox(next_line),
                            "label_bbox": label_bbox,
                            "confidence": label_conf,
                        })
                        line_consumed[lj] = True
                        value_found = True
                        break
                else:
                    break   # next line has its own labels; stop

            if value_found:
                continue

            # Strategy B: look at preceding lines (label appears *below* value).
            for lj in range(li - 1, max(li - 4, -1), -1):
                if line_consumed[lj]:
                    continue
                prev_line = lines[lj]
                has_labels = any(_is_label_candidate(b["text"]) for b in prev_line)
                if not has_labels:
                    value_text = " ".join(b["text"] for b in prev_line).strip()
                    if value_text:
                        pairs.append({
                            "label":      label_text,
                            "value":      value_text,
                            "bbox":       _make_bbox(prev_line),
                            "label_bbox": label_bbox,
                            "confidence": label_conf,
                        })
                        line_consumed[lj] = True
                        value_found = True
                        break
                else:
                    break   # prev line has its own labels; stop

            if not value_found:
                # Emit a label-only entry so callers know the field exists
                pairs.append({
                    "label":      label_text,
                    "value":      "",
                    "bbox":       None,
                    "label_bbox": label_bbox,
                    "confidence": label_conf,
                })

    return pairs


# ---------------------------------------------------------------------------
# OCR bounding-box extraction
# ---------------------------------------------------------------------------


def _ocr_boxes(img_array) -> list[dict]:
    """Run EasyOCR on a numpy image array and return word boxes.

    Returns list of dicts: {text, x, y, width, height, confidence}.
    """
    try:
        import easyocr  # type: ignore[import]
    except ImportError:
        logger.warning(
            "easyocr is not installed — dynamic extraction unavailable. "
            "Install with: pip install easyocr"
        )
        return []

    # Cached reader (module-level singleton shared with ocr_utils)
    reader = _get_ocr_reader()
    if reader is None:
        return []

    try:
        results = reader.readtext(img_array, detail=1, paragraph=False)
    except Exception as exc:
        logger.warning("EasyOCR readtext failed: %s", exc)
        return []

    boxes: list[dict] = []
    for result in results:
        bbox_pts, text, conf = result
        # bbox_pts: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
        xs = [p[0] for p in bbox_pts]
        ys = [p[1] for p in bbox_pts]
        x = min(xs)
        y = min(ys)
        w = max(xs) - x
        h = max(ys) - y
        text_clean = str(text).strip()
        if text_clean:
            boxes.append({
                "text": text_clean,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "confidence": float(conf),
            })

    # Sort top-to-bottom, left-to-right
    boxes.sort(key=lambda b: (b["y"], b["x"]))
    return boxes


# ---------------------------------------------------------------------------
# PyMuPDF word-box extraction (text PDFs)
# ---------------------------------------------------------------------------


def _pymupdf_word_boxes(pdf_path: str, page_index: int = 0) -> list[dict]:
    """Extract word-level bounding boxes from a text-based PDF page.

    Returns list of dicts: {text, x, y, width, height, confidence}.
    """
    try:
        import fitz  # PyMuPDF  # type: ignore[import]
    except ImportError:
        logger.warning("PyMuPDF (fitz) is not installed — cannot read PDF words.")
        return []

    boxes: list[dict] = []
    try:
        doc = fitz.open(pdf_path)
        try:
            if page_index >= len(doc):
                return []
            page = doc[page_index]
            # get_text("words") returns (x0, y0, x1, y1, word, block, line, word_no)
            words = page.get_text("words")
            for w in words:
                x0, y0, x1, y1, word = w[0], w[1], w[2], w[3], w[4]
                word_clean = str(word).strip()
                if word_clean:
                    boxes.append({
                        "text": word_clean,
                        "x": x0,
                        "y": y0,
                        "width": x1 - x0,
                        "height": y1 - y0,
                        "confidence": 1.0,
                    })
        finally:
            doc.close()
    except Exception as exc:
        logger.warning("_pymupdf_word_boxes failed: %s", exc)

    boxes.sort(key=lambda b: (b["y"], b["x"]))
    return boxes


def _pdf_has_text(pdf_path: str, page_index: int = 0) -> bool:
    """Return True if the PDF page contains extractable text."""
    try:
        import fitz  # type: ignore[import]
        doc = fitz.open(pdf_path)
        try:
            if page_index >= len(doc):
                return False
            text = doc[page_index].get_text().strip()
            return bool(text)
        finally:
            doc.close()
    except Exception:
        return False


def _render_pdf_page(pdf_path: str, page_index: int = 0, dpi: int = 150):
    """Render a PDF page to a numpy RGB array."""
    try:
        import fitz  # type: ignore[import]
        import numpy as np  # type: ignore[import]
        from PIL import Image  # type: ignore[import]

        doc = fitz.open(pdf_path)
        try:
            if page_index >= len(doc):
                return None
            page = doc[page_index]
            scale = dpi / 72.0
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            return np.array(img)
        finally:
            doc.close()
    except ImportError:
        logger.warning("PyMuPDF or PIL not available — cannot render PDF page.")
        return None
    except Exception as exc:
        logger.warning("_render_pdf_page failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# EasyOCR reader singleton
# ---------------------------------------------------------------------------

_reader_singleton = None


def _get_ocr_reader():
    """Return a cached EasyOCR Reader (GPU disabled; English only)."""
    global _reader_singleton
    if _reader_singleton is None:
        try:
            import easyocr  # type: ignore[import]
            logger.info("Initialising EasyOCR reader for dynamic extraction…")
            _reader_singleton = easyocr.Reader(["en"], gpu=False, verbose=False)
            logger.info("EasyOCR reader ready.")
        except ImportError:
            logger.warning("easyocr is not installed.")
        except Exception as exc:
            logger.warning("EasyOCR init failed: %s", exc)
    return _reader_singleton


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def extract_dynamic_fields(
    file_path: str,
    page_index: int = 0,
    dpi: int = 150,
) -> list[dict]:
    """Discover and return all label/value pairs in a PDF or image file.

    Strategy (in order):
    1. If the file is a PDF and the target page has extractable text, use
       PyMuPDF word bounding boxes (fast, high accuracy).
    2. Otherwise render the page (PDF) or load the image (PNG/JPG) and run
       EasyOCR to obtain word-level bounding boxes.
    3. Apply the label/value pairing heuristic.

    Parameters
    ----------
    file_path:
        Path to the source file (PDF, PNG, JPG, …).
    page_index:
        Zero-based page number to process (default: 0 = first page).
    dpi:
        Render resolution for image-based PDFs (default: 150).

    Returns
    -------
    list of dict, each with keys:
        label       — str
        value       — str
        page_number — int (1-based)
        confidence  — float
        bbox        — dict {x, y, width, height}

    Raises
    ------
    FileNotFoundError
        If *file_path* does not exist.
    ValueError
        If an image file is actually a PDF (magic bytes ``%PDF``).
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path!r}")

    # Read magic bytes
    with open(file_path, "rb") as fh:
        header = fh.read(8)

    is_pdf_by_sig = header[:4] == _PDF_SIG
    ext = os.path.splitext(file_path)[1].lower()
    is_pdf_by_ext = ext == ".pdf"

    # Detect PDF disguised as image
    img_exts = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
    if ext in img_exts and is_pdf_by_sig:
        raise ValueError(
            f"{file_path!r} has an image extension ({ext!r}) but its content "
            "starts with the PDF magic bytes ('%PDF').\n"
            "Troubleshooting: verify the file signature in a terminal:\n"
            "  Linux/Mac:  head -c 4 '<file>' | cat\n"
            "  PowerShell: (Get-Content '<file>' -Encoding Byte -TotalCount 4) -join ' '\n"
            "A real PNG file starts with bytes: 137 80 78 71 (hex: 89 50 4E 47).\n"
            "Rename the file to '.pdf' and pass it to this function again, or "
            "export a genuine PNG screenshot with the system Snipping Tool."
        )

    boxes: list[dict] = []

    if is_pdf_by_sig or is_pdf_by_ext:
        # ----------------------------------------------------------------
        # PDF path
        # ----------------------------------------------------------------
        if _pdf_has_text(file_path, page_index):
            logger.debug(
                "dynamic_extraction: text-based PDF — using PyMuPDF word boxes (page %d)",
                page_index,
            )
            boxes = _pymupdf_word_boxes(file_path, page_index)
        else:
            logger.debug(
                "dynamic_extraction: image-based PDF — rendering page %d at %d dpi then OCR",
                page_index, dpi,
            )
            img_array = _render_pdf_page(file_path, page_index, dpi)
            if img_array is not None:
                boxes = _ocr_boxes(img_array)
    else:
        # ----------------------------------------------------------------
        # Image path (PNG, JPG, …)
        # ----------------------------------------------------------------
        try:
            import cv2  # type: ignore[import]
            img_array = cv2.imread(file_path)
            if img_array is None:
                raise ValueError(
                    f"OpenCV could not open {file_path!r}. "
                    "Check the path and file format."
                )
            img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        except ImportError:
            logger.warning("cv2 not available — falling back to PIL for image load.")
            try:
                import numpy as np  # type: ignore[import]
                from PIL import Image  # type: ignore[import]
                img_array = np.array(Image.open(file_path).convert("RGB"))
            except Exception as exc:
                raise RuntimeError(
                    f"Cannot load image {file_path!r}: {exc}. "
                    "Install opencv-python: pip install opencv-python"
                ) from exc

        boxes = _ocr_boxes(img_array)

    if not boxes:
        logger.info("dynamic_extraction: no word boxes found for %r page %d", file_path, page_index)
        return []

    # Apply label/value pairing heuristic
    pairs = _pair_labels_values(boxes)

    # Attach page_number (1-based)
    for p in pairs:
        p["page_number"] = page_index + 1

    logger.info(
        "dynamic_extraction: found %d pair(s) on page %d of %r",
        len(pairs), page_index + 1, file_path,
    )
    return pairs


# ---------------------------------------------------------------------------
# Per-document schema helpers
# ---------------------------------------------------------------------------

def _normalise_label(label: str) -> str:
    """Strip trailing colon, collapse whitespace, and lowercase."""
    return re.sub(r"[\s:]+", " ", label).strip().lower()


def _label_similarity(a: str, b: str) -> float:
    """Return a character-level similarity ratio between two normalised labels."""
    return SequenceMatcher(None, _normalise_label(a), _normalise_label(b)).ratio()


def create_schema_from_pairs(pairs: list[dict]) -> list[str]:
    """Return an ordered, deduplicated list of label strings from *pairs*.

    The order mirrors the document's top-to-bottom, left-to-right reading
    order as returned by ``extract_dynamic_fields``.

    Args:
        pairs: List of dicts as returned by ``extract_dynamic_fields`` /
               ``_pair_labels_values``.  Each dict must contain a ``"label"``
               key.

    Returns:
        Ordered list of unique label strings (preserving first-seen order).
    """
    seen: set[str] = set()
    schema: list[str] = []
    for pair in pairs:
        label = pair.get("label", "").strip()
        if label and label not in seen:
            seen.add(label)
            schema.append(label)
    return schema


def map_pairs_to_schema(
    discovered_pairs: list[dict],
    schema_labels: list[str],
    fuzzy_threshold: float = 0.80,
) -> list[dict]:
    """Map *discovered_pairs* to an existing *schema_labels* list.

    Each schema label is matched against the discovered pairs using:
      1. Exact match (case-insensitive)
      2. Normalised match (strip colon / whitespace, lowercase)
      3. Fuzzy similarity ≥ *fuzzy_threshold* (difflib.SequenceMatcher)

    Every discovered pair is used at most once (greedy left-to-right).
    Unmatched schema labels get an empty value and zero confidence.

    Args:
        discovered_pairs: List of dicts from ``extract_dynamic_fields``.
        schema_labels:    Ordered list of label strings from the stored schema.
        fuzzy_threshold:  Minimum SequenceMatcher ratio to accept a fuzzy match.

    Returns:
        List of one dict per schema label (in schema order):
            label       — schema label string
            value       — matched value string (or ``""`` if unmatched)
            confidence  — float 0.0–1.0 (0.0 if unmatched)
            bbox        — matched bbox dict (or ``None`` if unmatched)
            page_number — int (1 if unmatched)
            matched     — bool
    """
    used: set[int] = set()
    result: list[dict] = []

    for schema_label in schema_labels:
        schema_norm = _normalise_label(schema_label)
        best_idx: int | None = None
        best_score: float = 0.0

        for i, pair in enumerate(discovered_pairs):
            if i in used:
                continue
            pair_label = pair.get("label", "")

            # 1. Exact case-insensitive match
            if pair_label.lower() == schema_label.lower():
                best_idx = i
                best_score = 1.0
                break

            # 2. Normalised match
            pair_norm = _normalise_label(pair_label)
            if pair_norm == schema_norm:
                best_idx = i
                best_score = 1.0
                break

            # 3. Fuzzy match
            score = _label_similarity(pair_label, schema_label)
            if score >= fuzzy_threshold and score > best_score:
                best_idx = i
                best_score = score

        if best_idx is not None:
            used.add(best_idx)
            pair = discovered_pairs[best_idx]
            result.append({
                "label": schema_label,
                "value": pair.get("value", ""),
                "confidence": pair.get("confidence", 1.0),
                "bbox": pair.get("bbox"),
                "page_number": pair.get("page_number", 1),
                "matched": True,
            })
        else:
            result.append({
                "label": schema_label,
                "value": "",
                "confidence": 0.0,
                "bbox": None,
                "page_number": 1,
                "matched": False,
            })

    return result
