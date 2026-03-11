"""
blueprints/training_matcher.py — Training Data Matcher.

Queries ``FieldCorrection`` and ``TrainingExample`` records to find the
best-fit values for each address-book field.  Returns up to 3 suggestions
per field, each with a confidence score and source label.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Scoring weights
_FREQ_WEIGHT = 0.6
_RECENCY_WEIGHT = 0.3
_FIELD_TYPE_BONUS = 0.1

# Maximum number of suggestions to return per field
MAX_SUGGESTIONS = 3

# Recency half-life in days: older records decay their score
_HALF_LIFE_DAYS = 30.0


def _recency_score(created_at: datetime | None) -> float:
    """Return a 0-1 score based on how recently the record was created."""
    if created_at is None:
        return 0.5
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    # Exponential decay
    import math
    return math.exp(-age_days / _HALF_LIFE_DAYS)


def _field_type_bonus(field_name: str) -> float:
    """Return a small bonus for fields with strict formats (email, phone, etc.)."""
    bonus_fields = {"Email", "Home Phone", "Cell Phone", "Work Phone", "Zip Code"}
    return _FIELD_TYPE_BONUS if field_name in bonus_fields else 0.0


def find_suggestions(
    fields: list[dict[str, Any]],
    *,
    session: Any,
    correction_model: Any,
    training_model: Any,
    max_per_field: int = MAX_SUGGESTIONS,
) -> dict[str, list[dict]]:
    """Return ranked suggestions for each field in *fields*.

    Args:
        fields: List of dicts with at least ``field_name`` key.
        session: SQLAlchemy session.
        correction_model: ``FieldCorrection`` model class.
        training_model: ``TrainingExample`` model class.
        max_per_field: Maximum suggestions to return per field.

    Returns:
        Dict mapping ``field_name`` → list of suggestion dicts, each with:

        * ``value``      — suggested string value
        * ``confidence`` — float 0-1 confidence score
        * ``source``     — ``"correction"`` or ``"training"``
        * ``frequency``  — how many times this value appeared
    """
    import math

    field_names = [f["field_name"] for f in fields]

    # ------------------------------------------------------------------
    # Collect all candidates from FieldCorrection
    # ------------------------------------------------------------------
    correction_rows = (
        session.query(
            correction_model.field_name,
            correction_model.corrected_value,
            correction_model.created_at,
        )
        .filter(
            correction_model.field_name.in_(field_names),
            correction_model.corrected_value.isnot(None),
            correction_model.corrected_value != "",
        )
        .all()
    )

    # Build aggregated map: field_name → {value: {freq, latest_date}}
    correction_agg: dict[str, dict[str, dict]] = {}
    for row in correction_rows:
        fn = row.field_name
        val = row.corrected_value
        entry = correction_agg.setdefault(fn, {}).setdefault(val, {"freq": 0, "date": None})
        entry["freq"] += 1
        created = getattr(row, "created_at", None)
        if created and (entry["date"] is None or created > entry["date"]):
            entry["date"] = created

    # ------------------------------------------------------------------
    # Collect all candidates from TrainingExample
    # ------------------------------------------------------------------
    import sqlalchemy as sa  # type: ignore[import]

    val_col = sa.func.coalesce(
        training_model.field_value, training_model.correct_value
    )

    training_rows = (
        session.query(
            training_model.field_name,
            val_col.label("val"),
            training_model.created_at,
        )
        .filter(
            training_model.field_name.in_(field_names),
            val_col.isnot(None),
            val_col != "",
        )
        .all()
    )

    training_agg: dict[str, dict[str, dict]] = {}
    for row in training_rows:
        fn = row.field_name
        val = row.val
        if not val:
            continue
        entry = training_agg.setdefault(fn, {}).setdefault(val, {"freq": 0, "date": None})
        entry["freq"] += 1
        created = getattr(row, "created_at", None)
        if created and (entry["date"] is None or created > entry["date"]):
            entry["date"] = created

    # ------------------------------------------------------------------
    # Build and rank suggestions per field
    # ------------------------------------------------------------------
    suggestions: dict[str, list[dict]] = {}

    for field_name in field_names:
        candidates: dict[str, dict] = {}

        # Merge corrections
        for val, data in correction_agg.get(field_name, {}).items():
            candidates[val] = {
                "value": val,
                "freq": data["freq"],
                "date": data["date"],
                "source": "correction",
            }

        # Merge training (don't override corrections)
        for val, data in training_agg.get(field_name, {}).items():
            if val not in candidates:
                candidates[val] = {
                    "value": val,
                    "freq": data["freq"],
                    "date": data["date"],
                    "source": "training",
                }
            else:
                # Boost frequency if value exists in both sources
                candidates[val]["freq"] += data["freq"]

        if not candidates:
            suggestions[field_name] = []
            continue

        # Compute scores
        max_freq = max(c["freq"] for c in candidates.values()) or 1
        bonus = _field_type_bonus(field_name)
        scored = []
        for val, c in candidates.items():
            freq_score = (c["freq"] / max_freq) * _FREQ_WEIGHT
            rec_score = _recency_score(c["date"]) * _RECENCY_WEIGHT
            confidence = min(1.0, freq_score + rec_score + bonus)
            scored.append({
                "value": val,
                "confidence": round(confidence, 3),
                "source": c["source"],
                "frequency": c["freq"],
            })

        scored.sort(key=lambda x: x["confidence"], reverse=True)
        suggestions[field_name] = scored[:max_per_field]

    return suggestions
