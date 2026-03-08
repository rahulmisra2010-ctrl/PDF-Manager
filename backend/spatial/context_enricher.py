"""
backend/spatial/context_enricher.py — Contextual feature enrichment.

Takes raw spatial word data and adds higher-level contextual features:
  - Pattern recognition (invoice #, date, amount, …)
  - Field-type inference combining position + label + pattern evidence
  - Confidence breakdown across evidence sources
  - Empty-field inference (when no OCR text but position context exists)
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern registry (field_type → compiled regex)
# ---------------------------------------------------------------------------

_PATTERNS: dict[str, re.Pattern] = {
    "invoice_number": re.compile(r"(INV|inv)[-/]?\d{3,}", re.I),
    "po_number":      re.compile(r"(PO|po)[-/]?\d{3,}", re.I),
    "date":           re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    "amount":         re.compile(r"^\$?\d{1,3}(,\d{3})*(\.\d{1,2})?$"),
    "phone":          re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}"),
    "email":          re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "zip_code":       re.compile(r"\b\d{5}(-\d{4})?\b"),
    "url":            re.compile(r"https?://\S+|www\.\S+"),
}

# Label-text → field-type hints (lower-cased, colon stripped)
_LABEL_TO_FIELD: dict[str, str] = {
    "invoice":        "invoice_number",
    "invoice #":      "invoice_number",
    "invoice no":     "invoice_number",
    "invoice number": "invoice_number",
    "date":           "date",
    "invoice date":   "date",
    "due date":       "date",
    "amount":         "amount",
    "total":          "amount",
    "total due":      "amount",
    "balance due":    "amount",
    "subtotal":       "amount",
    "phone":          "phone",
    "tel":            "phone",
    "telephone":      "phone",
    "email":          "email",
    "e-mail":         "email",
    "zip":            "zip_code",
    "zip code":       "zip_code",
    "po #":           "po_number",
    "po number":      "po_number",
    "purchase order": "po_number",
    "vendor":         "vendor_name",
    "customer":       "customer_name",
    "name":           "name",
    "company":        "company_name",
    "address":        "address",
    "city":           "city",
    "state":          "state",
    "country":        "country",
}


class ContextEnricher:
    """
    Add rich contextual features to spatially-extracted word dicts.

    Usage::

        enricher = ContextEnricher()
        enriched_words = enricher.enrich(words)
    """

    def enrich(self, words: list[dict]) -> list[dict]:
        """
        Iterate over *words* (SpatialOCREngine output) and append a
        ``contextual_features`` dict to each entry.

        If ``contextual_features`` already exists it is merged/updated.
        """
        result = []
        for w in words:
            text = w.get("text", "")
            sp = w.get("spatial_features", {})
            nearby_labels = sp.get("nearby_labels", [])

            ctx = self._build_context(text, nearby_labels)

            enriched = dict(w)
            existing_ctx = enriched.get("contextual_features", {})
            # Merge: new ctx wins if existing value is falsy
            merged = {**ctx, **{k: v for k, v in existing_ctx.items() if v}}
            enriched["contextual_features"] = merged
            result.append(enriched)
        return result

    def infer_empty_field(
        self,
        position_x: float,
        position_y: float,
        page_width: float,
        page_height: float,
        nearby_labels: list[str] | None = None,
    ) -> dict:
        """
        For a position where OCR found NO text, infer what field might live
        there based on spatial context alone.

        Returns::

            {
                "field_type_inferred": "invoice_number",
                "field_type_confidence": 0.72,
                "evidence": ["label_proximity", "position_zone"],
            }
        """
        if nearby_labels is None:
            nearby_labels = []

        evidence: list[str] = []
        field_type: str | None = None
        confidence: float = 0.0

        # 1. Label-based inference
        for label in nearby_labels:
            key = label.lower().rstrip(":").strip()
            if key in _LABEL_TO_FIELD:
                field_type = _LABEL_TO_FIELD[key]
                confidence = 0.75
                evidence.append("label_proximity")
                break

        # 2. Zone-based inference (top-right → often date or amount)
        if not field_type:
            norm_x = position_x / page_width if page_width else 0
            norm_y = position_y / page_height if page_height else 0
            if norm_y < 0.15:
                if norm_x > 0.6:
                    field_type = "date"
                    confidence = 0.55
                    evidence.append("position_zone")
                elif norm_x < 0.4:
                    field_type = "invoice_number"
                    confidence = 0.50
                    evidence.append("position_zone")

        return {
            "field_type_inferred": field_type,
            "field_type_confidence": round(confidence, 3),
            "evidence": evidence,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context(text: str, nearby_labels: list[str]) -> dict:
        """Build contextual feature dict from text and neighbouring labels."""
        # Pattern matching
        matched_pattern: str | None = None
        pattern_confidence = 0.0
        for field_type, pattern in _PATTERNS.items():
            if pattern.search(text):
                matched_pattern = pattern.pattern
                pattern_confidence = 0.80
                break

        # Label-based field-type inference
        label_field: str | None = None
        label_confidence = 0.0
        for label in nearby_labels:
            key = label.lower().rstrip(":").strip()
            if key in _LABEL_TO_FIELD:
                label_field = _LABEL_TO_FIELD[key]
                label_confidence = 0.90
                break

        # Combined inference
        if label_field:
            field_type_inferred = label_field
            field_type_confidence = round(
                0.8 * label_confidence + 0.2 * pattern_confidence, 3
            )
        elif matched_pattern:
            field_type_inferred = next(
                (ft for ft, p in _PATTERNS.items() if p.pattern == matched_pattern), None
            )
            field_type_confidence = round(pattern_confidence, 3)
        else:
            field_type_inferred = None
            field_type_confidence = 0.0

        return {
            "ocr_confidence": 0.95,
            "matches_pattern": matched_pattern,
            "pattern_confidence": round(pattern_confidence, 3),
            "field_type_inferred": field_type_inferred,
            "field_type_confidence": round(field_type_confidence, 3),
        }
