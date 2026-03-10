"""
training_service.py — Training data management for RAG confidence boosting.

Provides utilities for loading labeled training examples from the database
and using them to boost confidence scores during RAG field extraction.
"""

from __future__ import annotations

import difflib
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# String similarity
# ---------------------------------------------------------------------------

def _string_similarity(a: str, b: str) -> float:
    """Return a similarity ratio in [0.0, 1.0] between two strings.

    Uses ``difflib.SequenceMatcher`` with case-insensitive comparison.
    """
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# TrainingService
# ---------------------------------------------------------------------------

class TrainingService:
    """Manages training examples and computes confidence boosts.

    This service is intentionally kept free of Flask imports so it can be
    unit-tested without an application context.  Callers are responsible for
    passing training examples retrieved from the database.
    """

    # Similarity threshold above which an extracted value is considered
    # consistent with a training example → confidence boost applied.
    HIGH_SIMILARITY_THRESHOLD = 0.80

    # Minimum confidence boost applied when an extracted value closely matches
    # a training example.
    CONFIDENCE_BOOST = 0.10

    # Confidence level assigned when an empty extracted value is replaced by
    # a training example value.
    FALLBACK_CONFIDENCE = 0.75

    # ---------------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------------

    def boost_confidence(
        self,
        field_name: str,
        extracted_value: str,
        training_examples: list[dict[str, Any]],
    ) -> tuple[str, float, bool]:
        """Apply training data to improve an extracted field value.

        Args:
            field_name:         The name of the field being extracted.
            extracted_value:    The value produced by the RAG pipeline.
            training_examples:  A list of dicts with ``field_name`` and
                                ``correct_value`` keys (as returned by
                                ``TrainingExample.to_dict()``).

        Returns:
            A 3-tuple ``(value, confidence_delta, used_training)`` where:

            * ``value`` — the (possibly updated) field value
            * ``confidence_delta`` — amount to add to the base confidence
              (may be negative if not used)
            * ``used_training`` — ``True`` if training data influenced the
              result
        """
        relevant = [
            ex["correct_value"]
            for ex in training_examples
            if ex["field_name"] == field_name and ex.get("correct_value")
        ]

        if not relevant:
            return extracted_value, 0.0, False

        # When the extracted value is blank, use the first training example
        # directly (no similarity comparison possible against empty string).
        if not (extracted_value or "").strip():
            return relevant[0], self.FALLBACK_CONFIDENCE, True

        best_match, best_score = self._best_match(extracted_value, relevant)

        if best_score >= self.HIGH_SIMILARITY_THRESHOLD:
            # Extracted value is consistent with training → boost confidence
            return extracted_value, self.CONFIDENCE_BOOST, True

        return extracted_value, 0.0, False

    def apply_training_to_results(
        self,
        rag_results: list[dict[str, Any]],
        training_examples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Apply training examples to a list of RAG extraction results.

        Each result dict is expected to have ``field_name``, ``field_value``,
        and ``confidence`` keys (as produced by
        :meth:`RAGService.extract_fields`).

        Returns the same list with ``confidence`` values updated in-place.
        """
        if not training_examples:
            return rag_results

        for item in rag_results:
            value, delta, used = self.boost_confidence(
                item["field_name"],
                item.get("field_value", "") or "",
                training_examples,
            )
            if used:
                item["field_value"] = value
                if delta > 0:
                    item["confidence"] = round(
                        min(1.0, item["confidence"] + delta), 4
                    )
                elif item["confidence"] == 0.0:
                    item["confidence"] = round(delta, 4)
                item["training_boosted"] = True

        return rag_results

    # ---------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def _best_match(
        target: str, candidates: list[str]
    ) -> tuple[str | None, float]:
        """Return the candidate with the highest similarity to *target*."""
        best_candidate: str | None = None
        best_score = 0.0
        for candidate in candidates:
            score = _string_similarity(target, candidate)
            if score > best_score:
                best_score = score
                best_candidate = candidate
        return best_candidate, best_score
