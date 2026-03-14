"""
PDF processing service using PyMuPDF and OpenCV
"""

import io
import json
import csv
import logging
import re
import sys
import os
from pathlib import Path

import shutil

import fitz  # PyMuPDF

try:
    import cv2
    import numpy as np
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

# Support both direct execution (backend/ on sys.path) and package import
try:
    from config import settings
except ImportError:
    # When imported from root app (backend/ not on sys.path)
    _backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    sys.path.insert(0, os.path.abspath(_backend_dir + "/backend"))
    from config import settings  # type: ignore[import]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional OCR support
# ---------------------------------------------------------------------------
try:
    import pytesseract
    from PIL import Image as _PILImage
    _PYTESSERACT_AVAILABLE = True
except ImportError:
    _PYTESSERACT_AVAILABLE = False

# Address Book fields to extract
ADDRESS_BOOK_FIELDS = [
    "Name",
    "Street Address",
    "City",
    "State",
    "Zip Code",
    "Home Phone",
    "Cell Phone",
    "Work Phone",
    "Email",
]

# Pattern to split packed lines at known field label boundaries.
# Uses a zero-width lookahead so the label itself stays in the next segment.
# Handles optional leading punctuation/quotes before the label.
_PACKED_SPLIT_RE = re.compile(
    r'(?<!\A)\s*["\']?\s*(?='
    r'(?:Street\s+Address|Zip\s+Code|Home\s+Phone|Cell\s+Phone|Work\s+Phone|City|State|Email)'
    r'\s*[:\s])',
    re.IGNORECASE,
)

# Regexes used to detect address-book field labels in the raw text.
# When ≥ 4 of these match, the document is treated as an address-book
# template and all 9 fields are guaranteed to appear in the result (with
# an empty value for any field whose slot is blank in the source PDF).
_TEMPLATE_LABEL_PATTERNS: list[re.Pattern] = [
    re.compile(r'\bName\s*[:\s]', re.IGNORECASE),
    re.compile(r'\bStreet\s+Address\s*[:\s]', re.IGNORECASE),
    re.compile(r'\bCity\s*:', re.IGNORECASE),
    re.compile(r'\bState\s*:', re.IGNORECASE),
    re.compile(r'\bZip\s+Code\s*:', re.IGNORECASE),
    re.compile(r'\bHome\s+Phone\s*:', re.IGNORECASE),
    re.compile(r'\bCell\s+Phone\s*:', re.IGNORECASE),
    re.compile(r'\bWork\s+Phone\s*:', re.IGNORECASE),
    re.compile(r'\bEmail\s*:', re.IGNORECASE),
]


def _expand_packed_lines(lines: list[str]) -> list[str]:
    """Split lines that contain multiple packed field labels into separate lines."""
    expanded: list[str] = []
    for raw in lines:
        # Only try to split if the line contains more than one known label
        segments = _PACKED_SPLIT_RE.split(raw)
        expanded.extend(seg.strip() for seg in segments if seg.strip())
    return expanded


class PDFService:
    """Service for reading, processing, and exporting PDF files."""

    def extract(self, file_path: str) -> tuple[str, list, int]:
        """
        Extract text and tables from a PDF.

        Returns:
            tuple: (full_text, tables, page_count)
                   tables is a list of tables; each table is a list of rows;
                   each row is a list of cell strings.
        """
        doc = fitz.open(file_path)
        page_count = len(doc)
        full_text_parts: list[str] = []
        tables: list[list[list[str]]] = []

        for page in doc:
            # Extract plain text
            text = page.get_text()

            # OCR fallback for scanned/image-based pages
            if not text.strip() and _PYTESSERACT_AVAILABLE:
                try:
                    _custom_cmd = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
                    if _custom_cmd:
                        pytesseract.pytesseract.tesseract_cmd = _custom_cmd
                    mat = fitz.Matrix(2, 2)
                    pix = page.get_pixmap(matrix=mat)
                    img = _PILImage.open(io.BytesIO(pix.tobytes("png")))
                    text = pytesseract.image_to_string(img)
                    logger.info("OCR fallback produced %d chars", len(text))
                except Exception as exc:
                    logger.warning("OCR fallback failed: %s", exc)
                    text = ""

            full_text_parts.append(text)

            # Attempt to find table-like structures using bounding boxes
            if _CV2_AVAILABLE:
                page_tables = self._extract_tables_from_page(page)
                tables.extend(page_tables)

        doc.close()
        return "\n".join(full_text_parts), tables, page_count

    def _extract_tables_from_page(self, page) -> list[list[list[str]]]:
        """
        Detect and extract tables from a PDF page using OpenCV line detection.
        Returns a list of tables found on the page.
        """
        tables: list[list[list[str]]] = []

        if not _CV2_AVAILABLE:
            return tables

        # Render page to an image for OpenCV processing
        mat = fitz.Matrix(2, 2)  # 2x zoom for better accuracy
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if img is None:
            return tables

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)

        # Detect horizontal and vertical lines
        horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))

        horiz_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horiz_kernel)
        vert_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vert_kernel)

        combined = cv2.add(horiz_lines, vert_lines)
        contours, _ = cv2.findContours(
            combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        scale = 2  # matches the fitz.Matrix zoom above
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if w < 50 or h < 20:
                continue

            # Map pixel coords back to PDF space
            rect = fitz.Rect(
                x / scale, y / scale, (x + w) / scale, (y + h) / scale
            )
            words = page.get_text("words", clip=rect)
            if not words:
                continue

            # Group words into a simple 1-row table
            row = [word[4] for word in sorted(words, key=lambda w: w[0])]
            tables.append([row])

        return tables

    def export(
        self,
        document_id: str,
        file_path: str,
        fields: list[dict],
        fmt: str = "pdf",
    ) -> str:
        """
        Export the document with updated data.

        Args:
            document_id: Unique identifier of the document.
            file_path: Path to the original PDF file.
            fields: List of extracted/edited field dicts.
            fmt: Output format ('pdf', 'json', or 'csv').

        Returns:
            Path to the exported file.
        """
        export_dir = Path(settings.EXPORT_DIR)
        export_dir.mkdir(parents=True, exist_ok=True)
        export_path = export_dir / f"{document_id}.{fmt}"

        if fmt == "json":
            export_path.write_text(
                json.dumps(fields, indent=2, default=str), encoding="utf-8"
            )

        elif fmt == "csv":
            if fields:
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=fields[0].keys())
                writer.writeheader()
                writer.writerows(fields)
                export_path.write_text(output.getvalue(), encoding="utf-8")
            else:
                export_path.write_text("", encoding="utf-8")

        else:  # pdf
            self._export_as_pdf(file_path, fields, str(export_path))

        return str(export_path)

    @staticmethod
    def map_address_book_fields(text: str) -> list[dict]:
        """
        Parse OCR/PDF text and map content to address-book fields.

        Handles address books where multiple fields are packed on one line, e.g.:
            City: Asansol State: WB "Zip Code:_ 713301
            Home Phone: Cell Phone:__7699888010

        Parsing rules
        -------------
        * **Name**           – line starting with ``Name`` (no colon), value follows.
        * **Street Address** – inline value after label; stops at City if on same line.
        * **City**           – ``City: <value>`` (value ends before next field keyword).
        * **State**          – ``State: <value>``; underscores/quotes stripped.
        * **Zip Code**       – ``Zip Code: <value>``; underscores/quotes stripped.
        * **Cell Phone**     – ``Cell Phone:`` label; 10-digit number extracted.
        * **Home Phone**     – ``Home Phone:`` label; 10-digit number extracted.
        * **Work Phone**     – ``Work Phone:`` label; 10-digit number extracted.
        * **Email**          – ``Email: <value>``; skipped if empty.
        * Labels with no value are silently skipped.

        Args:
            text: Raw OCR or extracted text from the PDF page.

        Returns:
            Ordered list of ``{"field_name": ..., "value": ...}`` dicts.
        """

        def _clean(val: str) -> str:
            """Strip leading/trailing underscores, quotes, spaces, and colons."""
            return val.strip('_" :').strip()

        def _extract_phone(segment: str) -> str | None:
            """Extract a 10-digit phone number from a string."""
            digits = re.sub(r"\D", "", segment)
            m = re.search(r"\d{10}", digits)
            return m.group() if m else None

        def _is_field_label(line: str) -> bool:
            """Return True if line starts with a known address-book field label."""
            stripped = line.lstrip('"\'_ ')
            for field in ADDRESS_BOOK_FIELDS:
                if stripped.startswith(field):
                    return True
            return False

        # ------------------------------------------------------------------
        # Step 1: split raw text into lines, then expand packed lines so that
        # each field label starts its own virtual line.
        # ------------------------------------------------------------------
        raw_lines = text.splitlines()
        lines = _expand_packed_lines(raw_lines)

        result: list[dict] = []
        i = 0

        while i < len(lines):
            # Strip leading punctuation/quotes that sometimes prefix a label
            line = lines[i].strip().lstrip('"\'')

            if not line:
                i += 1
                continue

            # ------------------------------------------------------------------
            # Name: "Name Rahul Misra" (no colon after Name)
            # ------------------------------------------------------------------
            if re.match(r"^Name\s+\S", line, re.IGNORECASE):
                name_val = re.sub(r"^Name\s+", "", line, flags=re.IGNORECASE).strip()
                if name_val:
                    result.append({"field_name": "Name", "value": name_val})

            # ------------------------------------------------------------------
            # Street Address: value on same line; stop at City: if present
            # ------------------------------------------------------------------
            elif re.match(r"^Street\s+Address", line, re.IGNORECASE):
                label_end = re.match(r"^Street\s+Address\s*:?(\s*)", line, re.IGNORECASE)
                inline = line[label_end.end():].strip() if label_end else ""

                # If City: appears on the same line, truncate street at that point
                city_inline = re.search(r"\s+City\s*:", inline, re.IGNORECASE)
                if city_inline:
                    inline = inline[:city_inline.start()].strip()

                street_parts: list[str] = []
                if inline:
                    street_parts.append(inline)

                # Collect continuation lines until a field label
                i += 1
                while i < len(lines):
                    next_line = lines[i].strip()
                    if _is_field_label(next_line):
                        break
                    if next_line:
                        street_parts.append(next_line)
                    i += 1

                if street_parts:
                    result.append({
                        "field_name": "Street Address",
                        "value": ", ".join(street_parts),
                    })
                continue  # i already advanced; skip i += 1 at bottom

            # ------------------------------------------------------------------
            # City: <value>
            # ------------------------------------------------------------------
            elif re.match(r"^City\s*:", line, re.IGNORECASE):
                raw_val = re.sub(r"^City\s*:\s*", "", line, flags=re.IGNORECASE)
                # Value ends before the next field keyword on same segment
                trimmed = re.split(
                    r'\s+(?:State|Zip\s+Code|Home\s+Phone|Cell\s+Phone|Work\s+Phone|Email)\s*:',
                    raw_val, maxsplit=1, flags=re.IGNORECASE
                )[0]
                city_val = _clean(trimmed)
                if city_val:
                    result.append({"field_name": "City", "value": city_val})

            # ------------------------------------------------------------------
            # State: <value>
            # ------------------------------------------------------------------
            elif re.match(r"^State\s*:", line, re.IGNORECASE):
                raw_val = re.sub(r"^State\s*:\s*", "", line, flags=re.IGNORECASE)
                trimmed = re.split(
                    r'\s+(?:Zip\s+Code|Home\s+Phone|Cell\s+Phone|Work\s+Phone|Email)\s*:',
                    raw_val, maxsplit=1, flags=re.IGNORECASE
                )[0]
                state_val = _clean(trimmed)
                if state_val:
                    result.append({"field_name": "State", "value": state_val})

            # ------------------------------------------------------------------
            # Zip Code: <value>
            # ------------------------------------------------------------------
            elif re.match(r"^Zip\s+Code\s*:", line, re.IGNORECASE):
                raw_val = re.sub(r"^Zip\s+Code\s*:\s*", "", line, flags=re.IGNORECASE)
                trimmed = re.split(
                    r'\s+(?:Home\s+Phone|Cell\s+Phone|Work\s+Phone|Email)\s*:',
                    raw_val, maxsplit=1, flags=re.IGNORECASE
                )[0]
                zip_val = _clean(trimmed)
                if zip_val:
                    result.append({"field_name": "Zip Code", "value": zip_val})

            # ------------------------------------------------------------------
            # Home Phone: <10-digit number>
            # ------------------------------------------------------------------
            elif re.match(r"^Home\s+Phone\s*:", line, re.IGNORECASE):
                raw_val = re.sub(r"^Home\s+Phone\s*:\s*", "", line, flags=re.IGNORECASE)
                phone = _extract_phone(raw_val)
                if not phone:
                    # look ahead for number on next line
                    j = i + 1
                    while j < len(lines):
                        nxt = lines[j].strip()
                        if nxt and _is_field_label(nxt):
                            break
                        if nxt:
                            phone = _extract_phone(nxt)
                            if phone:
                                break
                        j += 1
                if phone:
                    result.append({"field_name": "Home Phone", "value": phone})

            # ------------------------------------------------------------------
            # Cell Phone: <10-digit number>
            # ------------------------------------------------------------------
            elif re.match(r"^Cell\s+Phone\s*:", line, re.IGNORECASE):
                raw_val = re.sub(r"^Cell\s+Phone\s*:\s*", "", line, flags=re.IGNORECASE)
                phone = _extract_phone(raw_val)
                if not phone:
                    j = i + 1
                    while j < len(lines):
                        nxt = lines[j].strip()
                        if nxt and _is_field_label(nxt):
                            break
                        if nxt:
                            phone = _extract_phone(nxt)
                            if phone:
                                break
                        j += 1
                if phone:
                    result.append({"field_name": "Cell Phone", "value": phone})

            # ------------------------------------------------------------------
            # Work Phone: <10-digit number>
            # ------------------------------------------------------------------
            elif re.match(r"^Work\s+Phone\s*:", line, re.IGNORECASE):
                raw_val = re.sub(r"^Work\s+Phone\s*:\s*", "", line, flags=re.IGNORECASE)
                phone = _extract_phone(raw_val)
                if phone:
                    result.append({"field_name": "Work Phone", "value": phone})

            # ------------------------------------------------------------------
            # Email: <value>
            # ------------------------------------------------------------------
            elif re.match(r"^Email\s*:", line, re.IGNORECASE):
                email_val = re.sub(r"^Email\s*:\s*", "", line, flags=re.IGNORECASE).strip()
                if email_val:
                    result.append({"field_name": "Email", "value": email_val})

            i += 1

        # ------------------------------------------------------------------
        # Template-completeness pass
        # ------------------------------------------------------------------
        # When the raw text contains ≥ 4 address-book field labels the
        # document is an address-book template (possibly blank).  In that
        # case every ADDRESS_BOOK_FIELD must appear in the output so the
        # editor can render an editable row for every slot — even those
        # that are empty in the source PDF.  Missing fields get an empty
        # value and a confidence of 0.0 so downstream validation logic
        # (e.g. _is_field_invalid) correctly flags them for user input.
        label_hits = sum(
            1 for pat in _TEMPLATE_LABEL_PATTERNS if pat.search(text)
        )
        if label_hits >= 4:
            present = {item["field_name"] for item in result}
            for fn in ADDRESS_BOOK_FIELDS:
                if fn not in present:
                    result.append({"field_name": fn, "value": "", "confidence": 0.0})

        return result

    def _export_as_pdf(
        self,
        original_path: str,
        fields: list[dict],
        output: "str | io.IOBase",
    ) -> None:
        """Overlay updated field values onto the original PDF and save.

        Args:
            original_path: Path to the original PDF file.
            fields: Field dicts with optional ``bounding_box`` and ``page_number``.
            output: Destination — either a file-system path (str) or a
                    writable binary file-like object (e.g. ``io.BytesIO``).
        """
        doc = fitz.open(original_path)

        for field in fields:
            page_number = field.get("page_number", 1)
            if page_number < 1 or page_number > len(doc):
                continue
            page = doc[page_number - 1]
            bbox = field.get("bounding_box")
            value = str(field.get("value", ""))

            # Also support flat bbox_x/bbox_y/bbox_width/bbox_height format
            if bbox is None and field.get("bbox_x") is not None:
                bx = field["bbox_x"]
                by = field["bbox_y"]
                bw = field.get("bbox_width") or 0
                bh = field.get("bbox_height") or 0
                bbox = {
                    "x0": bx,
                    "y0": by,
                    "x1": bx + bw,
                    "y1": by + bh,
                }

            if bbox:
                x1 = bbox.get("x1")
                y1 = bbox.get("y1")
                if x1 is None or y1 is None:
                    continue
                rect = fitz.Rect(
                    bbox.get("x0", 0),
                    bbox.get("y0", 0),
                    x1,
                    y1,
                )
                # White-out original area then write updated value
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                page.insert_text(
                    rect.tl, value, fontsize=10, color=(0, 0, 0)
                )

        doc.save(output)
        doc.close()