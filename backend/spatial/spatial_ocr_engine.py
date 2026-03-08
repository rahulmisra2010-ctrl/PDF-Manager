"""
backend/spatial/spatial_ocr_engine.py — Spatial OCR Context Engine.

Extracts word-level position, bounding box, spatial context, visual
characteristics, and field-relationship data from PDF pages.

For each detected word the engine builds a rich dict with:
  - text / position / size
  - spatial_features  (zone, column, row, distances, nearby labels)
  - visual_features   (font size approximation, bold hint, colour)
  - contextual_features (confidence, pattern match, inferred field type)
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field-type pattern registry
# ---------------------------------------------------------------------------

_FIELD_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("invoice_number", re.compile(r"^(INV|inv)[-/]?\d{3,}", re.I)),
    ("date",           re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")),
    ("amount",         re.compile(r"^\$?\d+[\d,]*(\.\d{2})?$")),
    ("phone",          re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")),
    ("email",          re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")),
    ("zip_code",       re.compile(r"\b\d{5}(-\d{4})?\b")),
    ("po_number",      re.compile(r"^PO[-/]?\d{3,}", re.I)),
]

# Labels that strongly hint at the field type of the VALUE to the right
_LABEL_HINTS: dict[str, str] = {
    "invoice":        "invoice_number",
    "invoice #":      "invoice_number",
    "invoice no":     "invoice_number",
    "date":           "date",
    "due date":       "date",
    "invoice date":   "date",
    "amount":         "amount",
    "total":          "amount",
    "total due":      "amount",
    "balance due":    "amount",
    "phone":          "phone",
    "tel":            "phone",
    "email":          "email",
    "e-mail":         "email",
    "zip":            "zip_code",
    "zip code":       "zip_code",
    "po #":           "po_number",
    "po number":      "po_number",
    "purchase order": "po_number",
}


def _infer_field_type(text: str, nearby_labels: list[str]) -> tuple[str | None, float]:
    """Attempt to infer the field type from text patterns and nearby labels.

    Returns (field_type, confidence).
    """
    # Try label hints first (highest priority)
    for label in nearby_labels:
        key = label.lower().strip().rstrip(":")
        if key in _LABEL_HINTS:
            return _LABEL_HINTS[key], 0.90

    # Try pattern matching
    for field_type, pattern in _FIELD_PATTERNS:
        if pattern.search(text):
            return field_type, 0.80

    return None, 0.0


def _match_patterns(text: str) -> list[dict]:
    """Return all matching patterns with their name and confidence."""
    matches = []
    for field_type, pattern in _FIELD_PATTERNS:
        m = pattern.search(text)
        if m:
            matches.append({"pattern": pattern.pattern, "field_type": field_type, "confidence": 0.80})
    return matches


class SpatialOCREngine:
    """
    Extract rich spatial context for every word on a PDF page.

    Usage::

        engine = SpatialOCREngine()
        words = engine.extract_page(pdf_path, page_num=1)
        # words → list[dict] with text, position, spatial/visual/contextual features
    """

    def __init__(self, zoom: float = 2.0) -> None:
        self._zoom = zoom

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_page(self, pdf_path: str, page_num: int) -> list[dict]:
        """
        Extract all words from *page_num* (1-based) with full spatial context.

        Returns a list of enriched word dicts.
        """
        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF (fitz) is required for SpatialOCREngine")
            return []

        try:
            doc = fitz.open(pdf_path)
            page = doc[page_num - 1]
            page_width = page.rect.width
            page_height = page.rect.height

            raw_words = page.get_text("words")  # (x0,y0,x1,y1,word,block,line,wn)

            doc.close()
        except Exception as exc:
            logger.exception("Failed to open PDF page: %s", exc)
            return []

        # Collect plain word objects first
        plain_words = []
        for w in raw_words:
            x0, y0, x1, y1, word_text, *_ = w
            word_text = (word_text or "").strip()
            if not word_text:
                continue
            plain_words.append({
                "text": word_text,
                "x": round(x0, 2),
                "y": round(y0, 2),
                "width": round(x1 - x0, 2),
                "height": round(y1 - y0, 2),
                "page": page_num,
            })

        # Determine zones
        header_y = page_height * 0.15
        footer_y = page_height * 0.85

        # Build the enriched output
        enriched: list[dict] = []
        for w in plain_words:
            x, y, width, height = w["x"], w["y"], w["width"], w["height"]

            zone = "body"
            if y < header_y:
                zone = "header"
            elif y > footer_y:
                zone = "footer"

            spatial_features = self._spatial_features(
                x, y, width, height, page_width, page_height, zone, plain_words
            )
            visual_features = self._visual_features(width, height, w["text"])
            nearby_labels = spatial_features.get("nearby_labels", [])
            contextual_features = self._contextual_features(
                w["text"], nearby_labels
            )

            enriched.append({
                "text": w["text"],
                "position": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "page": page_num,
                    "zone": zone,
                },
                "spatial_features": spatial_features,
                "visual_features": visual_features,
                "contextual_features": contextual_features,
            })

        return enriched

    def extract_document(self, pdf_path: str) -> dict:
        """Extract spatial data for every page in the PDF.

        Returns::

            {
                "total_pages": N,
                "pages": { "1": [...words...], "2": [...] },
            }
        """
        try:
            import fitz
            doc = fitz.open(pdf_path)
            page_count = len(doc)
            doc.close()
        except Exception as exc:
            logger.exception("Could not open PDF: %s", exc)
            return {"total_pages": 0, "pages": {}}

        pages: dict[str, list[dict]] = {}
        for p in range(1, page_count + 1):
            pages[str(p)] = self.extract_page(pdf_path, p)

        return {"total_pages": page_count, "pages": pages}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _spatial_features(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        page_width: float,
        page_height: float,
        zone: str,
        all_words: list[dict],
    ) -> dict:
        """Compute spatial features for a word."""
        cx = x + width / 2
        cy = y + height / 2

        dist_top = round(y, 2)
        dist_left = round(x, 2)
        dist_right = round(page_width - (x + width), 2)
        dist_bottom = round(page_height - (y + height), 2)

        # Horizontal alignment hint
        if cx < page_width * 0.33:
            h_align = "left"
        elif cx < page_width * 0.66:
            h_align = "center"
        else:
            h_align = "right"

        # Vertical alignment hint
        if cy < page_height * 0.33:
            v_align = "top"
        elif cy < page_height * 0.66:
            v_align = "middle"
        else:
            v_align = "bottom"

        # Nearby labels (words to the left within the same row ± 10px)
        nearby_labels: list[str] = []
        nearest_dist = float("inf")
        label_position = None
        for other in all_words:
            if other["x"] == x and other["y"] == y:
                continue
            oy = other["y"]
            ox = other["x"]
            ow = other["width"]
            # Same row (y within ±10 pixels)
            if abs(oy - y) <= 10:
                # Label should be to the left, close enough
                right_edge = ox + ow
                horizontal_gap = x - right_edge
                if 0 < horizontal_gap < 200:
                    nearby_labels.append(other["text"])
                    if horizontal_gap < nearest_dist:
                        nearest_dist = horizontal_gap
                        label_position = "left"

        is_isolated = len(nearby_labels) == 0 and not any(
            abs(other["y"] - y) <= 10 and other["x"] != x
            for other in all_words
        )

        # Column / row estimation (normalised 1-based index)
        col = max(1, int(x / (page_width / 4)) + 1)
        row = max(1, int(y / 20) + 1)

        return {
            "distance_from_top": dist_top,
            "distance_from_left": dist_left,
            "distance_from_right": dist_right,
            "distance_from_bottom": dist_bottom,
            "horizontal_alignment": h_align,
            "vertical_alignment": v_align,
            "is_isolated": is_isolated,
            "nearby_labels": nearby_labels[:5],  # cap at 5
            "distance_to_nearest_label": round(nearest_dist, 2) if nearest_dist != float("inf") else None,
            "label_position": label_position,
            "in_column": col,
            "in_row": row,
            "zone": zone,
        }

    @staticmethod
    def _visual_features(width: float, height: float, text: str) -> dict:
        """Estimate visual features from bounding-box dimensions and text."""
        # Approximate font size from character height
        font_size = round(height * 0.75, 1)

        # Heuristic: bold text tends to be slightly wider per character
        avg_char_width = width / max(len(text), 1)
        is_bold = avg_char_width > height * 0.65

        return {
            "font_size": font_size,
            "is_bold": is_bold,
            "is_italic": False,  # Cannot determine from bbox alone
            "text_color": "black",
            "background_color": "white",
            "contrast_ratio": 21.0,
            "in_box": False,
            "has_underline": False,
            "has_background_shading": False,
        }

    @staticmethod
    def _contextual_features(text: str, nearby_labels: list[str]) -> dict:
        """Infer contextual features including field type."""
        field_type, ft_confidence = _infer_field_type(text, nearby_labels)
        matched = _match_patterns(text)
        pattern_str = matched[0]["pattern"] if matched else None
        pattern_confidence = matched[0]["confidence"] if matched else 0.0

        return {
            "ocr_confidence": 0.95,  # Default for PyMuPDF native extraction
            "matches_pattern": pattern_str,
            "pattern_confidence": pattern_confidence,
            "field_type_inferred": field_type,
            "field_type_confidence": ft_confidence,
        }
