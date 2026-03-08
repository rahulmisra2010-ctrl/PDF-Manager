"""
backend/spatial/position_embedder.py — Spatial position embeddings.

Creates a compact numerical vector for each word's spatial features so
that similar positions (and therefore likely similar fields) can be found
via cosine or Euclidean distance.

Vector layout (12 dimensions, all normalised to [0, 1]):
  0  x_norm              — normalised left edge
  1  y_norm              — normalised top edge
  2  w_norm              — normalised width
  3  h_norm              — normalised height
  4  zone_norm           — 0=header, 0.5=body, 1=footer
  5  col_norm            — column index / max_columns
  6  row_norm            — row index / max_rows
  7  dist_label_norm     — distance to nearest label (0=close, 1=far)
  8  h_align_norm        — 0=left, 0.5=center, 1=right
  9  v_align_norm        — 0=top, 0.5=middle, 1=bottom
  10 is_isolated         — 0 or 1
  11 font_size_norm      — estimated font size / 72 (capped)
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

_ZONE_MAP = {"header": 0.0, "body": 0.5, "footer": 1.0}
_HALIGN_MAP = {"left": 0.0, "center": 0.5, "right": 1.0}
_VALIGN_MAP = {"top": 0.0, "middle": 0.5, "bottom": 1.0}

EMBEDDING_DIM = 12


class PositionEmbedder:
    """
    Convert spatial word features into fixed-length embedding vectors.

    Usage::

        embedder = PositionEmbedder(page_width=595, page_height=842)
        vec = embedder.embed(word)        # → list[float] of length 12
        vecs = embedder.embed_all(words)  # → list[list[float]]
    """

    def __init__(
        self,
        page_width: float = 595.0,
        page_height: float = 842.0,
        max_columns: int = 10,
        max_rows: int = 60,
    ) -> None:
        self._pw = page_width
        self._ph = page_height
        self._max_columns = max_columns
        self._max_rows = max_rows

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, word: dict) -> list[float]:
        """Return a 12-dimensional embedding for a single enriched word dict."""
        pos = word.get("position", {})
        sp = word.get("spatial_features", {})
        vis = word.get("visual_features", {})

        x = pos.get("x", 0) / self._pw
        y = pos.get("y", 0) / self._ph
        w = pos.get("width", 0) / self._pw
        h = pos.get("height", 0) / self._ph

        zone_str = pos.get("zone") or sp.get("zone", "body")
        zone = _ZONE_MAP.get(zone_str, 0.5)

        col = sp.get("in_column", 1)
        col_norm = min(col / self._max_columns, 1.0)

        row = sp.get("in_row", 1)
        row_norm = min(row / self._max_rows, 1.0)

        raw_dist = sp.get("distance_to_nearest_label")
        if raw_dist is None:
            dist_norm = 1.0  # maximum distance = no label found
        else:
            dist_norm = min(raw_dist / 300.0, 1.0)

        h_align = _HALIGN_MAP.get(sp.get("horizontal_alignment", "left"), 0.0)
        v_align = _VALIGN_MAP.get(sp.get("vertical_alignment", "top"), 0.0)

        is_isolated = 1.0 if sp.get("is_isolated", False) else 0.0

        font_size = vis.get("font_size", 12)
        font_norm = min(font_size / 72.0, 1.0)

        return [
            round(x, 5),
            round(y, 5),
            round(w, 5),
            round(h, 5),
            round(zone, 5),
            round(col_norm, 5),
            round(row_norm, 5),
            round(dist_norm, 5),
            round(h_align, 5),
            round(v_align, 5),
            round(is_isolated, 5),
            round(font_norm, 5),
        ]

    def embed_all(self, words: list[dict]) -> list[dict]:
        """Return words augmented with their embedding vectors."""
        result = []
        for w in words:
            vec = self.embed(w)
            entry = dict(w)
            entry["embedding"] = vec
            result.append(entry)
        return result

    # ------------------------------------------------------------------
    # Similarity helpers
    # ------------------------------------------------------------------

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Cosine similarity between two embedding vectors."""
        dot = sum(ai * bi for ai, bi in zip(a, b))
        mag_a = math.sqrt(sum(ai * ai for ai in a))
        mag_b = math.sqrt(sum(bi * bi for bi in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return round(dot / (mag_a * mag_b), 4)

    @staticmethod
    def euclidean_distance(a: list[float], b: list[float]) -> float:
        """Euclidean distance between two embedding vectors."""
        return round(math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b))), 4)

    def find_similar(
        self,
        query_embedding: list[float],
        candidates: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """
        Find the *top_k* most similar words from *candidates*.

        Each candidate must have an ``"embedding"`` key (e.g. produced by
        :meth:`embed_all`).  Returns candidates sorted by cosine similarity
        descending, with similarity score attached.
        """
        scored = []
        for c in candidates:
            emb = c.get("embedding")
            if not emb:
                continue
            sim = self.cosine_similarity(query_embedding, emb)
            scored.append({**c, "similarity": sim})
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]
