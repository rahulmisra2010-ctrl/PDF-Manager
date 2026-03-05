"""
PDF processing service using PyMuPDF and OpenCV
"""

import io
import json
import csv
import logging
import re
from pathlib import Path

import fitz  # PyMuPDF
import cv2
import numpy as np

from config import settings

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