"""
backend/ocr/confidence_calculator.py — Pixel-wise and field-level confidence.

Provides:
* Per-character confidence (aggregated from word-level engine data)
* Field-level confidence from word-list context
* Document quality assessment (0–100 %)
* Regional performance (header / body / footer)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ocr_engine import PageOCRResult, WordResult

logger = logging.getLogger(__name__)


@dataclass
class FieldConfidence:
    """Confidence metrics for a single extracted field."""

    field_name: str
    value: str
    confidence: float          # 0.0 – 1.0
    char_confidences: list[float] = field(default_factory=list)
    bounding_box: dict | None = None

    @property
    def confidence_pct(self) -> float:
        return round(self.confidence * 100, 1)

    @property
    def badge(self) -> str:
        if self.confidence >= 0.85:
            return "green"
        if self.confidence >= 0.65:
            return "yellow"
        return "red"


@dataclass
class DocumentQuality:
    """Overall quality assessment for a document."""

    score: float               # 0.0 – 100.0
    page_scores: list[float]   # per-page quality 0–100
    header_score: float
    body_score: float
    footer_score: float
    total_words: int
    high_conf_words: int
    medium_conf_words: int
    low_conf_words: int

    @property
    def grade(self) -> str:
        if self.score >= 90:
            return "Excellent"
        if self.score >= 75:
            return "Good"
        if self.score >= 55:
            return "Fair"
        return "Poor"


class ConfidenceCalculator:
    """
    Calculates confidence metrics from OCR word results.

    Usage::

        calc = ConfidenceCalculator()
        quality = calc.document_quality(page_results)
        field_conf = calc.field_confidence("Name", "Rahul Misra", words)
    """

    HIGH_THRESHOLD = 0.85
    MED_THRESHOLD = 0.60

    # Fraction of page height used for header / footer zones
    HEADER_FRAC = 0.15
    FOOTER_FRAC = 0.15

    def page_quality(self, page_result: "PageOCRResult") -> float:
        """Return a quality score (0–100) for a single page."""
        words = page_result.words
        if not words:
            return 0.0
        return round(
            sum(w.confidence for w in words) / len(words) * 100, 2
        )

    def document_quality(
        self, page_results: list["PageOCRResult"]
    ) -> DocumentQuality:
        """
        Compute overall document quality and regional scores.

        Args:
            page_results: List of :class:`~ocr_engine.PageOCRResult` objects.

        Returns:
            :class:`DocumentQuality` with per-page and regional breakdowns.
        """
        all_words: list["WordResult"] = []
        page_scores: list[float] = []

        for pr in page_results:
            page_scores.append(self.page_quality(pr))
            all_words.extend(pr.words)

        if not all_words:
            return DocumentQuality(
                score=0.0,
                page_scores=page_scores,
                header_score=0.0,
                body_score=0.0,
                footer_score=0.0,
                total_words=0,
                high_conf_words=0,
                medium_conf_words=0,
                low_conf_words=0,
            )

        total = len(all_words)
        high = sum(1 for w in all_words if w.confidence >= self.HIGH_THRESHOLD)
        medium = sum(
            1 for w in all_words
            if self.MED_THRESHOLD <= w.confidence < self.HIGH_THRESHOLD
        )
        low = total - high - medium

        overall = sum(w.confidence for w in all_words) / total * 100

        # Regional scores — approximate using Y coordinate ranges
        # We normalise y within each page by tracking per-page height via words
        header_confs: list[float] = []
        body_confs: list[float] = []
        footer_confs: list[float] = []

        for pr in page_results:
            pw = pr.words
            if not pw:
                continue
            max_y = max(w.y + w.height for w in pw) or 1.0
            for w in pw:
                rel_y = w.y / max_y
                if rel_y <= self.HEADER_FRAC:
                    header_confs.append(w.confidence)
                elif rel_y >= (1.0 - self.FOOTER_FRAC):
                    footer_confs.append(w.confidence)
                else:
                    body_confs.append(w.confidence)

        def _avg(lst: list[float]) -> float:
            return round(sum(lst) / len(lst) * 100, 2) if lst else 0.0

        return DocumentQuality(
            score=round(overall, 2),
            page_scores=page_scores,
            header_score=_avg(header_confs),
            body_score=_avg(body_confs),
            footer_score=_avg(footer_confs),
            total_words=total,
            high_conf_words=high,
            medium_conf_words=medium,
            low_conf_words=low,
        )

    def field_confidence(
        self,
        field_name: str,
        value: str,
        words: list["WordResult"],
    ) -> FieldConfidence:
        """
        Compute confidence for a specific extracted field.

        Matches value tokens against the word list and returns the average
        confidence of matched words.

        Args:
            field_name: Name of the field (e.g. "Name").
            value:      Extracted field value string.
            words:      Word results from OCR.

        Returns:
            :class:`FieldConfidence` with per-character breakdown.
        """
        if not value:
            return FieldConfidence(
                field_name=field_name, value=value, confidence=0.0
            )

        value_tokens = value.lower().split()
        matched: list["WordResult"] = []
        matched_bbox: list[dict] = []

        for w in words:
            if w.text.lower() in value_tokens:
                matched.append(w)
                matched_bbox.append(
                    {"x": w.x, "y": w.y, "width": w.width, "height": w.height}
                )

        if matched:
            avg_conf = sum(w.confidence for w in matched) / len(matched)
            # Per-character confidence: distribute word confidence across chars
            char_confs: list[float] = []
            for w in matched:
                char_confs.extend([w.confidence] * len(w.text))
            # Build bounding box that encompasses all matched words
            xs = [b["x"] for b in matched_bbox]
            ys = [b["y"] for b in matched_bbox]
            xs2 = [b["x"] + b["width"] for b in matched_bbox]
            ys2 = [b["y"] + b["height"] for b in matched_bbox]
            combined_bbox = {
                "x": min(xs),
                "y": min(ys),
                "width": max(xs2) - min(xs),
                "height": max(ys2) - min(ys),
            }
        else:
            # No word match — use a modest default confidence
            avg_conf = 0.75
            char_confs = [0.75] * len(value)
            combined_bbox = None

        return FieldConfidence(
            field_name=field_name,
            value=value,
            confidence=round(avg_conf, 4),
            char_confidences=char_confs,
            bounding_box=combined_bbox,
        )
