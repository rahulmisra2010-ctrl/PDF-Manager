"""
blueprints/validation.py — Field Validation Engine.

Validates extracted address-book fields for:
- Blank / missing values
- Format errors (email, phone, zip code)
- Low-confidence scores

Each issue is scored and categorised so the UI can display actionable
suggestions grouped by severity.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Field-format validators (regex-based)
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)
_PHONE_RE = re.compile(
    r"^[\d\s\-().+]{7,20}$"
)
_ZIP_RE = re.compile(
    r"^\d{5}(-\d{4})?$"
)
_STATE_RE = re.compile(
    r"^[A-Za-z]{2}$"
)

# Severity levels
SEVERITY_BLANK = "blank"
SEVERITY_FORMAT = "format"
SEVERITY_SUSPICIOUS = "suspicious"

# Score weights (higher = worse)
SCORE_BLANK = 10
SCORE_FORMAT = 5
SCORE_SUSPICIOUS = 3


def _validate_field(field_name: str, value: str, confidence: float) -> list[dict]:
    """Return a list of issue dicts for a single field value.

    Each issue dict has keys: ``field_name``, ``severity``, ``message``, ``score``.
    An empty list means the field passed all checks.
    """
    issues: list[dict] = []
    stripped = (value or "").strip()

    # ------------------------------------------------------------------
    # Blank check
    # ------------------------------------------------------------------
    if not stripped:
        issues.append({
            "field_name": field_name,
            "severity": SEVERITY_BLANK,
            "message": f"'{field_name}' is blank or missing.",
            "score": SCORE_BLANK,
        })
        return issues  # No further checks on blank values

    # ------------------------------------------------------------------
    # Format checks
    # ------------------------------------------------------------------
    if field_name == "Email":
        if not _EMAIL_RE.match(stripped):
            issues.append({
                "field_name": field_name,
                "severity": SEVERITY_FORMAT,
                "message": f"'{field_name}' does not look like a valid email address.",
                "score": SCORE_FORMAT,
            })
    elif field_name in ("Home Phone", "Cell Phone", "Work Phone"):
        digits = re.sub(r"\D", "", stripped)
        if len(digits) < 7 or not _PHONE_RE.match(stripped):
            issues.append({
                "field_name": field_name,
                "severity": SEVERITY_FORMAT,
                "message": f"'{field_name}' does not look like a valid phone number.",
                "score": SCORE_FORMAT,
            })
    elif field_name == "Zip Code":
        if not _ZIP_RE.match(stripped):
            issues.append({
                "field_name": field_name,
                "severity": SEVERITY_FORMAT,
                "message": f"'{field_name}' should be a 5-digit (or ZIP+4) code.",
                "score": SCORE_FORMAT,
            })
    elif field_name == "State":
        if not _STATE_RE.match(stripped):
            issues.append({
                "field_name": field_name,
                "severity": SEVERITY_FORMAT,
                "message": f"'{field_name}' should be a 2-letter state abbreviation.",
                "score": SCORE_FORMAT,
            })

    # ------------------------------------------------------------------
    # Low-confidence / suspicious check
    # ------------------------------------------------------------------
    if confidence < 0.65 and not issues:
        issues.append({
            "field_name": field_name,
            "severity": SEVERITY_SUSPICIOUS,
            "message": (
                f"'{field_name}' has a low confidence score ({confidence:.0%}) "
                "and may be incorrectly extracted."
            ),
            "score": SCORE_SUSPICIOUS,
        })

    return issues


def validate_fields(fields: list[dict[str, Any]]) -> dict:
    """Validate a list of field dicts and return a structured report.

    Args:
        fields: List of dicts with keys ``field_name``, ``value``,
                ``confidence`` (optional, defaults to 1.0).

    Returns:
        Dict with keys:

        * ``issues`` — list of issue dicts (field_name, severity, message, score)
        * ``total_score`` — sum of issue scores (0 = all OK)
        * ``fields_with_issues`` — set of field names that have issues
        * ``summary`` — human-readable summary string
    """
    all_issues: list[dict] = []

    for f in fields:
        field_name = f.get("field_name", "")
        value = f.get("value", "") or ""
        confidence = float(f.get("confidence", 1.0))
        all_issues.extend(_validate_field(field_name, value, confidence))

    total_score = sum(i["score"] for i in all_issues)
    fields_with_issues = {i["field_name"] for i in all_issues}

    if not all_issues:
        summary = "All fields passed validation."
    else:
        n = len(all_issues)
        summary = f"{n} issue(s) found across {len(fields_with_issues)} field(s)."

    return {
        "issues": all_issues,
        "total_score": total_score,
        "fields_with_issues": sorted(fields_with_issues),
        "summary": summary,
    }
