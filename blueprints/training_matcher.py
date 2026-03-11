"""
blueprints/training_matcher.py — Training Data Matcher for PDF-Manager.

Provides the ``find_best_matches`` helper function that queries
``TrainingExample`` and ``FieldCorrection`` records to surface the most
likely values for blank or suspicious fields.

Usage::

    from blueprints.training_matcher import find_best_matches

    suggestions = find_best_matches(doc_id=5, blank_fields=["Name", "Email"])
    # {"Name": [{"value": "John Smith", "confidence": 0.95, ...}], ...}
"""

from models import FieldCorrection, TrainingExample, db


def _score_confidence(count: int, base: float, ceiling: float) -> float:
    """Compute a confidence score that scales from *base* (rare) toward *ceiling* (frequent)."""
    return round(min(ceiling, base + (count / max(count + 5, 1)) * (ceiling - base)), 2)


def find_best_matches(doc_id: int, blank_fields: list, top_n: int = 3) -> dict:
    """Find best-fit values from training data for blank or suspicious fields.

    Queries ``TrainingExample`` (primary) and ``FieldCorrection`` (secondary)
    records, scoring suggestions by frequency of use.  Returns the top *top_n*
    suggestions for each field name.

    Args:
        doc_id:       Document ID (reserved for future context-aware filtering).
        blank_fields: List of field names that need suggestions.
        top_n:        Maximum number of suggestions to return per field (default 3).

    Returns::

        {
            "Name": [
                {"value": "John Smith", "confidence": 0.95, "source": "training", "count": 12},
                {"value": "Jane Doe",   "confidence": 0.82, "source": "training", "count": 5},
            ],
            "Email": [
                {"value": "john@company.com", "confidence": 0.98, "source": "correction", "count": 3},
            ],
            ...
        }

    Fields with no suggestions are omitted from the returned dict.
    """
    suggestions: dict = {}

    if not blank_fields:
        return suggestions

    for field_name in blank_fields:
        field_suggestions: list = []
        seen_values: set = set()

        # ------------------------------------------------------------------
        # 1. TrainingExample records (highest-quality source)
        # ------------------------------------------------------------------
        training_rows = (
            db.session.query(
                db.func.coalesce(
                    TrainingExample.field_value,
                    TrainingExample.correct_value,
                ).label("val"),
                db.func.count(
                    db.func.coalesce(
                        TrainingExample.field_value,
                        TrainingExample.correct_value,
                    )
                ).label("cnt"),
            )
            .filter(
                TrainingExample.field_name == field_name,
                db.func.coalesce(
                    TrainingExample.field_value,
                    TrainingExample.correct_value,
                ).isnot(None),
                db.func.coalesce(
                    TrainingExample.field_value,
                    TrainingExample.correct_value,
                ) != "",
            )
            .group_by(
                db.func.coalesce(
                    TrainingExample.field_value,
                    TrainingExample.correct_value,
                )
            )
            .order_by(db.desc("cnt"))
            .limit(top_n * 2)
            .all()
        )

        for row in training_rows:
            if len(field_suggestions) >= top_n:
                break
            val = row.val
            if val and val not in seen_values:
                seen_values.add(val)
                field_suggestions.append({
                    "value": val,
                    "confidence": _score_confidence(row.cnt, base=0.70, ceiling=0.99),
                    "source": "training",
                    "count": row.cnt,
                })

        # ------------------------------------------------------------------
        # 2. FieldCorrection records (secondary source — from Train Me runs)
        # ------------------------------------------------------------------
        if len(field_suggestions) < top_n:
            correction_rows = (
                db.session.query(
                    FieldCorrection.corrected_value.label("val"),
                    db.func.count(FieldCorrection.corrected_value).label("cnt"),
                )
                .filter(
                    FieldCorrection.field_name == field_name,
                    FieldCorrection.corrected_value.isnot(None),
                    FieldCorrection.corrected_value != "",
                )
                .group_by(FieldCorrection.corrected_value)
                .order_by(db.desc("cnt"))
                .limit(top_n * 2)
                .all()
            )

            for row in correction_rows:
                if len(field_suggestions) >= top_n:
                    break
                val = row.val
                if val and val not in seen_values:
                    seen_values.add(val)
                    # Slightly lower ceiling than training examples
                    field_suggestions.append({
                        "value": val,
                        "confidence": _score_confidence(row.cnt, base=0.60, ceiling=0.89),
                        "source": "correction",
                        "count": row.cnt,
                    })

        if field_suggestions:
            suggestions[field_name] = field_suggestions

    return suggestions
