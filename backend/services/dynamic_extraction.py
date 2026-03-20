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

Label-detection heuristics (v1)
--------------------------------
A word/span is treated as a label candidate if:
  1. It ends with ``:`` (colon), OR
  2. It ends with a keyword that commonly introduces a value on forms
     (Address, Name, Date, Amount, No, ID, Email, Phone, Pin, Payable, etc.).

The value for a label is chosen as:
  - The nearest text to the **right** on the same line (within ±``_LINE_THRESH``
    of vertical centre), OR if none,
  - The nearest text **below** within ``_BELOW_THRESH`` pixels.

Multi-word labels are merged by grouping consecutive label candidates that
appear on the same text line before any non-label word.

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
    r"Reference|Ref|Serial|Sr|Branch|Mobile|Fax|Website|Subject"
    r")$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Spatial thresholds (in image pixels; scale-independent relative to text height)
# ---------------------------------------------------------------------------

_LINE_THRESH_FACTOR = 0.6   # label box height × factor = vertical tolerance for "same line"
_BELOW_THRESH_FACTOR = 3.0  # label box height × factor = max vertical gap for "below" match
_RIGHT_MIN_GAP = 2          # minimum horizontal gap (px) to be considered "to the right"
_MULTI_WORD_LABEL_MAX_GAP = 80  # max horizontal gap (px) between consecutive label words
_MIN_OCR_CONF = 0.40        # minimum EasyOCR confidence to include a token


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


def _pair_labels_values(boxes: list[dict]) -> list[dict]:
    """Pair label boxes with their nearest value boxes.

    Parameters
    ----------
    boxes:
        List of dicts with keys: text, x, y, width, height, confidence.
        All boxes should be from the same page/image.

    Returns
    -------
    list of dicts: {label, value, bbox, label_bbox, confidence}
        bbox      — value bounding box (x, y, width, height) for value highlight.
        label_bbox — label bounding box (x, y, width, height) for label highlight.
        For label-only entries (no value found), bbox is None.
    """
    if not boxes:
        return []

    # Split into label candidates and all other (value candidates)
    label_idxs = [i for i, b in enumerate(boxes) if _is_label_candidate(b["text"])]

    # Merge consecutive label words into multi-word labels
    label_boxes_raw = [boxes[i] for i in label_idxs]
    label_boxes = _merge_label_words(label_boxes_raw)

    # All boxes are potential value candidates
    value_boxes = boxes  # we'll skip self-matches below

    pairs: list[dict] = []
    used_value_idxs: set[int] = set()

    for lb in label_boxes:
        label_text = lb["text"].rstrip(":").strip()
        if not label_text:
            continue

        lb_cy = _box_center_y(lb)
        lb_right = lb["x"] + lb["width"]
        lb_h = lb["height"] or 12.0

        line_thresh = lb_h * _LINE_THRESH_FACTOR
        below_thresh = lb_h * _BELOW_THRESH_FACTOR

        label_bbox = {
            "x": lb["x"], "y": lb["y"],
            "width": lb["width"], "height": lb["height"],
        }

        # 1) Find candidates to the RIGHT on the same line
        right_candidates = []
        for i, vb in enumerate(value_boxes):
            vb_cy = _box_center_y(vb)
            on_same_line = abs(vb_cy - lb_cy) <= line_thresh
            to_the_right = vb["x"] >= lb_right + _RIGHT_MIN_GAP
            is_same_text = vb["text"].rstrip(":").strip() == label_text
            if on_same_line and to_the_right and not is_same_text:
                right_candidates.append((i, vb))

        if right_candidates:
            # Pick the nearest to the right (smallest x)
            right_candidates.sort(key=lambda t: t[1]["x"])
            # Merge consecutive right-side boxes on same line into one value
            value_parts = []
            value_boxes_used: list[dict] = []
            prev_right_edge = lb_right
            for i, vb in right_candidates:
                gap = vb["x"] - prev_right_edge
                if gap > lb_h * 4 and value_parts:
                    break  # too far; stop here
                if _is_label_candidate(vb["text"]) and value_parts:
                    break  # new label starts; stop
                value_parts.append(vb["text"])
                value_boxes_used.append(vb)
                prev_right_edge = vb["x"] + vb["width"]
                used_value_idxs.add(i)

            value_text = " ".join(value_parts).strip()
            if value_text and value_boxes_used:
                pairs.append({
                    "label": label_text,
                    "value": value_text,
                    "bbox": _make_bbox(value_boxes_used),
                    "label_bbox": label_bbox,
                    "confidence": lb["confidence"],
                })
            else:
                # Label found but value is empty — emit label-only entry
                pairs.append({
                    "label": label_text,
                    "value": "",
                    "bbox": None,
                    "label_bbox": label_bbox,
                    "confidence": lb["confidence"],
                })
            continue

        # 2) Nothing to the right — look BELOW
        below_candidates = []
        for i, vb in enumerate(value_boxes):
            vb_top = vb["y"]
            lb_bottom = lb["y"] + lb["height"]
            is_below = vb_top > lb_bottom - 4  # slight tolerance
            vertical_gap = vb_top - lb_bottom
            within_thresh = vertical_gap <= below_thresh
            is_same_text = vb["text"].rstrip(":").strip() == label_text
            if is_below and within_thresh and not is_same_text:
                below_candidates.append((i, vb, vertical_gap))

        if below_candidates:
            below_candidates.sort(key=lambda t: (t[2], t[1]["x"]))
            i, vb, _ = below_candidates[0]
            if not _is_label_candidate(vb["text"]):
                value_text, value_boxes_used, used_value_idxs = _merge_adjacent_value_tokens(
                    vb, i, value_boxes, used_value_idxs, lb_h
                )
                if value_text:
                    pairs.append({
                        "label": label_text,
                        "value": value_text,
                        "bbox": _make_bbox(value_boxes_used),
                        "label_bbox": label_bbox,
                        "confidence": lb["confidence"],
                    })
                    continue

        # 3) Nothing to the right or below — look ABOVE (for label-below-value layouts,
        #    e.g., "Net Payable" label appearing beneath the value "73001")
        above_candidates = []
        for i, vb in enumerate(value_boxes):
            if i in used_value_idxs:
                continue
            vb_bottom = vb["y"] + vb["height"]
            lb_top = lb["y"]
            is_above = vb_bottom < lb_top + 4  # slight tolerance
            vertical_gap = lb_top - vb_bottom
            within_thresh = vertical_gap <= below_thresh
            is_same_text = vb["text"].rstrip(":").strip() == label_text
            if is_above and within_thresh and not is_same_text:
                above_candidates.append((i, vb, vertical_gap))

        if above_candidates:
            above_candidates.sort(key=lambda t: (t[2], abs(_box_center_x(t[1]) - _box_center_x(lb))))
            i, vb, _ = above_candidates[0]
            if not _is_label_candidate(vb["text"]):
                value_text, value_boxes_used, used_value_idxs = _merge_adjacent_value_tokens(
                    vb, i, value_boxes, used_value_idxs, lb_h
                )
                if value_text:
                    pairs.append({
                        "label": label_text,
                        "value": value_text,
                        "bbox": _make_bbox(value_boxes_used),
                        "label_bbox": label_bbox,
                        "confidence": lb["confidence"],
                    })
                    continue

        # 4) No value found at all — emit a label-only entry with blank value
        pairs.append({
            "label": label_text,
            "value": "",
            "bbox": None,
            "label_bbox": label_bbox,
            "confidence": lb["confidence"],
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
        if text_clean and float(conf) >= _MIN_OCR_CONF:
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
