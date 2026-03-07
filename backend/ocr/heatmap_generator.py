"""
backend/ocr/heatmap_generator.py — OCR confidence heatmap generator.

Generates a JSON-serialisable heatmap that maps grid cells to confidence
values (Red/Yellow/Green) suitable for rendering in the frontend.

If OpenCV / NumPy are available, a PNG base64 image is also generated.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ocr_engine import PageOCRResult, WordResult

logger = logging.getLogger(__name__)

try:
    import cv2 as _cv2
    import numpy as _np
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


def _confidence_to_bgr(confidence: float) -> tuple[int, int, int]:
    """Map confidence (0–1) to BGR colour: red → yellow → green."""
    if confidence >= 0.85:
        return (0, 200, 0)      # green
    if confidence >= 0.65:
        return (0, 200, 255)    # yellow (BGR: B=0, G=200, R=255)
    return (0, 0, 220)          # red


def _badge_color(confidence: float) -> str:
    if confidence >= 0.85:
        return "green"
    if confidence >= 0.65:
        return "yellow"
    return "red"


class HeatmapGenerator:
    """
    Generate confidence heatmaps for OCR results.

    Two output formats
    ------------------
    * ``generate_json``  — returns a list of cell dicts (always available)
    * ``generate_image`` — returns a base64-encoded PNG (requires OpenCV)
    """

    def __init__(self, grid_cols: int = 40, grid_rows: int = 56) -> None:
        self._grid_cols = grid_cols
        self._grid_rows = grid_rows

    # ------------------------------------------------------------------
    # JSON heatmap
    # ------------------------------------------------------------------

    def generate_json(
        self,
        page_result: "PageOCRResult",
        page_width: float = 595.0,
        page_height: float = 842.0,
    ) -> dict:
        """
        Build a JSON-serialisable heatmap for a page.

        The page is divided into a grid; each cell contains the average
        confidence of all OCR words whose centre falls inside it.

        Args:
            page_result:  OCR result for the page.
            page_width:   PDF page width in points (default A4).
            page_height:  PDF page height in points (default A4).

        Returns:
            dict with ``cells``, ``grid_cols``, ``grid_rows``, and ``word_markers``.
        """
        cols = self._grid_cols
        rows = self._grid_rows
        cell_w = page_width / cols
        cell_h = page_height / rows

        # Accumulate confidence per cell
        cell_sum = [[0.0] * cols for _ in range(rows)]
        cell_cnt = [[0] * cols for _ in range(rows)]

        for word in page_result.words:
            cx = word.x + word.width / 2
            cy = word.y + word.height / 2
            col = min(int(cx / cell_w), cols - 1)
            row = min(int(cy / cell_h), rows - 1)
            cell_sum[row][col] += word.confidence
            cell_cnt[row][col] += 1

        cells = []
        for r in range(rows):
            for c in range(cols):
                cnt = cell_cnt[r][c]
                conf = (cell_sum[r][c] / cnt) if cnt > 0 else None
                cells.append(
                    {
                        "row": r,
                        "col": c,
                        "confidence": round(conf, 4) if conf is not None else None,
                        "color": _badge_color(conf) if conf is not None else "none",
                    }
                )

        word_markers = [
            {
                "text": w.text,
                "confidence": round(w.confidence, 4),
                "color": _badge_color(w.confidence),
                "x": w.x,
                "y": w.y,
                "width": w.width,
                "height": w.height,
            }
            for w in page_result.words
        ]

        return {
            "page_number": page_result.page_number,
            "grid_cols": cols,
            "grid_rows": rows,
            "page_width": page_width,
            "page_height": page_height,
            "cells": cells,
            "word_markers": word_markers,
            "avg_confidence": round(page_result.avg_confidence, 4),
        }

    # ------------------------------------------------------------------
    # PNG image heatmap (optional, requires OpenCV)
    # ------------------------------------------------------------------

    def generate_image(
        self,
        page_result: "PageOCRResult",
        page_width: float = 595.0,
        page_height: float = 842.0,
        scale: float = 1.0,
    ) -> str | None:
        """
        Generate a PNG heatmap image encoded as a base64 string.

        Returns ``None`` if OpenCV is not installed.

        Args:
            page_result: OCR result for the page.
            page_width:  Page width in points.
            page_height: Page height in points.
            scale:       Render scale factor (default 1.0 = 1 pixel per point).

        Returns:
            ``"data:image/png;base64,<data>"`` string or ``None``.
        """
        if not _CV2_AVAILABLE:
            return None

        img_w = int(page_width * scale)
        img_h = int(page_height * scale)
        img = _np.ones((img_h, img_w, 3), dtype=_np.uint8) * 240  # light grey bg

        for word in page_result.words:
            x1 = int(word.x * scale)
            y1 = int(word.y * scale)
            x2 = int((word.x + word.width) * scale)
            y2 = int((word.y + word.height) * scale)
            color = _confidence_to_bgr(word.confidence)
            _cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)  # filled rect
            # Draw word text
            _cv2.putText(
                img,
                word.text[:12],
                (x1, max(y1 + 12, 1)),
                _cv2.FONT_HERSHEY_SIMPLEX,
                0.35 * scale,
                (0, 0, 0),
                1,
                _cv2.LINE_AA,
            )

        # Add a semi-transparent legend
        legend_y = img_h - 30
        for i, (label, bgr) in enumerate(
            [("High (≥85%)", (0, 200, 0)), ("Med (≥60%)", (0, 200, 255)), ("Low (<60%)", (0, 0, 220))]
        ):
            lx = 10 + i * 160
            _cv2.rectangle(img, (lx, legend_y), (lx + 20, legend_y + 15), bgr, -1)
            _cv2.putText(
                img, label, (lx + 25, legend_y + 12),
                _cv2.FONT_HERSHEY_SIMPLEX, 0.4, (50, 50, 50), 1
            )

        _, buf = _cv2.imencode(".png", img)
        b64 = base64.b64encode(buf.tobytes()).decode("ascii")
        return f"data:image/png;base64,{b64}"
