"""
backend/extraction/extractor.py — Main AI extraction orchestrator.

Combines OCR engines, field detection, RAG, and confidence scoring
into a single :class:`AIExtractor` that is called from the API layer.
"""

from __future__ import annotations

import logging
import sys
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# Resolve import paths for both direct execution and package imports
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT_DIR = os.path.dirname(_BACKEND_DIR)
for _p in (_BACKEND_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ocr.ocr_engine import OCREngine          # noqa: E402
from ocr.confidence_calculator import ConfidenceCalculator  # noqa: E402
from ocr.heatmap_generator import HeatmapGenerator  # noqa: E402
from extraction.field_detector import FieldDetector  # noqa: E402
from extraction.rag_system import RAGSystem    # noqa: E402


class AIExtractor:
    """
    High-level AI extraction pipeline.

    Workflow
    --------
    1. OCR the document with the triple engine.
    2. Compute per-word confidence and document quality.
    3. Detect address-book fields using rules + NER.
    4. Refine values using RAG similarity search.
    5. Return a structured result dict.

    Usage::

        extractor = AIExtractor()
        result = extractor.extract(pdf_path, document_id="42")
    """

    def __init__(self) -> None:
        self._ocr = OCREngine()
        self._calc = ConfidenceCalculator()
        self._heatmap = HeatmapGenerator()
        self._detector = FieldDetector()
        self._rag = RAGSystem()

    def extract(
        self,
        pdf_path: str,
        document_id: str,
        run_rag: bool = True,
    ) -> dict:
        """
        Extract all fields and metrics from a PDF.

        Args:
            pdf_path:    Absolute path to the uploaded PDF.
            document_id: String document ID (used as RAG index key).
            run_rag:     Whether to run the RAG field refinement step.

        Returns:
            dict with keys:
            * ``fields``        — list of field dicts with confidence
            * ``ocr_pages``     — per-page OCR metadata
            * ``quality``       — document quality dict
            * ``heatmaps``      — per-page heatmap JSON
            * ``extraction_time_seconds``
        """
        t0 = time.time()

        # 1. OCR
        page_results = self._ocr.ocr_document(pdf_path)
        full_text = "\n".join(pr.full_text for pr in page_results)

        # 2. Quality assessment
        quality = self._calc.document_quality(page_results)

        # 3. Field detection
        detected = self._detector.detect(full_text)

        # 4. RAG refinement
        rag_enrich: dict[str, dict] = {}
        if run_rag and full_text.strip():
            try:
                self._rag.index(full_text, document_id)
                for f in detected:
                    refined = self._rag.extract_field(
                        f.field_name, document_id, full_text
                    )
                    if refined and refined["value"]:
                        rag_enrich[f.field_name] = refined
            except Exception as exc:
                logger.warning("RAG extraction failed: %s", exc)

        # 5. Compute field-level confidence from OCR words
        all_words = [w for pr in page_results for w in pr.words]
        fields_out: list[dict] = []
        for df in detected:
            fc = self._calc.field_confidence(df.field_name, df.value, all_words)
            rag_data = rag_enrich.get(df.field_name)

            # Blend rule confidence with RAG confidence
            if rag_data:
                blended = round(
                    (fc.confidence + rag_data["confidence"]) / 2, 4
                )
            else:
                blended = fc.confidence

            fields_out.append(
                {
                    "field_name": df.field_name,
                    "value": df.value,
                    "field_type": df.field_type,
                    "confidence": blended,
                    "confidence_pct": round(blended * 100, 1),
                    "badge": fc.badge,
                    "source": "rag" if rag_data else df.source,
                    "bbox": df.bbox or fc.bounding_box,
                    "char_confidences": fc.char_confidences[:20],
                }
            )

        # 6. Heatmaps
        heatmaps = []
        for pr in page_results:
            hmap = self._heatmap.generate_json(pr)
            img = self._heatmap.generate_image(pr)
            hmap["image"] = img
            heatmaps.append(hmap)

        # 7. Per-page OCR metadata
        ocr_pages = [pr.to_dict() for pr in page_results]

        elapsed = time.time() - t0

        return {
            "document_id": document_id,
            "fields": fields_out,
            "ocr_pages": ocr_pages,
            "quality": {
                "score": quality.score,
                "grade": quality.grade,
                "page_scores": quality.page_scores,
                "header_score": quality.header_score,
                "body_score": quality.body_score,
                "footer_score": quality.footer_score,
                "total_words": quality.total_words,
                "high_conf_words": quality.high_conf_words,
                "medium_conf_words": quality.medium_conf_words,
                "low_conf_words": quality.low_conf_words,
            },
            "heatmaps": heatmaps,
            "engines_available": self._ocr.available_engines,
            "extraction_time_seconds": round(elapsed, 3),
        }
