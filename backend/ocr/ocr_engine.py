"""
backend/ocr/ocr_engine.py — Triple OCR Engine with ensemble confidence scoring.

Engines
-------
* Tesseract (pytesseract)  — traditional OCR, always attempted first
* EasyOCR                  — deep-learning OCR, optional
* PaddleOCR                — production-grade OCR, optional

Each engine is imported lazily and degraded gracefully when not installed.
Results from available engines are merged using ensemble confidence scoring:
the character/word with the highest average confidence across engines wins.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional engine flags
# ---------------------------------------------------------------------------

try:
    import pytesseract
    from PIL import Image as _PILImage
    _TESSERACT_AVAILABLE = True
except ImportError:
    _TESSERACT_AVAILABLE = False
    logger.info("pytesseract not installed — Tesseract OCR engine disabled")

try:
    import easyocr as _easyocr_module
    _EASYOCR_AVAILABLE = True
except ImportError:
    _EASYOCR_AVAILABLE = False
    logger.info("easyocr not installed — EasyOCR engine disabled")

try:
    from paddleocr import PaddleOCR as _PaddleOCR
    _PADDLEOCR_AVAILABLE = True
except ImportError:
    _PADDLEOCR_AVAILABLE = False
    logger.info("paddleocr not installed — PaddleOCR engine disabled")


def _find_tesseract_cmd() -> str | None:
    return os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

class WordResult:
    """A single recognized word with bounding box and confidence."""

    __slots__ = ("text", "confidence", "x", "y", "width", "height", "engine")

    def __init__(
        self,
        text: str,
        confidence: float,
        x: float,
        y: float,
        width: float,
        height: float,
        engine: str,
    ) -> None:
        self.text = text
        self.confidence = confidence  # 0.0 – 1.0
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.engine = engine

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "engine": self.engine,
        }


class PageOCRResult:
    """OCR output for a single PDF page."""

    def __init__(
        self,
        page_number: int,
        words: list[WordResult],
        full_text: str,
        engines_used: list[str],
        avg_confidence: float,
    ) -> None:
        self.page_number = page_number
        self.words = words
        self.full_text = full_text
        self.engines_used = engines_used
        self.avg_confidence = avg_confidence

    def to_dict(self) -> dict:
        return {
            "page_number": self.page_number,
            "full_text": self.full_text,
            "engines_used": self.engines_used,
            "avg_confidence": round(self.avg_confidence, 4),
            "word_count": len(self.words),
            "words": [w.to_dict() for w in self.words],
        }


# ---------------------------------------------------------------------------
# OCR Engine
# ---------------------------------------------------------------------------

class OCREngine:
    """
    Triple OCR engine that combines Tesseract, EasyOCR, and PaddleOCR.

    Usage::

        engine = OCREngine()
        result = engine.ocr_page(pdf_path, page_number=1)
        print(result.full_text)
        print(result.avg_confidence)
    """

    def __init__(
        self,
        use_tesseract: bool = True,
        use_easyocr: bool = True,
        use_paddleocr: bool = True,
        zoom: float = 2.0,
        lang: str = "en",
    ) -> None:
        self._use_tesseract = use_tesseract and _TESSERACT_AVAILABLE
        self._use_easyocr = use_easyocr and _EASYOCR_AVAILABLE
        self._use_paddleocr = use_paddleocr and _PADDLEOCR_AVAILABLE
        self._zoom = zoom
        self._lang = lang
        self._easyocr_reader: Any = None
        self._paddleocr: Any = None
        self._tesseract_cmd = _find_tesseract_cmd()

    # ------------------------------------------------------------------
    # Lazy initialisers
    # ------------------------------------------------------------------

    def _get_easyocr_reader(self) -> Any:
        if self._easyocr_reader is None and _EASYOCR_AVAILABLE:
            self._easyocr_reader = _easyocr_module.Reader(
                ["en"], gpu=False, verbose=False
            )
        return self._easyocr_reader

    def _get_paddleocr(self) -> Any:
        if self._paddleocr is None and _PADDLEOCR_AVAILABLE:
            self._paddleocr = _PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        return self._paddleocr

    # ------------------------------------------------------------------
    # Page rendering
    # ------------------------------------------------------------------

    def _render_page(self, pdf_path: str, page_number: int) -> bytes:
        """Render a PDF page to PNG bytes at self._zoom magnification."""
        doc = fitz.open(pdf_path)
        try:
            page = doc[page_number - 1]
            mat = fitz.Matrix(self._zoom, self._zoom)
            pix = page.get_pixmap(matrix=mat)
            return pix.tobytes("png")
        finally:
            doc.close()

    # ------------------------------------------------------------------
    # Individual engine runners
    # ------------------------------------------------------------------

    def _run_tesseract(self, img_bytes: bytes) -> list[WordResult]:
        """Run Tesseract and return per-word results."""
        if not self._use_tesseract or not _TESSERACT_AVAILABLE:
            return []
        try:
            if self._tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd
            img = _PILImage.open(io.BytesIO(img_bytes))
            data = pytesseract.image_to_data(
                img, output_type=pytesseract.Output.DICT, lang="eng"
            )
            words: list[WordResult] = []
            n = len(data["text"])
            z = self._zoom
            for i in range(n):
                word = (data["text"][i] or "").strip()
                conf = data["conf"][i]
                if not word or conf < 0:
                    continue
                # Tesseract confidence is 0–100; normalise to 0–1
                confidence = max(0.0, min(conf / 100.0, 1.0))
                x = data["left"][i] / z
                y = data["top"][i] / z
                w = data["width"][i] / z
                h = data["height"][i] / z
                words.append(WordResult(word, confidence, x, y, w, h, "tesseract"))
            return words
        except Exception as exc:
            logger.warning("Tesseract OCR failed: %s", exc)
            return []

    def _run_easyocr(self, img_bytes: bytes) -> list[WordResult]:
        """Run EasyOCR and return per-word results."""
        if not self._use_easyocr or not _EASYOCR_AVAILABLE:
            return []
        try:
            reader = self._get_easyocr_reader()
            import numpy as _np
            img_array = _np.frombuffer(img_bytes, dtype=_np.uint8)
            import cv2 as _cv2
            img = _cv2.imdecode(img_array, _cv2.IMREAD_COLOR)
            results = reader.readtext(img)
            words: list[WordResult] = []
            z = self._zoom
            for bbox_pts, text, conf in results:
                text = (text or "").strip()
                if not text:
                    continue
                xs = [p[0] for p in bbox_pts]
                ys = [p[1] for p in bbox_pts]
                x = min(xs) / z
                y = min(ys) / z
                w = (max(xs) - min(xs)) / z
                h = (max(ys) - min(ys)) / z
                words.append(WordResult(text, float(conf), x, y, w, h, "easyocr"))
            return words
        except Exception as exc:
            logger.warning("EasyOCR failed: %s", exc)
            return []

    def _run_paddleocr(self, img_bytes: bytes) -> list[WordResult]:
        """Run PaddleOCR and return per-word results."""
        if not self._use_paddleocr or not _PADDLEOCR_AVAILABLE:
            return []
        try:
            ocr = self._get_paddleocr()
            import numpy as _np
            img_array = _np.frombuffer(img_bytes, dtype=_np.uint8)
            import cv2 as _cv2
            img = _cv2.imdecode(img_array, _cv2.IMREAD_COLOR)
            result = ocr.ocr(img, cls=True)
            words: list[WordResult] = []
            z = self._zoom
            if result and result[0]:
                for line in result[0]:
                    bbox_pts, (text, conf) = line
                    text = (text or "").strip()
                    if not text:
                        continue
                    xs = [p[0] for p in bbox_pts]
                    ys = [p[1] for p in bbox_pts]
                    x = min(xs) / z
                    y = min(ys) / z
                    w = (max(xs) - min(xs)) / z
                    h = (max(ys) - min(ys)) / z
                    words.append(WordResult(text, float(conf), x, y, w, h, "paddleocr"))
            return words
        except Exception as exc:
            logger.warning("PaddleOCR failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # PyMuPDF native extraction (non-image pages)
    # ------------------------------------------------------------------

    def _run_pymupdf(self, pdf_path: str, page_number: int) -> list[WordResult]:
        """Extract words from a native PDF page (no image conversion needed)."""
        try:
            doc = fitz.open(pdf_path)
            page = doc[page_number - 1]
            raw_words = page.get_text("words")
            doc.close()
            words: list[WordResult] = []
            for w in raw_words:
                x0, y0, x1, y1, word, *_ = w
                word = word.strip()
                if not word:
                    continue
                words.append(
                    WordResult(word, 0.95, x0, y0, x1 - x0, y1 - y0, "pymupdf")
                )
            return words
        except Exception as exc:
            logger.warning("PyMuPDF word extraction failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Ensemble merge
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_results(
        results_by_engine: list[list[WordResult]],
    ) -> list[WordResult]:
        """
        Merge word results from multiple engines using a spatial grid.

        For overlapping bounding boxes (IOU > 0.3), keep the word with the
        highest confidence.  Non-overlapping words are kept as-is.
        """
        all_words: list[WordResult] = []
        for engine_words in results_by_engine:
            all_words.extend(engine_words)

        if not all_words:
            return []

        # Sort by (y, x) – reading order
        all_words.sort(key=lambda w: (round(w.y / 5) * 5, w.x))

        merged: list[WordResult] = []
        used = [False] * len(all_words)

        def _iou(a: WordResult, b: WordResult) -> float:
            ax1, ay1 = a.x, a.y
            ax2, ay2 = a.x + a.width, a.y + a.height
            bx1, by1 = b.x, b.y
            bx2, by2 = b.x + b.width, b.y + b.height
            ix1 = max(ax1, bx1)
            iy1 = max(ay1, by1)
            ix2 = min(ax2, bx2)
            iy2 = min(ay2, by2)
            if ix2 <= ix1 or iy2 <= iy1:
                return 0.0
            inter = (ix2 - ix1) * (iy2 - iy1)
            area_a = a.width * a.height
            area_b = b.width * b.height
            union = area_a + area_b - inter
            return inter / union if union > 0 else 0.0

        for i, word in enumerate(all_words):
            if used[i]:
                continue
            best = word
            for j in range(i + 1, len(all_words)):
                if used[j]:
                    continue
                if _iou(word, all_words[j]) > 0.3:
                    used[j] = True
                    if all_words[j].confidence > best.confidence:
                        best = all_words[j]
            merged.append(best)
            used[i] = True

        return merged

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available_engines(self) -> list[str]:
        engines = ["pymupdf"]
        if self._use_tesseract:
            engines.append("tesseract")
        if self._use_easyocr:
            engines.append("easyocr")
        if self._use_paddleocr:
            engines.append("paddleocr")
        return engines

    def ocr_page(self, pdf_path: str, page_number: int) -> PageOCRResult:
        """
        OCR a single page using all available engines.

        Args:
            pdf_path:    Absolute path to the PDF.
            page_number: 1-based page index.

        Returns:
            :class:`PageOCRResult` with merged word list and metrics.
        """
        # Try PyMuPDF native extraction first
        native_words = self._run_pymupdf(pdf_path, page_number)
        native_text = " ".join(w.text for w in native_words).strip()

        engines_used: list[str] = ["pymupdf"]
        all_engine_results: list[list[WordResult]] = []

        # If native extraction got meaningful text, use it and skip OCR
        if native_text and len(native_text) > 20:
            all_engine_results.append(native_words)
        else:
            # Render to image and run OCR engines
            img_bytes = self._render_page(pdf_path, page_number)

            tess_words = self._run_tesseract(img_bytes)
            if tess_words:
                all_engine_results.append(tess_words)
                engines_used.append("tesseract")

            easy_words = self._run_easyocr(img_bytes)
            if easy_words:
                all_engine_results.append(easy_words)
                engines_used.append("easyocr")

            paddle_words = self._run_paddleocr(img_bytes)
            if paddle_words:
                all_engine_results.append(paddle_words)
                engines_used.append("paddleocr")

            # Fallback: if no OCR engine worked, use native (may be empty)
            if not all_engine_results:
                all_engine_results.append(native_words)

        merged = self._merge_results(all_engine_results)
        full_text = " ".join(w.text for w in merged)
        avg_conf = (
            sum(w.confidence for w in merged) / len(merged) if merged else 0.0
        )

        return PageOCRResult(
            page_number=page_number,
            words=merged,
            full_text=full_text,
            engines_used=engines_used,
            avg_confidence=avg_conf,
        )

    def ocr_document(self, pdf_path: str) -> list[PageOCRResult]:
        """OCR all pages of a PDF and return a list of PageOCRResult."""
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        doc.close()

        return [self.ocr_page(pdf_path, p) for p in range(1, page_count + 1)]
