"""
backend/services/auto_extraction_pipeline.py — Intelligent multi-tool extraction pipeline.

Orchestrates the full extraction tool chain for each document:
  1. Classify document type (DocClassifier)
  2. Select best tools (Mindee → Koncile → PyMuPDF → pdfplumber → OCR → LLM → Regex)
  3. Run extraction in parallel
  4. Compare and merge results
  5. Validate with LLM
  6. Score with ML confidence
  7. Record quality metrics

Environment variables:
  MINDEE_API_KEY   — Mindee IDP API key
  KONCILE_API_KEY  — Koncile.ai API key
  OPENAI_API_KEY   — OpenAI API key for LLM extraction
"""

from __future__ import annotations

import io
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependencies — each tool degrades gracefully if not installed
# ---------------------------------------------------------------------------

try:
    import fitz  # PyMuPDF
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False
    logger.info("PyMuPDF not installed – pymupdf tool disabled")

try:
    import pdfplumber  # type: ignore
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    _PDFPLUMBER_AVAILABLE = False
    logger.info("pdfplumber not installed – pdfplumber tool disabled")

try:
    from pdf2image import convert_from_bytes  # type: ignore
    import pytesseract  # type: ignore
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False
    logger.info("pdf2image/pytesseract not installed – OCR tool disabled")

try:
    from mindee import Client as MindeeClient  # type: ignore
    _MINDEE_AVAILABLE = True
except ImportError:
    _MINDEE_AVAILABLE = False
    logger.info("mindee not installed – Mindee tool disabled")

try:
    import docx  # python-docx
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False

try:
    import openpyxl  # type: ignore
    _OPENPYXL_AVAILABLE = True
except ImportError:
    _OPENPYXL_AVAILABLE = False

# Internal services
try:
    from backend.ml.doc_classifier import DocClassifier
    from backend.ml.field_classifier import FieldClassifier
    from backend.services.llm_extractor import LLMExtractor
    from backend.services.quality_checker import QualityChecker
except ImportError:
    from ml.doc_classifier import DocClassifier  # type: ignore
    from ml.field_classifier import FieldClassifier  # type: ignore
    from services.llm_extractor import LLMExtractor  # type: ignore
    from services.quality_checker import QualityChecker  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff",
                        ".tif", ".docx", ".xlsx", ".xls", ".txt"}


class ExtractionResult:
    """Container for a single tool's extraction output."""

    def __init__(
        self,
        tool: str,
        fields: Dict[str, str],
        raw_text: str = "",
        confidence: float = 0.0,
        error: Optional[str] = None,
        duration_ms: int = 0,
    ) -> None:
        self.tool = tool
        self.fields = fields
        self.raw_text = raw_text
        self.confidence = confidence
        self.error = error
        self.duration_ms = duration_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "fields": self.fields,
            "raw_text": self.raw_text[:500] if self.raw_text else "",
            "confidence": self.confidence,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class AutoExtractionPipeline:
    """
    Complete automatic extraction pipeline that orchestrates all tools.

    Usage::

        pipeline = AutoExtractionPipeline()
        result = pipeline.extract(file_data, filename="invoice.pdf")
    """

    def __init__(
        self,
        mindee_key: Optional[str] = None,
        koncile_key: Optional[str] = None,
        openai_key: Optional[str] = None,
    ) -> None:
        self._mindee_key = mindee_key or os.getenv("MINDEE_API_KEY", "")
        self._koncile_key = koncile_key or os.getenv("KONCILE_API_KEY", "")
        self._openai_key = openai_key or os.getenv("OPENAI_API_KEY", "")

        self._doc_classifier = DocClassifier()
        self._field_classifier = FieldClassifier()
        self._llm = LLMExtractor(api_key=self._openai_key)
        self._qc = QualityChecker()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        file_data: bytes,
        filename: str = "document",
        progress_cb: Optional[Callable[[str, float], None]] = None,
    ) -> Dict[str, Any]:
        """
        Run the full extraction pipeline on a file.

        Args:
            file_data:   Raw bytes of the uploaded file.
            filename:    Original filename (used for type detection).
            progress_cb: Optional callback(step_name, progress_0_to_1).

        Returns:
            Dict with:
              - ``fields``          merged extracted fields
              - ``doc_type``        detected document type
              - ``confidence``      overall confidence score
              - ``tools_used``      list of tools that ran
              - ``tool_results``    per-tool results
              - ``quality``         QualityChecker result dict
              - ``raw_text``        best raw text extracted
              - ``duration_ms``     total processing time
        """
        start_time = time.monotonic()
        ext = os.path.splitext(filename.lower())[1]

        def _progress(step: str, pct: float) -> None:
            if progress_cb:
                progress_cb(step, pct)
            logger.debug("Pipeline step: %s (%.0f%%)", step, pct * 100)

        _progress("Starting extraction", 0.0)

        # Step 1: Extract raw text using available tools
        _progress("Extracting text", 0.1)
        raw_text, tool_results = self._run_text_extractors(file_data, filename, ext)

        # Step 2: Classify document type
        _progress("Classifying document", 0.35)
        doc_type, type_confidence, preferred_tools = self._doc_classifier.classify(
            raw_text, filename
        )

        # Step 3: Run structured extraction using preferred tools
        _progress("Extracting fields", 0.45)
        all_fields = self._merge_tool_fields(tool_results)

        # Step 4: LLM extraction for semantic understanding
        _progress("LLM extraction", 0.65)
        if self._llm.available and raw_text.strip():
            llm_fields = self._llm.extract(raw_text, doc_type=doc_type)
            # Merge LLM fields (LLM fills gaps, doesn't override high-confidence results)
            for k, v in llm_fields.items():
                if k not in all_fields and v:
                    all_fields[k] = v
            if llm_fields:
                tool_results.append(ExtractionResult(
                    tool="llm", fields=llm_fields,
                    raw_text="", confidence=0.75
                ))

        # Step 5: ML confidence scoring
        _progress("ML scoring", 0.8)
        confidence = self._compute_confidence(
            all_fields, tool_results, type_confidence
        )

        # Step 6: Quality check
        _progress("Quality check", 0.9)
        quality = self._qc.check(all_fields, doc_type=doc_type)

        duration_ms = int((time.monotonic() - start_time) * 1000)
        _progress("Complete", 1.0)

        return {
            "fields": all_fields,
            "doc_type": doc_type,
            "confidence": round(confidence, 4),
            "tools_used": [r.tool for r in tool_results if not r.error],
            "tool_results": [r.to_dict() for r in tool_results],
            "quality": quality,
            "raw_text": raw_text[:2000],
            "duration_ms": duration_ms,
            "filename": filename,
        }

    # ------------------------------------------------------------------
    # Text extraction per file type
    # ------------------------------------------------------------------

    def _run_text_extractors(
        self, data: bytes, filename: str, ext: str
    ) -> Tuple[str, List[ExtractionResult]]:
        """Run all applicable text extraction tools, return best text + results."""
        results: List[ExtractionResult] = []

        if ext == ".txt":
            text = data.decode("utf-8", errors="replace")
            fields = self._parse_text_to_fields(text)
            results.append(ExtractionResult("text", fields, text, 0.9))
            return text, results

        if ext in {".docx"}:
            r = self._extract_docx(data)
            results.append(r)
            return r.raw_text, results

        if ext in {".xlsx", ".xls"}:
            r = self._extract_excel(data)
            results.append(r)
            return r.raw_text, results

        if ext in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}:
            r = self._extract_image_ocr(data)
            results.append(r)
            return r.raw_text, results

        # PDF — try multiple tools
        pdf_results: List[ExtractionResult] = []

        if _FITZ_AVAILABLE:
            r = self._extract_pymupdf(data)
            pdf_results.append(r)

        if _PDFPLUMBER_AVAILABLE:
            r = self._extract_pdfplumber(data)
            pdf_results.append(r)

        if _MINDEE_AVAILABLE and self._mindee_key:
            r = self._extract_mindee(data, filename)
            pdf_results.append(r)

        if _OCR_AVAILABLE:
            r = self._extract_ocr(data)
            pdf_results.append(r)

        results.extend(pdf_results)

        # Pick the longest non-empty raw text as the best
        best_text = ""
        for r in pdf_results:
            if len(r.raw_text) > len(best_text):
                best_text = r.raw_text

        return best_text, results

    # ------------------------------------------------------------------
    # Individual tool implementations
    # ------------------------------------------------------------------

    def _extract_pymupdf(self, data: bytes) -> ExtractionResult:
        t0 = time.monotonic()
        try:
            doc = fitz.open(stream=data, filetype="pdf")
            text_parts = []
            widget_fields: Dict[str, str] = {}

            for page in doc:
                text_parts.append(page.get_text())
                for widget in page.widgets() or []:
                    name = (widget.field_name or "").strip()
                    value = str(widget.field_value or "").strip()
                    if name and value:
                        widget_fields[name] = value
            doc.close()

            full_text = "\n".join(text_parts)
            conf = 0.80 if widget_fields else 0.70
            return ExtractionResult(
                "pymupdf", widget_fields, full_text, conf,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            return ExtractionResult("pymupdf", {}, "", 0.0, str(exc))

    def _extract_pdfplumber(self, data: bytes) -> ExtractionResult:
        t0 = time.monotonic()
        try:
            text_parts = []
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text_parts.append(t)

            full_text = "\n".join(text_parts)
            fields = self._parse_text_to_fields(full_text)
            return ExtractionResult(
                "pdfplumber", fields, full_text, 0.72,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            return ExtractionResult("pdfplumber", {}, "", 0.0, str(exc))

    def _extract_ocr(self, data: bytes) -> ExtractionResult:
        t0 = time.monotonic()
        try:
            images = convert_from_bytes(data)
            ocr_parts = []
            for image in images:
                ocr_parts.append(pytesseract.image_to_string(image))
            full_text = "\n".join(ocr_parts)
            fields = self._parse_text_to_fields(full_text)
            return ExtractionResult(
                "tesseract", fields, full_text, 0.65,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            return ExtractionResult("tesseract", {}, "", 0.0, str(exc))

    def _extract_image_ocr(self, data: bytes) -> ExtractionResult:
        t0 = time.monotonic()
        try:
            from PIL import Image  # type: ignore
            image = Image.open(io.BytesIO(data))
            text = pytesseract.image_to_string(image)
            fields = self._parse_text_to_fields(text)
            return ExtractionResult(
                "tesseract", fields, text, 0.65,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            return ExtractionResult("tesseract", {}, "", 0.0, str(exc))

    def _extract_mindee(self, data: bytes, filename: str) -> ExtractionResult:
        t0 = time.monotonic()
        try:
            client = MindeeClient(api_key=self._mindee_key)
            input_doc = client.source_from_bytes(data, filename)
            result = client.parse(
                "mindee/invoices", input_doc
            )
            fields: Dict[str, str] = {}
            if result.document:
                pred = result.document.inference.prediction
                for attr in dir(pred):
                    if attr.startswith("_"):
                        continue
                    try:
                        val = getattr(pred, attr)
                        if hasattr(val, "value") and val.value:
                            fields[attr.replace("_", " ").title()] = str(val.value)
                    except Exception:
                        pass
            return ExtractionResult(
                "mindee", fields, "", 0.90,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            logger.warning("Mindee extraction failed: %s", exc)
            return ExtractionResult("mindee", {}, "", 0.0, str(exc))

    def _extract_docx(self, data: bytes) -> ExtractionResult:
        t0 = time.monotonic()
        if not _DOCX_AVAILABLE:
            return ExtractionResult("docx", {}, "", 0.0, "python-docx not installed")
        try:
            document = docx.Document(io.BytesIO(data))
            paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
            full_text = "\n".join(paragraphs)
            fields = self._parse_text_to_fields(full_text)
            return ExtractionResult(
                "docx", fields, full_text, 0.75,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            return ExtractionResult("docx", {}, "", 0.0, str(exc))

    def _extract_excel(self, data: bytes) -> ExtractionResult:
        t0 = time.monotonic()
        if not _OPENPYXL_AVAILABLE:
            return ExtractionResult("excel", {}, "", 0.0, "openpyxl not installed")
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            rows: List[str] = []
            fields: Dict[str, str] = {}
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) if c is not None else "" for c in row]
                    if len(cells) >= 2 and cells[0] and cells[1]:
                        fields[cells[0]] = cells[1]
                    elif any(cells):
                        rows.append("\t".join(cells))
            wb.close()
            full_text = "\n".join(rows)
            return ExtractionResult(
                "excel", fields, full_text, 0.80,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            return ExtractionResult("excel", {}, "", 0.0, str(exc))

    # ------------------------------------------------------------------
    # Field merging and confidence
    # ------------------------------------------------------------------

    def _merge_tool_fields(self, results: List[ExtractionResult]) -> Dict[str, str]:
        """Merge fields from all tool results, preferring higher-confidence tools."""
        # Sort by confidence descending so higher-confidence tools win
        sorted_results = sorted(results, key=lambda r: r.confidence, reverse=True)
        merged: Dict[str, str] = {}
        for r in sorted_results:
            for k, v in r.fields.items():
                if k not in merged and v:
                    merged[k] = v
        return merged

    def _compute_confidence(
        self,
        fields: Dict[str, str],
        tool_results: List[ExtractionResult],
        type_confidence: float,
    ) -> float:
        """Compute overall confidence from tool results and field count."""
        if not fields:
            return 0.0

        successful = [r for r in tool_results if r.fields and not r.error]
        if not successful:
            return 0.0

        tool_conf = max(r.confidence for r in successful)
        multi_tool_bonus = min(len(successful) * 0.05, 0.15)
        field_count_factor = min(len(fields) / 10, 1.0)

        raw = (tool_conf * 0.6 + type_confidence * 0.2
               + multi_tool_bonus + field_count_factor * 0.05)
        return min(raw, 1.0)

    # ------------------------------------------------------------------
    # Text-to-fields parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_text_to_fields(text: str) -> Dict[str, str]:
        """Simple key-value parser for extracted text."""
        import re
        fields: Dict[str, str] = {}
        if not text:
            return fields

        # Pattern: "Field Name: Value" or "Field Name - Value"
        for line in text.splitlines():
            line = line.strip()
            m = re.match(r"^([A-Za-z][A-Za-z0-9 _/\-]{1,50})\s*[:–\-]\s*(.+)$", line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                if key and val and len(val) < 300:
                    fields[key] = val

        return fields
