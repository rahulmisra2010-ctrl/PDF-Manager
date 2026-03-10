"""
backend/services/validation_service.py — Train Me validation service.

Compares extracted address book fields against a reference/golden dataset and
produces a structured validation result suitable for the Train Me endpoint.

Public API
----------
* load_reference_data(reference_set)  → dict[field_name, value]
* compare_field(extracted, reference) → (status_label, score)
* validate_document(doc_id, fields, reference_set) → dict
"""

from __future__ import annotations

import difflib
import json
import os
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Reference data loader
# ---------------------------------------------------------------------------

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_REFERENCE_FILE = os.path.join(_DATA_DIR, "reference_fields.json")

# Status labels
STATUS_VALIDATED = "\u2713 validated"          # ✓ validated
STATUS_NEEDS_REVIEW = "\u26a0 needs review"    # ⚠ needs review
STATUS_NEEDS_CORRECTION = "\u2717 needs correction"  # ✗ needs correction
STATUS_BLANK = "\u26a0 blank"                  # ⚠ blank

# Match score thresholds
THRESHOLD_EXACT = 1.0
THRESHOLD_PARTIAL = 0.80


def load_reference_data(reference_set: str) -> dict[str, str]:
    """Load the golden/reference values for *reference_set*.

    Args:
        reference_set: Key in ``reference_fields.json`` (e.g. "mat_pdf_v1").

    Returns:
        Mapping of field_name → reference value string.

    Raises:
        ValueError: If the reference set is not found.
        FileNotFoundError: If the reference file is missing.
    """
    with open(_REFERENCE_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    sets = data.get("reference_sets", {})
    if reference_set not in sets:
        available = list(sets.keys())
        raise ValueError(
            f"Reference set {reference_set!r} not found. "
            f"Available sets: {available}"
        )

    return dict(sets[reference_set].get("fields", {}))


def compare_field(extracted: str, reference: str) -> tuple[str, float]:
    """Compare an extracted value against the reference value.

    Uses exact comparison first, then character-level sequence matching for
    fuzzy comparison (handles OCR errors, minor punctuation differences, etc.).

    Args:
        extracted: The value extracted from the document (may be empty).
        reference: The golden/reference value (may be empty).

    Returns:
        A ``(status_label, match_score)`` tuple where *match_score* is in
        the range ``[0.0, 1.0]``.
    """
    # Normalise: strip whitespace, work with strings
    ext = (extracted or "").strip()
    ref = (reference or "").strip()

    # Both blank → the reference expectation is blank, so it matches
    if not ext and not ref:
        return STATUS_VALIDATED, 1.0

    # Extracted is blank but reference has a value → blank field
    if not ext and ref:
        return STATUS_BLANK, 0.0

    # Exact match (case-insensitive)
    if ext.lower() == ref.lower():
        return STATUS_VALIDATED, 1.0

    # Fuzzy match using SequenceMatcher
    ratio = difflib.SequenceMatcher(None, ext.lower(), ref.lower()).ratio()

    if ratio >= THRESHOLD_PARTIAL:
        return STATUS_NEEDS_REVIEW, round(ratio, 4)

    return STATUS_NEEDS_CORRECTION, round(ratio, 4)


def validate_document(
    doc_id: int,
    fields: list[dict[str, Any]],
    reference_set: str = "mat_pdf_v1",
) -> dict[str, Any]:
    """Validate extracted fields for *doc_id* against *reference_set*.

    Args:
        doc_id: Database ID of the document (used for metadata only).
        fields: List of ``{"field_id": int, "field_name": str, "value": str}``
                dicts, typically from the request body.
        reference_set: Key identifying which reference dataset to use.

    Returns:
        A dict with keys: ``status``, ``timestamp``, ``results``, and
        ``validation_metadata``.
    """
    reference = load_reference_data(reference_set)

    results = []
    validated_count = 0
    needs_correction_count = 0
    blank_count = 0

    for position, field_entry in enumerate(fields, start=1):
        field_name = field_entry.get("field_name", "")
        extracted_value = field_entry.get("value", "") or ""
        field_id = field_entry.get("field_id")

        ref_value = reference.get(field_name, "")
        status, score = compare_field(extracted_value, ref_value)

        corrected = False
        corrected_to = None

        if status == STATUS_VALIDATED:
            validated_count += 1
        elif status == STATUS_BLANK:
            blank_count += 1
            if ref_value:
                # Auto-fill: the corrected value is the reference
                corrected = True
                corrected_to = ref_value
        else:
            # needs_review or needs_correction
            needs_correction_count += 1
            if ref_value and ref_value != extracted_value:
                corrected = True
                corrected_to = ref_value

        result_entry: dict[str, Any] = {
            "field_id": field_id,
            "field_name": field_name,
            "extracted_value": extracted_value,
            "reference_value": ref_value,
            "status": status,
            "match_score": score,
            "position": position,
            "corrected": corrected,
        }
        if corrected:
            result_entry["corrected_to"] = corrected_to

        results.append(result_entry)

    total = len(fields)
    accuracy = round(validated_count / total, 4) if total else 0.0

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "status": "validation_complete",
        "timestamp": timestamp,
        "results": results,
        "validation_metadata": {
            "total_fields": total,
            "validated": validated_count,
            "needs_correction": needs_correction_count,
            "blank_fields": blank_count,
            "accuracy": accuracy,
            "reference_set": reference_set,
        },
    }
