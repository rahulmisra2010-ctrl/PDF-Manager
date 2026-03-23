"""
backend/services/field_extractor.py — Geometry-based OCR post-processor.

Converts raw OCR word-boxes into structured label/value pairs suitable for
the AI Extraction sidebar.  Key steps:

1. **Merge** adjacent same-line tokens into a single value token
   (e.g. ``ABC.`` + ``Complay`` + ``LTD``  →  ``ABC. Complay LTD``).
2. **Classify** each merged token as a likely *label* or *value*.
   Labels include parenthesised captions such as ``(city)`` / ``(state)`` /
   ``(ZIP)`` as well as keyword matches (Address, Legal Name, …).
3. **Pair** each value with the nearest label using spatial heuristics:
   prefer labels **above** (within 100 px), then labels **to the left**
   (within 200 px of horizontal distance).
4. Deduplicate and return a list ready for the sidebar.

Public API
----------
extract_labeled_fields(raw_boxes, page=None) -> list[dict]
    Input:
        raw_boxes — list of dicts, each with keys:
            text, x0, y0, x1, y1, confidence (float 0-1), page (int, optional)
    Output:
        list of dicts with keys:
            label, value, page, confidence, label_box, value_box
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Known label keywords (case-insensitive)
# ---------------------------------------------------------------------------

_LABEL_KEYWORDS: set[str] = {
    "legal name",
    "first name",
    "last name",
    "middle name",
    "full name",
    "given name",
    "surname",
    "student number",
    "student id",
    "address",
    "street and number",
    "city",
    "state",
    "zip",
    "zip code",
    "postal code",
    "pincode",
    "phone",
    "phone number",
    "mobile",
    "email",
    "academic program",
    "program",
    "reason for withdrawal",
    "reason",
    "year",
    "date",
    "student signature",
    "signature",
    "name",
    "department",
    "designation",
    "employee",
    "country",
    "district",
    "gender",
    "dob",
    "date of birth",
}

_LABEL_HINT_WORDS: set[str] = {
    "name",
    "address",
    "city",
    "state",
    "zip",
    "phone",
    "program",
    "year",
    "date",
    "email",
    "gender",
    "district",
    "country",
    "signature",
}


# ---------------------------------------------------------------------------
# Spatial parameters
# ---------------------------------------------------------------------------

_SAME_LINE_TOL: float = 12.0   # max vertical-centre distance to be "same line"
_MERGE_X_GAP: float = 18.0     # max horizontal gap (px) to merge same-line tokens
_LABEL_ABOVE_MAX_DY: float = 100.0   # max vertical distance for label-above match
_LABEL_LEFT_MAX_DX: float = 200.0    # max horizontal distance for label-left match


# ---------------------------------------------------------------------------
# Internal box dataclass
# ---------------------------------------------------------------------------

@dataclass
class _Box:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float = 1.0
    page: int = 1

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    text = (text or "").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_label(text: str) -> str:
    t = _normalize_text(text).lower()
    t = re.sub(r"[()#:\-_]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _clean_value(text: str) -> str:
    return _normalize_text(text)


# ---------------------------------------------------------------------------
# Label / value classifiers
# ---------------------------------------------------------------------------

def _is_likely_label(text: str) -> bool:
    """Return True if *text* looks like a form-field label."""
    raw = _normalize_text(text)
    norm = _normalize_label(text)

    if not norm:
        return False

    # Exact keyword match
    if norm in _LABEL_KEYWORDS:
        return True

    # Parenthesised captions such as "(city)", "(state)", "(ZIP)"
    if raw.startswith("(") and raw.endswith(")"):
        inner = _normalize_label(raw[1:-1])
        if inner in _LABEL_HINT_WORDS or inner in _LABEL_KEYWORDS:
            return True
        # Any short parenthesised word is likely a label
        if len(inner.split()) <= 3 and len(inner) >= 2:
            return True

    # Contains a hint word and is short enough to be a label
    if any(w in norm.split() for w in _LABEL_HINT_WORDS) and len(norm) <= 40:
        return True

    # Ends with a colon (common label convention)
    if raw.rstrip().endswith(":"):
        return True

    return False


def _is_likely_value(text: str) -> bool:
    """Return True if *text* looks like a form-field value."""
    raw = _clean_value(text)
    if not raw:
        return False
    if _is_likely_label(raw):
        return False
    # Values contain at least one letter or digit
    return bool(re.search(r"[A-Za-z0-9]", raw))


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _h_overlap(a: _Box, b: _Box) -> float:
    return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))


def _v_overlap(a: _Box, b: _Box) -> float:
    return max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))


def _same_line(a: _Box, b: _Box, tol: float = _SAME_LINE_TOL) -> bool:
    return abs(a.cy - b.cy) <= tol


# ---------------------------------------------------------------------------
# Step 1: merge adjacent same-line tokens
# ---------------------------------------------------------------------------

def _merge_same_line_boxes(
    boxes: list[_Box],
    x_gap: float = _MERGE_X_GAP,
    y_tol: float = _SAME_LINE_TOL,
) -> list[_Box]:
    """Merge horizontally adjacent tokens on the same line.

    ``ABC.`` + ``Complay`` + ``LTD`` on the same line with small gaps
    becomes ``ABC. Complay LTD`` (single box spanning all three).
    """
    if not boxes:
        return []

    # Sort by page, then top-to-bottom, left-to-right
    boxes = sorted(boxes, key=lambda b: (b.page, b.cy, b.x0))
    merged: list[_Box] = []
    used: list[bool] = [False] * len(boxes)

    for i, box in enumerate(boxes):
        if used[i]:
            continue

        current = _Box(
            text=_clean_value(box.text),
            x0=box.x0,
            y0=box.y0,
            x1=box.x1,
            y1=box.y1,
            confidence=box.confidence,
            page=box.page,
        )
        used[i] = True

        # Repeatedly absorb the next eligible neighbour
        growing = True
        while growing:
            growing = False
            for j in range(i + 1, len(boxes)):
                if used[j]:
                    continue
                other = boxes[j]
                if other.page != current.page:
                    continue
                if not _same_line(current, other, y_tol):
                    continue
                dx = other.x0 - current.x1
                if 0 <= dx <= x_gap:
                    # Do not merge across a label/value boundary: stop when the
                    # classification changes so that labels stay separate from
                    # the values that follow them (and vice-versa).
                    cur_is_label = _is_likely_label(current.text)
                    other_is_label = _is_likely_label(other.text)
                    if cur_is_label != other_is_label:
                        break  # boundary detected — stop extending this token
                    sep = "" if current.text.endswith("-") else " "
                    current = _Box(
                        text=_clean_value(current.text + sep + _clean_value(other.text)),
                        x0=min(current.x0, other.x0),
                        y0=min(current.y0, other.y0),
                        x1=max(current.x1, other.x1),
                        y1=max(current.y1, other.y1),
                        confidence=min(current.confidence, other.confidence),
                        page=current.page,
                    )
                    used[j] = True
                    growing = True
                    break  # restart from the beginning of the inner loop

        merged.append(current)

    return merged


# ---------------------------------------------------------------------------
# Step 3: pair each value with its nearest label
# ---------------------------------------------------------------------------

def _find_best_label(value: _Box, label_boxes: list[_Box]) -> Optional[_Box]:
    """Return the label _Box most likely to belong to *value*.

    Priority:
    1. Label **above** the value (within _LABEL_ABOVE_MAX_DY), prefer closer.
    2. Label **to the left** on the same row (within _LABEL_LEFT_MAX_DX).
    """
    best: Optional[_Box] = None
    best_score: float = float("inf")

    for label in label_boxes:
        if label.page != value.page:
            continue

        dx_center = abs(label.cx - value.cx)
        dy_center = abs(label.cy - value.cy)

        # ── Case A: label above the value ──────────────────────────────────
        is_above = label.y1 <= value.y0 + 8
        x_aligned = _h_overlap(label, value) > 0 or dx_center <= 90

        if is_above and x_aligned:
            dy = max(0.0, value.y0 - label.y1)
            if dy <= _LABEL_ABOVE_MAX_DY:
                score = dy * 2 + dx_center
                if score < best_score:
                    best_score = score
                    best = label
            continue

        # ── Case B: label to the left on the same row ───────────────────────
        is_left = label.x1 <= value.x0 + 8
        y_aligned = _v_overlap(label, value) > 0 or dy_center <= 24

        if is_left and y_aligned:
            dx = max(0.0, value.x0 - label.x1)
            if dx <= _LABEL_LEFT_MAX_DX:
                # Lower priority than above → add a constant penalty
                score = dx * 2 + dy_center + 30
                if score < best_score:
                    best_score = score
                    best = label

    return best


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_labeled_fields(
    raw_boxes: list[dict],
    page: Optional[int] = None,
) -> list[dict]:
    """Convert raw OCR boxes into structured label/value pairs.

    Parameters
    ----------
    raw_boxes:
        List of dicts, each with keys:
          ``text``, ``x0``, ``y0``, ``x1``, ``y1``,
          ``confidence`` (float, default 1.0),
          ``page`` (int, default 1).
    page:
        If provided, only process boxes whose ``page`` equals this value.

    Returns
    -------
    List of dicts with keys:
        ``label``      — normalised label string (e.g. ``"city"``).
        ``value``      — merged value string (e.g. ``"ABC1"``).
        ``page``       — page number (int, 1-based).
        ``confidence`` — min(label_confidence, value_confidence).
        ``label_box``  — dict {text, x0, y0, x1, y1} for the label token.
        ``value_box``  — dict {text, x0, y0, x1, y1} for the value token.
    """
    # ── Ingest and filter ──────────────────────────────────────────────────
    boxes: list[_Box] = []
    for b in raw_boxes:
        p = int(b.get("page", 1))
        if page is not None and p != page:
            continue
        text = _normalize_text(b.get("text", ""))
        if not text:
            continue
        try:
            x0 = float(b["x0"])
            y0 = float(b["y0"])
            x1 = float(b["x1"])
            y1 = float(b["y1"])
        except (KeyError, TypeError, ValueError):
            continue
        boxes.append(_Box(
            text=text,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            confidence=float(b.get("confidence", 1.0)),
            page=p,
        ))

    # ── Step 1: merge same-line tokens ─────────────────────────────────────
    merged = _merge_same_line_boxes(boxes)

    # ── Step 2: classify as labels or values ───────────────────────────────
    label_boxes = [b for b in merged if _is_likely_label(b.text)]
    value_boxes = [b for b in merged if _is_likely_value(b.text)]

    # ── Step 3: pair values with nearest label ─────────────────────────────
    pairs: list[dict] = []
    seen: set[tuple] = set()

    for value in value_boxes:
        label = _find_best_label(value, label_boxes)
        if label is None:
            continue

        label_name = _normalize_label(label.text)
        value_text = _clean_value(value.text)
        if not label_name or not value_text:
            continue

        key = (label_name, value_text, value.page)
        if key in seen:
            continue
        seen.add(key)

        pairs.append({
            "label": label_name,
            "value": value_text,
            "page": value.page,
            "confidence": round(min(label.confidence, value.confidence), 4),
            "label_box": {
                "text": label.text,
                "x0": label.x0,
                "y0": label.y0,
                "x1": label.x1,
                "y1": label.y1,
            },
            "value_box": {
                "text": value.text,
                "x0": value.x0,
                "y0": value.y0,
                "x1": value.x1,
                "y1": value.y1,
            },
        })

    return pairs
