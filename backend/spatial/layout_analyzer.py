"""
backend/spatial/layout_analyzer.py — Form layout analysis.

Detects:
  - Page zones  (header / body / footer)
  - Columns     (vertical clusters of x-positions)
  - Rows        (horizontal clusters of y-positions)
  - Label-value pairs (proximity-based matching)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LayoutAnalyzer:
    """
    Analyse the spatial layout of words extracted from a PDF page.

    Usage::

        analyzer = LayoutAnalyzer()
        layout = analyzer.analyze(words, page_width=595, page_height=842)
    """

    # Threshold for clustering y-coordinates into "rows"
    ROW_CLUSTER_THRESHOLD = 8  # pixels

    # Threshold for clustering x-coordinates into "columns"
    COL_CLUSTER_THRESHOLD = 30  # pixels

    # Maximum horizontal distance between label and value
    LABEL_VALUE_MAX_DIST = 250  # pixels

    def analyze(
        self,
        words: list[dict],
        page_width: float,
        page_height: float,
    ) -> dict:
        """
        Return a full layout analysis dict.

        Parameters
        ----------
        words:
            List of word dicts as returned by :class:`SpatialOCREngine`.
            Each dict must have at least ``x``, ``y``, ``width``, ``height``,
            ``text`` keys (or nested under ``position``).
        page_width, page_height:
            Page dimensions in PDF user units (points).
        """
        flat = self._flatten(words)

        zones = self.detect_zones(page_height)
        columns = self.detect_columns(flat, page_width)
        rows = self.detect_rows(flat)
        label_value_pairs = self.find_label_value_pairs(flat)

        # Assign column/row index to each word
        word_layout = []
        for w in flat:
            col_idx = self._assign_column(w["x"], columns)
            row_idx = self._assign_row(w["y"], rows)
            zone = "body"
            if w["y"] < page_height * 0.15:
                zone = "header"
            elif w["y"] > page_height * 0.85:
                zone = "footer"
            word_layout.append({
                "text": w["text"],
                "x": w["x"],
                "y": w["y"],
                "width": w["width"],
                "height": w["height"],
                "zone": zone,
                "column_index": col_idx,
                "row_index": row_idx,
            })

        return {
            "zones": zones,
            "columns": columns,
            "rows": rows,
            "label_value_pairs": label_value_pairs,
            "word_layout": word_layout,
            "page_width": page_width,
            "page_height": page_height,
        }

    # ------------------------------------------------------------------
    # Zone detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_zones(page_height: float) -> dict:
        """Divide the page into header / body / footer zones."""
        return {
            "header": {"y_start": 0, "y_end": round(page_height * 0.15, 2)},
            "body":   {"y_start": round(page_height * 0.15, 2), "y_end": round(page_height * 0.85, 2)},
            "footer": {"y_start": round(page_height * 0.85, 2), "y_end": round(page_height, 2)},
        }

    # ------------------------------------------------------------------
    # Column detection
    # ------------------------------------------------------------------

    def detect_columns(self, flat_words: list[dict], page_width: float) -> list[dict]:
        """Cluster words into vertical column groups by x-position."""
        if not flat_words:
            return []

        # Use word left-edge x values
        xs = sorted(set(w["x"] for w in flat_words))

        # Simple greedy cluster: merge adjacent xs that are within threshold
        clusters: list[list[float]] = []
        current: list[float] = [xs[0]]
        for x in xs[1:]:
            if x - current[-1] <= self.COL_CLUSTER_THRESHOLD:
                current.append(x)
            else:
                clusters.append(current)
                current = [x]
        clusters.append(current)

        columns = []
        for i, cluster in enumerate(clusters):
            x_min = min(cluster)
            x_max = max(cluster)
            # Extend to next cluster or page edge
            if i + 1 < len(clusters):
                x_end = min(clusters[i + 1]) - 1
            else:
                x_end = page_width
            columns.append({
                "index": i + 1,
                "x_start": round(x_min, 2),
                "x_end": round(x_end, 2),
                "word_count": sum(
                    1 for w in flat_words
                    if x_min - self.COL_CLUSTER_THRESHOLD <= w["x"] <= x_max + self.COL_CLUSTER_THRESHOLD
                ),
            })

        return columns

    # ------------------------------------------------------------------
    # Row detection
    # ------------------------------------------------------------------

    def detect_rows(self, flat_words: list[dict]) -> list[dict]:
        """Cluster words into horizontal row groups by y-position."""
        if not flat_words:
            return []

        ys = sorted(set(round(w["y"], 1) for w in flat_words))

        clusters: list[list[float]] = []
        current: list[float] = [ys[0]]
        for y in ys[1:]:
            if y - current[-1] <= self.ROW_CLUSTER_THRESHOLD:
                current.append(y)
            else:
                clusters.append(current)
                current = [y]
        clusters.append(current)

        rows = []
        for i, cluster in enumerate(clusters):
            y_min = min(cluster)
            y_max = max(cluster)
            if i + 1 < len(clusters):
                y_end = min(clusters[i + 1]) - 1
            else:
                y_end = y_max + 20  # estimate
            rows.append({
                "index": i + 1,
                "y_start": round(y_min, 2),
                "y_end": round(y_end, 2),
                "word_count": sum(
                    1 for w in flat_words
                    if y_min - self.ROW_CLUSTER_THRESHOLD <= w["y"] <= y_max + self.ROW_CLUSTER_THRESHOLD
                ),
            })

        return rows

    # ------------------------------------------------------------------
    # Label-value pair detection
    # ------------------------------------------------------------------

    def find_label_value_pairs(self, flat_words: list[dict]) -> list[dict]:
        """
        Match potential label words to value words on the same row.

        Heuristic: a word ending in ':' or matching a known label pattern,
        followed by another word to the right within LABEL_VALUE_MAX_DIST
        pixels and within ±8 pixels vertical alignment.
        """
        pairs = []
        used_as_value: set[int] = set()

        for i, label_w in enumerate(flat_words):
            text = label_w["text"].strip()
            if not self._is_likely_label(text):
                continue

            # Search for the nearest value to the right on the same row
            best_value = None
            best_dist = float("inf")
            best_j = -1

            for j, val_w in enumerate(flat_words):
                if j == i or j in used_as_value:
                    continue
                # Must be to the right
                gap = val_w["x"] - (label_w["x"] + label_w["width"])
                if gap < 0 or gap > self.LABEL_VALUE_MAX_DIST:
                    continue
                # Same row
                if abs(val_w["y"] - label_w["y"]) > 10:
                    continue
                if gap < best_dist:
                    best_dist = gap
                    best_value = val_w
                    best_j = j

            if best_value is not None:
                confidence = max(0.5, 1.0 - (best_dist / self.LABEL_VALUE_MAX_DIST))
                pairs.append({
                    "label": text.rstrip(":"),
                    "label_position": {"x": label_w["x"], "y": label_w["y"]},
                    "value": best_value["text"],
                    "value_position": {"x": best_value["x"], "y": best_value["y"]},
                    "distance": round(best_dist, 2),
                    "confidence": round(confidence, 3),
                })
                used_as_value.add(best_j)

        return pairs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten(words: list[dict]) -> list[dict]:
        """Accept both raw dicts and enriched SpatialOCREngine output."""
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

    @staticmethod
    def _is_likely_label(text: str) -> bool:
        """Return True if the text looks like a form label."""
        stripped = text.rstrip(":").lower().strip()
        if text.endswith(":"):
            return True
        known_labels = {
            "invoice", "date", "amount", "total", "name", "address",
            "city", "state", "zip", "phone", "email", "fax", "po",
            "vendor", "customer", "bill to", "ship to", "description",
            "quantity", "price", "tax", "subtotal", "payment",
        }
        return stripped in known_labels

    @staticmethod
    def _assign_column(x: float, columns: list[dict]) -> int:
        """Return the 1-based column index for the given x coordinate."""
        for col in columns:
            if col["x_start"] <= x <= col["x_end"]:
                return col["index"]
        return 0

    @staticmethod
    def _assign_row(y: float, rows: list[dict]) -> int:
        """Return the 1-based row index for the given y coordinate."""
        for row in rows:
            if row["y_start"] <= y <= row["y_end"]:
                return row["index"]
        return 0
