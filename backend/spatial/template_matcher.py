"""
backend/spatial/template_matcher.py — Layout template matching.

Compares the layout of a current document page against a library of
previously-seen templates (training samples) and returns similarity scores.

Templates are lightweight dicts that describe the positions of key fields
on a page; they are built from the output of LayoutAnalyzer and stored
in-memory (or serialised to JSON for persistence).
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


class TemplateMatcher:
    """
    Match a current document layout against stored templates.

    Usage::

        matcher = TemplateMatcher()

        # Register a training sample
        matcher.add_template("invoice_a", layout_dict, field_positions)

        # Match a new document page
        matches = matcher.match(current_layout, current_field_positions)
        # matches → list of {"template_id": ..., "similarity": ...} sorted desc
    """

    def __init__(self) -> None:
        # { template_id: {"layout": {...}, "field_positions": {...}} }
        self._templates: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Template management
    # ------------------------------------------------------------------

    def add_template(
        self,
        template_id: str,
        layout: dict,
        field_positions: dict[str, dict],
    ) -> None:
        """Register a training layout template.

        Parameters
        ----------
        template_id:
            Unique identifier (e.g. ``"invoice_a"``).
        layout:
            Output of :meth:`LayoutAnalyzer.analyze`.
        field_positions:
            Mapping ``{field_type: {"x": ..., "y": ...}}`` for known fields
            on this template (e.g. from manual annotation or training data).
        """
        self._templates[template_id] = {
            "layout": layout,
            "field_positions": field_positions,
        }

    def remove_template(self, template_id: str) -> bool:
        return bool(self._templates.pop(template_id, None))

    @property
    def template_ids(self) -> list[str]:
        return list(self._templates.keys())

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match(
        self,
        current_layout: dict,
        current_field_positions: dict[str, dict] | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Compare *current_layout* against all registered templates.

        Returns up to *top_k* matches sorted by similarity descending::

            [
              {"template_id": "invoice_a", "similarity": 0.92, "field_positions": {...}},
              ...
            ]
        """
        results = []
        for tid, tmpl in self._templates.items():
            sim = self._layout_similarity(current_layout, tmpl["layout"])
            results.append({
                "template_id": tid,
                "similarity": round(sim, 4),
                "field_positions": tmpl["field_positions"],
            })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def best_match(
        self,
        current_layout: dict,
        current_field_positions: dict[str, dict] | None = None,
    ) -> dict | None:
        """Return the single best matching template, or None."""
        matches = self.match(current_layout, current_field_positions, top_k=1)
        return matches[0] if matches else None

    def suggest_field_positions(
        self,
        position_x: float,
        position_y: float,
        page_width: float,
        page_height: float,
        top_k: int = 3,
    ) -> list[dict]:
        """
        Given a hover position, search all templates for nearby field positions
        and return the most likely field types.

        Returns::

            [{"field_type": "invoice_number", "confidence": 0.95, ...}, ...]
        """
        norm_x = position_x / page_width if page_width else 0
        norm_y = position_y / page_height if page_height else 0

        candidates = []
        for tid, tmpl in self._templates.items():
            for field_type, fpos in tmpl.get("field_positions", {}).items():
                fx = fpos.get("x", 0) / page_width if page_width else 0
                fy = fpos.get("y", 0) / page_height if page_height else 0
                dist = math.sqrt((norm_x - fx) ** 2 + (norm_y - fy) ** 2)
                # Convert distance to a similarity score (max dist on unit square ≈ 1.41)
                similarity = max(0.0, 1.0 - dist / 0.3)
                candidates.append({
                    "field_type": field_type,
                    "template_id": tid,
                    "similarity": round(similarity, 4),
                    "template_field_position": fpos,
                    "distance_norm": round(dist, 4),
                })

        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        return candidates[:top_k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _layout_similarity(layout_a: dict, layout_b: dict) -> float:
        """
        Compute a rough similarity score [0, 1] between two layout dicts.

        Compares:
          - Number of columns (weighted 0.2)
          - Number of rows    (weighted 0.2)
          - Label-value pair labels overlap (weighted 0.6)
        """
        score = 0.0

        # Column count similarity
        cols_a = len(layout_a.get("columns", []))
        cols_b = len(layout_b.get("columns", []))
        if cols_a > 0 and cols_b > 0:
            score += 0.2 * (1.0 - abs(cols_a - cols_b) / max(cols_a, cols_b))
        elif cols_a == cols_b:  # both 0
            score += 0.2

        # Row count similarity
        rows_a = len(layout_a.get("rows", []))
        rows_b = len(layout_b.get("rows", []))
        if rows_a > 0 and rows_b > 0:
            score += 0.2 * (1.0 - abs(rows_a - rows_b) / max(rows_a, rows_b))
        elif rows_a == rows_b:
            score += 0.2

        # Label overlap
        labels_a = {p["label"].lower() for p in layout_a.get("label_value_pairs", [])}
        labels_b = {p["label"].lower() for p in layout_b.get("label_value_pairs", [])}
        if labels_a or labels_b:
            overlap = len(labels_a & labels_b)
            union = len(labels_a | labels_b)
            score += 0.6 * (overlap / union if union else 0)
        else:
            score += 0.6  # both empty — treat as similar

        return score
