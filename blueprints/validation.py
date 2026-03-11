"""
blueprints/validation.py — Field Validation Engine for PDF-Manager.

Provides a Flask blueprint with a POST route to detect blank, wrongly
formatted, and low-confidence fields, plus a reusable helper function
``validate_fields_data`` that the address-book-live pipeline uses directly.

Routes
------
POST /validate-fields/<doc_id>  — validate extracted fields for a document

Helper functions
----------------
validate_fields_data(fields)         — validate a list of field dicts
check_field_format(field_name, val)  — check format for a known field type
"""

import re

from flask import Blueprint, jsonify, request
from flask_login import login_required

from models import Document, ExtractedField

validation_bp = Blueprint("validation", __name__)

# ---------------------------------------------------------------------------
# Confidence thresholds (consistent with existing codebase constants)
# ---------------------------------------------------------------------------
CONFIDENCE_HIGH = 0.85
CONFIDENCE_MED = 0.65

# ---------------------------------------------------------------------------
# Per-field format validators
# ---------------------------------------------------------------------------
_FIELD_VALIDATORS: dict = {
    "Email": {
        "pattern": r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$",
        "message": "Invalid email format",
    },
    "Home Phone": {
        "pattern": r"^[\+\d\s\-\(\)\.]{7,20}$",
        "message": "Invalid phone number (expected 7–20 digits/symbols)",
    },
    "Cell Phone": {
        "pattern": r"^[\+\d\s\-\(\)\.]{7,20}$",
        "message": "Invalid phone number (expected 7–20 digits/symbols)",
    },
    "Work Phone": {
        "pattern": r"^[\+\d\s\-\(\)\.]{7,20}$",
        "message": "Invalid phone number (expected 7–20 digits/symbols)",
    },
    "Zip Code": {
        "pattern": r"^\d{5}(-\d{4})?$",
        "message": "Invalid zip code (expected 5 or 9 digits)",
    },
    "State": {
        "pattern": r"^[A-Za-z]{2}$",
        "message": "State should be a 2-letter abbreviation (e.g. CA)",
    },
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def check_field_format(field_name: str, value: str) -> dict | None:
    """Check whether *value* conforms to the expected format for *field_name*.

    Returns ``None`` when the value is valid (or no validator exists for this
    field).  Returns a dict ``{"issue": "invalid_format", "message": "..."}``
    when the value fails validation.
    """
    if not value:
        return None  # blank is handled separately

    validator = _FIELD_VALIDATORS.get(field_name)
    if not validator:
        return None

    if not re.match(validator["pattern"], value.strip()):
        return {"issue": "invalid_format", "message": validator["message"]}

    return None


def validate_fields_data(fields: list) -> dict:
    """Validate a list of field dicts and return a structured result.

    Each entry in *fields* should be a dict with at least:
        ``field_id``, ``field_name``, ``value``, ``confidence`` (optional).

    Returns::

        {
            "issues": [
                {
                    "field_id": ..., "field_name": ..., "value": ...,
                    "issue_type": "blank"|"invalid_format"|"low_confidence",
                    "message": ...,
                    "severity": "error"|"warning"
                },
                ...
            ],
            "fields": {
                "<field_name>": {
                    "field_id": ..., "value": ..., "confidence": ...,
                    "status": "ok"|"blank"|"invalid"|"suspicious"
                },
                ...
            },
            "blank_fields": ["Name", "Phone", ...],
            "total": <int>,
            "issues_count": <int>,
        }
    """
    issues: list = []
    field_statuses: dict = {}
    blank_fields: list = []

    for field in fields:
        field_name = field.get("field_name", "")
        value = (field.get("value") or "").strip()
        confidence = float(field.get("confidence", 1.0))
        field_id = field.get("field_id") or field.get("id")

        status = "ok"

        if not value:
            issues.append({
                "field_id": field_id,
                "field_name": field_name,
                "value": value,
                "issue_type": "blank",
                "message": f"'{field_name}' is blank",
                "severity": "warning",
            })
            blank_fields.append(field_name)
            status = "blank"
        else:
            # Format validation
            fmt_error = check_field_format(field_name, value)
            if fmt_error:
                issues.append({
                    "field_id": field_id,
                    "field_name": field_name,
                    "value": value,
                    "issue_type": "invalid_format",
                    "message": fmt_error["message"],
                    "severity": "error",
                })
                status = "invalid"

            # Confidence check
            if confidence < CONFIDENCE_MED:
                issues.append({
                    "field_id": field_id,
                    "field_name": field_name,
                    "value": value,
                    "issue_type": "low_confidence",
                    "message": f"Low confidence score ({confidence:.0%}) — review recommended",
                    "severity": "warning",
                })
                if status == "ok":
                    status = "suspicious"

        field_statuses[field_name] = {
            "field_id": field_id,
            "value": value,
            "confidence": confidence,
            "status": status,
        }

    return {
        "issues": issues,
        "fields": field_statuses,
        "blank_fields": blank_fields,
        "total": len(fields),
        "issues_count": len(issues),
    }


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@validation_bp.route("/validate-fields/<int:doc_id>", methods=["POST"])
@login_required
def validate_fields(doc_id: int):
    """Validate extracted fields for a document.

    Accepts an optional JSON body with a ``fields`` list; if omitted, fields
    are loaded from the database for *doc_id*.

    Returns::

        {
            "status": "success",
            "issues": [...],
            "fields": {...},
            "blank_fields": [...],
            "total": <int>,
            "issues_count": <int>
        }
    """
    Document.query.get_or_404(doc_id)
    data = request.get_json(silent=True) or {}

    fields = data.get("fields")
    if not fields:
        db_fields = ExtractedField.query.filter_by(document_id=doc_id).all()
        fields = [
            {
                "field_id": f.id,
                "field_name": f.field_name,
                "value": f.value or "",
                "confidence": f.confidence,
            }
            for f in db_fields
        ]

    result = validate_fields_data(fields)
    return jsonify({"status": "success", **result})
