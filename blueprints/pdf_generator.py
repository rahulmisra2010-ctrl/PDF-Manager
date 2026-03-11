"""
blueprints/pdf_generator.py — PDF Generation Service.

Loads an original PDF, overlays user-selected field values as text
annotations using PyMuPDF (fitz), and returns the result as bytes.

Falls back gracefully when PyMuPDF is not installed.
"""

from __future__ import annotations

import io
import os
from typing import Any


# Default font size for overlaid text
_FONT_SIZE = 11
_FONT_COLOR = (0.0, 0.0, 0.8)  # blue-ish


def generate_filled_pdf(
    source_path: str,
    field_values: dict[str, str],
    field_bboxes: dict[str, dict[str, Any]] | None = None,
) -> bytes:
    """Overlay *field_values* onto *source_path* and return PDF bytes.

    Args:
        source_path: Absolute path to the original PDF file.
        field_values: Mapping of ``field_name`` → ``value`` to fill in.
        field_bboxes: Optional mapping of ``field_name`` → bbox dict with keys
                      ``x``, ``y``, ``width``, ``height``, ``page_number``.
                      When absent, values are appended in a summary section.

    Returns:
        PDF file contents as ``bytes``.

    Raises:
        FileNotFoundError: If *source_path* does not exist.
        RuntimeError: If PDF generation fails.
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source PDF not found: {source_path}")

    try:
        import fitz  # PyMuPDF  # type: ignore[import]
        return _generate_with_fitz(fitz, source_path, field_values, field_bboxes or {})
    except ImportError:
        return _generate_fallback(source_path, field_values)


def _generate_with_fitz(
    fitz: Any,
    source_path: str,
    field_values: dict[str, str],
    field_bboxes: dict[str, dict[str, Any]],
) -> bytes:
    """Generate PDF using PyMuPDF."""
    doc = fitz.open(source_path)

    for field_name, value in field_values.items():
        if not value:
            continue

        bbox_info = field_bboxes.get(field_name)
        if bbox_info:
            page_num = int(bbox_info.get("page_number", 1)) - 1
            page_num = max(0, min(page_num, len(doc) - 1))
            page = doc[page_num]
            x = float(bbox_info.get("x", 50))
            y = float(bbox_info.get("y", 50))
            rect = fitz.Rect(x, y, x + float(bbox_info.get("width", 200)), y + 20)
            page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))  # white background
            page.insert_text(
                (x + 2, y + 14),
                value,
                fontsize=_FONT_SIZE,
                color=_FONT_COLOR,
            )

    # Append a summary page with all field values
    page = doc.new_page()
    y_pos = 50
    page.insert_text((50, y_pos), "Validated Field Values", fontsize=14, color=(0, 0, 0))
    y_pos += 30
    for field_name, value in field_values.items():
        if value:
            page.insert_text(
                (50, y_pos),
                f"{field_name}: {value}",
                fontsize=_FONT_SIZE,
                color=(0, 0, 0),
            )
            y_pos += 20

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    buf.seek(0)
    return buf.read()


def _generate_fallback(source_path: str, field_values: dict[str, str]) -> bytes:
    """Return the original PDF bytes unchanged (PyMuPDF not available)."""
    with open(source_path, "rb") as fh:
        return fh.read()
