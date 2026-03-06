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

import fitz  # PyMuPDF
import cv2
import numpy as np

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
                    pytesseract.pytesseract.tesseract_cmd = (
                        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                    )
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
        Parse OCR text line-by-line and map content to address-book fields.

        Parsing rules
        -------------
        * **Name**         – first line that starts with ``Name`` but has *no* colon;
                             everything after ``Name`` (or the next non-empty line) is
                             used as the value.
        * **Street Address** – text between the ``Street Address`` label and the
                             ``City:`` line; multiple lines are joined with ``", "``.
        * **City**         – line matching ``City: <value>``
        * **State**        – line matching ``State: <value>``; leading/trailing
                             underscores stripped.
        * **Zip Code**     – line matching ``Zip Code: <value>``; underscores stripped.
        * **Cell Phone**   – ``Cell Phone:`` label; a 10-digit run of digits is
                             searched on the same line then the following non-empty
                             lines (stops at the next recognisable field label).
        * Labels with no value (e.g. ``Email:`` with nothing after) are skipped.

        Args:
            text: Raw OCR or extracted text from the PDF page.

        Returns:
            Ordered list of ``{"field_name": ..., "value": ...}`` dicts.
        """

        def _clean(val: str) -> str:
            """Strip leading/trailing underscores, spaces, and colons."""
            return val.strip("_ :").strip()

        def _is_field_label(line: str) -> bool:
            """Return True if *line* starts with a known address-book field label."""
            for field in ADDRESS_BOOK_FIELDS:
                if line.startswith(field):
                    return True
            return False

        lines = text.splitlines()
        result: list[dict] = []
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            if not line:
                i += 1
                continue

            # ------------------------------------------------------------------
            # Name: starts with "Name" without a colon (e.g. "Name Rahul Misra")
            # ------------------------------------------------------------------
            if re.match(r"^Name\s+\S", line):
                name_val = re.sub(r"^Name\s+", "", line).strip()
                if name_val:
                    result.append({"field_name": "Name", "value": name_val})

            # ------------------------------------------------------------------
            # Street Address: collect lines until City:
            # ------------------------------------------------------------------
            elif line.startswith("Street Address"):
                street_parts: list[str] = []
                # Value on the same line after the label
                inline = line[len("Street Address"):].strip().lstrip(":").strip()
                if inline:
                    street_parts.append(inline)
                i += 1
                while i < len(lines):
                    next_line = lines[i].strip()
                    if next_line.startswith("City:"):
                        break
                    if next_line:
                        street_parts.append(next_line)
                    i += 1
                if street_parts:
                    result.append({
                        "field_name": "Street Address",
                        "value": ", ".join(street_parts),
                    })
                # Do not increment i again; outer loop will handle City: next
                continue

            # ------------------------------------------------------------------
            # City: City: <value>
            # ------------------------------------------------------------------
            elif line.startswith("City:"):
                city_val = line[len("City:"):].strip()
                if city_val:
                    result.append({"field_name": "City", "value": city_val})

            # ------------------------------------------------------------------
            # State: State: <value>  (strip underscores)
            # ------------------------------------------------------------------
            elif line.startswith("State:"):
                state_val = _clean(line[len("State:"):].strip())
                if state_val:
                    result.append({"field_name": "State", "value": state_val})

            # ------------------------------------------------------------------
            # Zip Code: Zip Code: <value>  (strip underscores)
            # ------------------------------------------------------------------
            elif line.startswith("Zip Code:"):
                zip_val = _clean(line[len("Zip Code:"):].strip())
                if zip_val:
                    result.append({"field_name": "Zip Code", "value": zip_val})

            # ------------------------------------------------------------------
            # Cell Phone: search same line, then next non-empty lines
            # ------------------------------------------------------------------
            elif line.startswith("Cell Phone:"):
                inline = line[len("Cell Phone:"):].strip()
                digits = re.sub(r"\D", "", inline)
                phone_match = re.search(r"\d{10}", digits)
                if phone_match:
                    result.append({"field_name": "Cell Phone", "value": phone_match.group()})
                else:
                    j = i + 1
                    while j < len(lines):
                        nxt = lines[j].strip()
                        if nxt:
                            if _is_field_label(nxt):
                                break
                            d = re.sub(r"\D", "", nxt)
                            m = re.search(r"\d{10}", d)
                            if m:
                                result.append({"field_name": "Cell Phone", "value": m.group()})
                                break
                        j += 1

            # ------------------------------------------------------------------
            # Email: skip if no value
            # ------------------------------------------------------------------
            elif line.startswith("Email:"):
                email_val = line[len("Email:"):].strip()
                if email_val:
                    result.append({"field_name": "Email", "value": email_val})

            i += 1

        return result

    def _export_as_pdf(
        self, original_path: str, fields: list[dict], output_path: str
    ) -> None:
        """Overlay updated field values onto the original PDF and save."""
        doc = fitz.open(original_path)

        for field in fields:
            page_number = field.get("page_number", 1)
            if page_number < 1 or page_number > len(doc):
                continue
            page = doc[page_number - 1]
            bbox = field.get("bounding_box")
            value = str(field.get("value", ""))

            if bbox:
                rect = fitz.Rect(
                    bbox.get("x0", 0),
                    bbox.get("y0", 0),
                    bbox.get("x1", 100),
                    bbox.get("y1", 20),
                )
                # White-out original area then write updated value
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                page.insert_text(
                    rect.tl, value, fontsize=10, color=(0, 0, 0)
                )

        doc.save(output_path)
        doc.close()