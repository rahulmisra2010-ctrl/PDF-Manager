"""
backend/spatial/label_detector.py — Label detection and association.

Identifies which words are labels (field names) and which are values,
then builds a mapping: label → value with confidence scores.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Common label keywords (lowercase, without trailing colon)
_KNOWN_LABELS: frozenset[str] = frozenset({
    "invoice", "invoice #", "invoice no", "invoice number",
    "date", "invoice date", "due date", "payment date",
    "amount", "total", "total due", "balance due", "subtotal",
    "tax", "discount",
    "vendor", "supplier", "customer", "client",
    "name", "company",
    "address", "street", "city", "state", "zip", "zip code", "country",
    "phone", "tel", "telephone", "fax",
    "email", "e-mail",
    "po #", "po number", "purchase order",
    "description", "item", "quantity", "qty", "unit price", "price",
    "bill to", "ship to", "sold to",
    "from", "to", "re",
    "account", "account #", "reference", "ref",
    "payment method", "terms", "currency",
})

_ENDS_COLON = re.compile(r".+:$")


class LabelDetector:
    """
    Identify labels in a word list and associate each label with its value.

    Usage::

        detector = LabelDetector()
        result = detector.detect(words)
        # result → {"labels": [...], "values": [...], "pairs": [...]}
    """

    # Maximum horizontal gap between a label right-edge and a value left-edge
    MAX_LABEL_VALUE_DISTANCE: float = 300.0

    # Maximum vertical offset to consider two words on the "same row"
    SAME_ROW_TOLERANCE: float = 10.0

    def detect(self, words: list[dict]) -> dict:
        """
        Classify every word as label / value / other and build label-value pairs.

        Parameters
        ----------
        words:
            Either raw word dicts (x, y, width, height, text) or enriched
            SpatialOCREngine output (position.x, position.y, …).
        """
        flat = self._flatten(words)

        labels = []
        values = []
        pairs = []
        value_used: set[int] = set()

        for i, w in enumerate(flat):
            if self._is_label(w["text"]):
                labels.append({
                    "text": w["text"].rstrip(":"),
                    "x": w["x"],
                    "y": w["y"],
                    "width": w["width"],
                    "height": w["height"],
                    "word_index": i,
                })

        for i, w in enumerate(flat):
            if not self._is_label(w["text"]):
                values.append({
                    "text": w["text"],
                    "x": w["x"],
                    "y": w["y"],
                    "width": w["width"],
                    "height": w["height"],
                    "word_index": i,
                })

        # Associate each label with the nearest value to its right on the same row
        for label in labels:
            best_value = None
            best_dist = float("inf")
            best_val_idx = -1

            label_right_edge = label["x"] + label["width"]

            for vi, val in enumerate(values):
                if vi in value_used:
                    continue
                if abs(val["y"] - label["y"]) > self.SAME_ROW_TOLERANCE:
                    continue
                gap = val["x"] - label_right_edge
                if 0 <= gap <= self.MAX_LABEL_VALUE_DISTANCE and gap < best_dist:
                    best_dist = gap
                    best_value = val
                    best_val_idx = vi

            if best_value is not None:
                value_used.add(best_val_idx)
                confidence = round(
                    max(0.5, 1.0 - best_dist / self.MAX_LABEL_VALUE_DISTANCE), 3
                )
                pairs.append({
                    "label": label["text"].rstrip(":"),
                    "label_position": {"x": label["x"], "y": label["y"]},
                    "value": best_value["text"],
                    "value_position": {"x": best_value["x"], "y": best_value["y"]},
                    "distance_px": round(best_dist, 2),
                    "confidence": confidence,
                })

        return {
            "labels": labels,
            "values": values,
            "pairs": pairs,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_label(text: str) -> bool:
        """Heuristic label classifier."""
        stripped = text.strip()
        # Ends with a colon → very likely a label
        if _ENDS_COLON.match(stripped):
            return True
        # Known label keyword
        key = stripped.lower().rstrip(":").strip()
        if key in _KNOWN_LABELS:
            return True
        # Short (≤ 3 words) and all title-case or upper-case → possible label
        words = stripped.split()
        if 1 <= len(words) <= 3 and all(w[0].isupper() for w in words if w):
            # Only if it looks like a field name (no numbers or special chars)
            if re.fullmatch(r"[A-Za-z #]+", stripped.replace(":", "")):
                return True
        return False

    @staticmethod
    def _flatten(words: list[dict]) -> list[dict]:
        """Accept enriched SpatialOCREngine output or plain word dicts."""
        flat = []
        for w in words:
            if "position" in w:
                pos = w["position"]
                flat.append({
                    "text": w.get("text", ""),
                    "x": pos.get("x", 0),
                    "y": pos.get("y", 0),
                    "width": pos.get("width", 0),
                    "height": pos.get("height", 0),
                })
            else:
                flat.append({
                    "text": w.get("text", ""),
                    "x": w.get("x", 0),
                    "y": w.get("y", 0),
                    "width": w.get("width", 0),
                    "height": w.get("height", 0),
                })
        return flat
