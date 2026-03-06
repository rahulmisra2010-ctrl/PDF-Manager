"""
backend/services/ai_extraction_service.py — AI-powered PDF extraction service.

Provides multi-engine text extraction with bounding-box metadata, smart field
type detection, and confidence scoring.  Uses available libraries with graceful
degradation:
  - PyMuPDF (always available) for text + bounding boxes
  - pytesseract (optional) as OCR fallback for image-based pages
  - EasyOCR (optional) for higher-accuracy OCR
  - OpenCV (optional) for image pre-processing
"""

from __future__ import annotations

import io
import logging
import os
import re
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency flags
# ---------------------------------------------------------------------------

try:
    import cv2
    import numpy as np
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image as _PILImage
    _PYTESSERACT_AVAILABLE = True
except ImportError:
    _PYTESSERACT_AVAILABLE = False

try:
    import easyocr
    _EASYOCR_AVAILABLE = True
except ImportError:
    _EASYOCR_AVAILABLE = False

# ---------------------------------------------------------------------------
# Field-type patterns for smart recognition
# ---------------------------------------------------------------------------

_FIELD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Check more-specific patterns first to avoid false matches
    ("email",    re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}")),
    ("url",      re.compile(r"https?://\S+")),
    ("currency", re.compile(r"[$€£¥]\s*[\d,]+(?:\.\d{2})?")),
    ("date",     re.compile(
        r"\b(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}"
        r"|\d{4}[/\-]\d{2}[/\-]\d{2}"
        r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
        re.IGNORECASE,
    )),
    ("zip_code", re.compile(r"^\s*\d{5}(?:-\d{4})?\s*$")),
    ("phone",    re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")),
    ("number",   re.compile(r"^\s*-?\d[\d,\.]*\s*$")),
]

_ADDRESS_KEYWORDS = re.compile(
    r"\b(?:street|st|avenue|ave|road|rd|drive|dr|boulevard|blvd|lane|ln"
    r"|court|ct|place|pl|way|circle|cir)\b",
    re.IGNORECASE,
)

_NAME_LINE_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$")


def _classify_text(text: str) -> tuple[str, float]:
    """
    Classify *text* into a field type and return (field_type, confidence).

    Returns ``("text", 0.5)`` as the default when no pattern matches.
    """
    t = text.strip()
    if not t:
        return ("text", 0.0)

    for field_type, pattern in _FIELD_PATTERNS:
        if pattern.search(t):
            return (field_type, 0.92)

    if _ADDRESS_KEYWORDS.search(t):
        return ("address", 0.80)

    if _NAME_LINE_RE.match(t):
        return ("name", 0.75)

    # Multi-word but no special pattern → generic text
    return ("text", 0.60)


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------

class AIExtractionService:
    """
    AI-powered PDF extraction service.

    Provides:
    * Per-page image rendering (PNG bytes)
    * Word-level bounding box extraction with field-type classification
    * Region-based text extraction (given pixel coordinates)
    * Smart field detection returning confidence scores
    """

    def __init__(self) -> None:
        self._easyocr_reader: Any = None  # initialised lazily

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_page(self, pdf_path: str, page_number: int, zoom: float = 1.5) -> bytes:
        """
        Render *page_number* (1-based) of *pdf_path* to PNG bytes.

        Args:
            pdf_path:    Absolute path to the PDF file.
            page_number: 1-based page number to render.
            zoom:        Scale factor (default 1.5 × gives ~108 DPI at 72 DPI base).

        Returns:
            PNG image data as bytes.
        """
        doc = fitz.open(pdf_path)
        try:
            if page_number < 1 or page_number > len(doc):
                raise ValueError(
                    f"Page {page_number} out of range (1–{len(doc)})"
                )
            page = doc[page_number - 1]
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            return pix.tobytes("png")
        finally:
            doc.close()

    def extract_page_fields(
        self,
        pdf_path: str,
        page_number: int,
        zoom: float = 1.5,
    ) -> list[dict]:
        """
        Extract all text blocks from *page_number* with bounding boxes,
        field-type classification, and confidence scores.

        Args:
            pdf_path:    Absolute path to the PDF file.
            page_number: 1-based page number.
            zoom:        Render zoom factor (used to map pixel→PDF coordinates).

        Returns:
            List of dicts with keys:
                text, field_type, confidence,
                bbox (dict: x0, y0, x1, y1 in *pixel* coordinates at *zoom*),
                page
        """
        doc = fitz.open(pdf_path)
        try:
            if page_number < 1 or page_number > len(doc):
                return []
            page = doc[page_number - 1]

            # Primary: PyMuPDF word-level extraction
            words = page.get_text("words")  # list of (x0,y0,x1,y1, text, …)

            fields: list[dict] = []
            if words:
                fields = self._words_to_fields(words, zoom, page_number)

            # Fallback to OCR if no text found
            if not fields:
                fields = self._ocr_page(page, page_number, zoom)

            return fields
        finally:
            doc.close()

    def extract_region(
        self,
        pdf_path: str,
        page_number: int,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        zoom: float = 1.5,
    ) -> dict:
        """
        Extract text from a rectangular region (pixel coordinates at *zoom*).

        Returns a dict with keys: text, field_type, confidence, bbox, page.
        """
        doc = fitz.open(pdf_path)
        try:
            if page_number < 1 or page_number > len(doc):
                return {"text": "", "field_type": "text", "confidence": 0.0}
            page = doc[page_number - 1]

            # Convert pixel coords back to PDF points
            pdf_rect = fitz.Rect(
                x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom
            )

            # Get words within the rect
            words = page.get_text("words", clip=pdf_rect)
            if words:
                text = " ".join(w[4] for w in sorted(words, key=lambda w: (w[1], w[0])))
            else:
                text = page.get_text(clip=pdf_rect).strip()

            # OCR fallback for image-based content
            if not text and _PYTESSERACT_AVAILABLE:
                text = self._ocr_region(page, pdf_rect)

            field_type, confidence = _classify_text(text)
            return {
                "text": text,
                "field_type": field_type,
                "confidence": confidence,
                "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                "page": page_number,
            }
        finally:
            doc.close()

    def detect_all_fields(self, pdf_path: str) -> list[dict]:
        """
        Auto-detect all fields across all pages of *pdf_path*.

        Returns a flat list of field dicts (same schema as
        :meth:`extract_page_fields`).
        """
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        doc.close()

        all_fields: list[dict] = []
        for pno in range(1, page_count + 1):
            all_fields.extend(self.extract_page_fields(pdf_path, pno))
        return all_fields

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _words_to_fields(
        self,
        words: list,
        zoom: float,
        page_number: int,
    ) -> list[dict]:
        """Convert PyMuPDF word tuples to field dicts with pixel bboxes."""
        fields: list[dict] = []
        for word in words:
            x0, y0, x1, y1 = word[0], word[1], word[2], word[3]
            text = word[4].strip()
            if not text:
                continue
            field_type, confidence = _classify_text(text)
            fields.append({
                "text": text,
                "field_type": field_type,
                "confidence": confidence,
                "bbox": {
                    "x0": x0 * zoom,
                    "y0": y0 * zoom,
                    "x1": x1 * zoom,
                    "y1": y1 * zoom,
                },
                "page": page_number,
            })
        return fields

    def _ocr_page(self, page, page_number: int, zoom: float) -> list[dict]:
        """OCR-based extraction when PDF has no embedded text."""
        if not _PYTESSERACT_AVAILABLE:
            return []
        try:
            import shutil
            _custom_cmd = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
            if _custom_cmd:
                pytesseract.pytesseract.tesseract_cmd = _custom_cmd
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img = _PILImage.open(io.BytesIO(pix.tobytes("png")))
            data = pytesseract.image_to_data(
                img, output_type=pytesseract.Output.DICT
            )
            fields: list[dict] = []
            n = len(data["text"])
            for i in range(n):
                text = str(data["text"][i]).strip()
                if not text:
                    continue
                conf_raw = float(data["conf"][i])
                if conf_raw < 0:
                    continue
                confidence = min(conf_raw / 100.0, 1.0)
                x, y, w, h = (
                    data["left"][i],
                    data["top"][i],
                    data["width"][i],
                    data["height"][i],
                )
                field_type, type_conf = _classify_text(text)
                fields.append({
                    "text": text,
                    "field_type": field_type,
                    "confidence": round((confidence + type_conf) / 2, 3),
                    "bbox": {
                        "x0": float(x),
                        "y0": float(y),
                        "x1": float(x + w),
                        "y1": float(y + h),
                    },
                    "page": page_number,
                })
            return fields
        except Exception as exc:
            logger.warning("OCR page extraction failed: %s", exc)
            return []

    def _ocr_region(self, page, pdf_rect: fitz.Rect) -> str:
        """OCR a specific region of a PDF page."""
        try:
            import shutil
            _custom_cmd = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
            if _custom_cmd:
                pytesseract.pytesseract.tesseract_cmd = _custom_cmd
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, clip=pdf_rect)
            img = _PILImage.open(io.BytesIO(pix.tobytes("png")))
            return pytesseract.image_to_string(img).strip()
        except Exception as exc:
            logger.warning("OCR region extraction failed: %s", exc)
            return ""

    @staticmethod
    def get_available_engines() -> list[str]:
        """Return names of available OCR/AI engines."""
        engines = ["PyMuPDF"]
        if _PYTESSERACT_AVAILABLE:
            engines.append("pytesseract")
        if _EASYOCR_AVAILABLE:
            engines.append("EasyOCR")
        if _CV2_AVAILABLE:
            engines.append("OpenCV")
        return engines
