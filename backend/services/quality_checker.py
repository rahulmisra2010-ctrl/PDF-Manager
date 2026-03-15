"""
backend/services/quality_checker.py — Quality metrics and validation for extracted fields.

Provides:
  - Confidence scoring per field
  - Data quality metrics across a sample set
  - Anomaly detection
  - Field format validation
  - Automatic correction suggestions
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field format validators
# ---------------------------------------------------------------------------

_FORMAT_VALIDATORS: Dict[str, Tuple[str, str]] = {
    "email": (r"^[\w.+-]+@[\w-]+\.[a-z]{2,}$", "Expected format: user@domain.com"),
    "phone": (r"^[\d\s\+\-().]{7,20}$", "Expected: 7-20 digit phone number"),
    "date": (
        r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{2}[/-]\d{2}|\w+ \d{1,2},?\s?\d{4})$",
        "Expected: MM/DD/YYYY or YYYY-MM-DD",
    ),
    "zip_code": (r"^\d{5}(-\d{4})?$", "Expected: 5-digit ZIP or ZIP+4"),
    "postal_code": (r"^[A-Z0-9]{3,10}$", "Expected: alphanumeric postal code"),
    "currency": (r"^[\$€£¥]?\s?[\d,]+\.?\d{0,2}$", "Expected: currency amount"),
    "percentage": (r"^\d+(\.\d+)?%?$", "Expected: numeric percentage"),
    "url": (r"^https?://[\w\-.]+\.\w{2,}", "Expected: https://... URL"),
}

_FIELD_NAME_TO_FORMAT: Dict[str, str] = {
    "email": "email",
    "email address": "email",
    "phone": "phone",
    "phone number": "phone",
    "cell phone": "phone",
    "home phone": "phone",
    "work phone": "phone",
    "mobile": "phone",
    "date": "date",
    "date of birth": "date",
    "dob": "date",
    "invoice date": "date",
    "due date": "date",
    "zip": "zip_code",
    "zip code": "zip_code",
    "postal code": "postal_code",
    "amount": "currency",
    "total": "currency",
    "subtotal": "currency",
    "tax amount": "currency",
    "total amount": "currency",
    "percentage": "percentage",
    "tax rate": "percentage",
    "url": "url",
    "website": "url",
}


class QualityChecker:
    """
    Validates extracted fields and computes quality metrics.

    Usage::

        qc = QualityChecker()
        result = qc.check(fields, doc_type="Invoice")
        metrics = qc.compute_metrics([result1, result2, ...])
    """

    def __init__(self, custom_validators: Optional[Dict[str, str]] = None) -> None:
        self._validators = dict(_FORMAT_VALIDATORS)
        if custom_validators:
            self._validators.update(custom_validators)

    # ------------------------------------------------------------------
    # Per-field validation
    # ------------------------------------------------------------------

    def validate_field(
        self, field_name: str, field_value: str
    ) -> Dict[str, Any]:
        """
        Validate a single field.

        Returns dict with keys:
          - ``valid`` (bool)
          - ``format_type`` (str or None)
          - ``error`` (str or None)
          - ``suggestion`` (str or None)
          - ``confidence`` (float)
        """
        name_lower = field_name.strip().lower()
        value = str(field_value).strip()

        result: Dict[str, Any] = {
            "valid": True,
            "format_type": None,
            "error": None,
            "suggestion": None,
            "confidence": 1.0,
        }

        if not value:
            result["valid"] = False
            result["error"] = "Empty value"
            result["confidence"] = 0.0
            return result

        # Detect expected format
        fmt_key = _FIELD_NAME_TO_FORMAT.get(name_lower)
        if fmt_key and fmt_key in self._validators:
            pattern, hint = self._validators[fmt_key]
            result["format_type"] = fmt_key
            if not re.match(pattern, value, re.IGNORECASE):
                result["valid"] = False
                result["error"] = f"Invalid {fmt_key} format"
                result["suggestion"] = hint
                result["confidence"] = 0.3

        # Penalize very short or very long values
        if len(value) < 2:
            result["confidence"] = min(result["confidence"], 0.4)
        elif len(value) > 500:
            result["confidence"] = min(result["confidence"], 0.6)

        return result

    # ------------------------------------------------------------------
    # Full-sample check
    # ------------------------------------------------------------------

    def check(
        self,
        fields: Dict[str, str],
        doc_type: str = "Unknown",
    ) -> Dict[str, Any]:
        """
        Run quality checks on all extracted fields.

        Returns:
          - ``field_results``        — per-field validation dicts
          - ``anomalies``            — list of anomaly descriptions
          - ``corrections``          — suggested corrections dict
          - ``overall_confidence``   — average confidence score [0, 1]
          - ``valid_field_count``    — count of valid fields
          - ``invalid_field_count``  — count of invalid fields
          - ``quality_grade``        — A/B/C/D/F grade string
        """
        field_results: Dict[str, Any] = {}
        anomalies: List[str] = []
        corrections: Dict[str, str] = {}
        confidences: List[float] = []

        for name, value in fields.items():
            vr = self.validate_field(name, value)
            field_results[name] = vr
            confidences.append(vr["confidence"])

            if not vr["valid"]:
                anomalies.append(f"Field '{name}': {vr['error']}")
                if vr.get("suggestion"):
                    corrections[name] = vr["suggestion"]

        # Anomaly: duplicate values across different field names
        value_to_fields: Dict[str, List[str]] = {}
        for name, value in fields.items():
            val_lower = str(value).strip().lower()
            if val_lower:
                value_to_fields.setdefault(val_lower, []).append(name)
        for val, names in value_to_fields.items():
            if len(names) > 1 and len(val) > 3:
                anomalies.append(
                    f"Duplicate value '{val}' across fields: {', '.join(names)}"
                )

        overall_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )
        valid_count = sum(1 for r in field_results.values() if r["valid"])
        invalid_count = len(field_results) - valid_count

        grade = self._grade(overall_confidence, invalid_count, len(fields))

        return {
            "field_results": field_results,
            "anomalies": anomalies,
            "corrections": corrections,
            "overall_confidence": round(overall_confidence, 4),
            "valid_field_count": valid_count,
            "invalid_field_count": invalid_count,
            "quality_grade": grade,
            "doc_type": doc_type,
            "total_fields": len(fields),
        }

    # ------------------------------------------------------------------
    # Batch metrics
    # ------------------------------------------------------------------

    def compute_metrics(self, check_results: List[Dict]) -> Dict[str, Any]:
        """
        Compute aggregate quality metrics across multiple check results.

        Args:
            check_results: List of dicts returned by ``check()``.

        Returns:
            Aggregate metrics dict.
        """
        if not check_results:
            return {}

        confs = [r.get("overall_confidence", 0.0) for r in check_results]
        grades = [r.get("quality_grade", "F") for r in check_results]
        total_anomalies = sum(len(r.get("anomalies", [])) for r in check_results)
        total_fields = sum(r.get("total_fields", 0) for r in check_results)
        valid_fields = sum(r.get("valid_field_count", 0) for r in check_results)

        grade_counts: Dict[str, int] = {}
        for g in grades:
            grade_counts[g] = grade_counts.get(g, 0) + 1

        return {
            "sample_count": len(check_results),
            "avg_confidence": round(sum(confs) / len(confs), 4),
            "min_confidence": round(min(confs), 4),
            "max_confidence": round(max(confs), 4),
            "total_fields_checked": total_fields,
            "valid_fields": valid_fields,
            "field_validity_rate": round(valid_fields / total_fields, 4) if total_fields else 0.0,
            "total_anomalies": total_anomalies,
            "grade_distribution": grade_counts,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _grade(confidence: float, invalid_count: int, total: int) -> str:
        if total == 0:
            return "F"
        error_rate = invalid_count / total
        if confidence >= 0.9 and error_rate == 0:
            return "A"
        if confidence >= 0.75 and error_rate <= 0.1:
            return "B"
        if confidence >= 0.6 and error_rate <= 0.25:
            return "C"
        if confidence >= 0.4:
            return "D"
        return "F"
