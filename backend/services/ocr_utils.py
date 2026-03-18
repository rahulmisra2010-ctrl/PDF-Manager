"""
backend/services/ocr_utils.py — EasyOCR fallback for image-based PDFs.

When pdfplumber / PyMuPDF text extraction yields no usable content (e.g. the
PDF page is a scanned image), this module renders the page to a raster image
with PyMuPDF and runs EasyOCR to recover the text.

Public API
----------
ocr_page_text(pdf_path, page_index=0, dpi=300) -> str
    Render a single PDF page and return its OCR text.

extract_street_address_from_ocr(ocr_text) -> str | None
    Find the line that follows a "Street Address" header (case-insensitive,
    tolerant of minor OCR noise).

fill_missing_fields_with_ocr(fields, pdf_path, page_index=0) -> dict
    Given an already-extracted fields dict, fill any blank "Street Address"
    (or "street_address") entry using OCR.  Other fields are untouched.

Environment / configuration
---------------------------
OCR_FALLBACK_ENABLED  — set to "0" or "false" to disable (default: enabled)
OCR_FALLBACK_DPI      — render resolution (default: 300)
OCR_FALLBACK_PAGE     — zero-based page index to OCR (default: 0)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature flag — honour OCR_FALLBACK_ENABLED env-var
# ---------------------------------------------------------------------------

def _ocr_enabled() -> bool:
    """Return True unless OCR_FALLBACK_ENABLED is explicitly disabled."""
    val = os.environ.get("OCR_FALLBACK_ENABLED", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


# ---------------------------------------------------------------------------
# Lazy EasyOCR reader cache (models are large; reload only once per process)
# ---------------------------------------------------------------------------

_easyocr_reader = None  # module-level singleton


def _get_reader():
    """Return a cached EasyOCR Reader, creating it on first call."""
    global _easyocr_reader
    if _easyocr_reader is None:
        try:
            import easyocr  # type: ignore[import]
            logger.info("Initialising EasyOCR reader (first-run may download models)…")
            _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            logger.info("EasyOCR reader ready.")
        except ImportError:
            logger.warning(
                "easyocr is not installed — OCR fallback will not run. "
                "Install it with: pip install easyocr"
            )
    return _easyocr_reader


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def ocr_page_text(pdf_path: str, page_index: int = 0, dpi: int = 300) -> str:
    """Render a PDF page to an image and return the OCR text.

    Parameters
    ----------
    pdf_path:
        Absolute path to the PDF file.
    page_index:
        Zero-based page number (default: 0 = first page).
    dpi:
        Render resolution in dots-per-inch (default: 300).  Higher values give
        better OCR accuracy at the cost of memory/speed.

    Returns
    -------
    str
        The recognised text joined with newlines, or an empty string if OCR
        is unavailable or the page cannot be rendered.
    """
    reader = _get_reader()
    if reader is None:
        return ""

    try:
        import fitz  # PyMuPDF  # type: ignore[import]
    except ImportError:
        logger.warning("PyMuPDF (fitz) is not installed — cannot render PDF page for OCR.")
        return ""

    try:
        doc = fitz.open(pdf_path)
        try:
            if page_index >= len(doc):
                logger.warning(
                    "ocr_page_text: page_index %d out of range (document has %d pages)",
                    page_index, len(doc),
                )
                return ""
            page = doc[page_index]
            # Scale factor so that 1 inch = dpi pixels (default PDF unit = 72 pt/inch)
            scale = dpi / 72.0
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat)
            img_bytes: bytes = pix.tobytes("png")
        finally:
            doc.close()
    except Exception as exc:
        logger.warning("ocr_page_text: failed to render page %d of %s: %s", page_index, pdf_path, exc)
        return ""

    try:
        import numpy as np  # type: ignore[import]
        from PIL import Image  # type: ignore[import]
        import io

        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_array = np.array(img)
        results = reader.readtext(img_array, detail=0, paragraph=False)
        text = "\n".join(str(r) for r in results)
        logger.debug("ocr_page_text: extracted %d chars from page %d", len(text), page_index)
        return text
    except Exception as exc:
        logger.warning("ocr_page_text: EasyOCR failed on page %d: %s", page_index, exc)
        return ""


def extract_street_address_from_ocr(ocr_text: str) -> Optional[str]:
    """Find the Street Address value embedded in OCR text.

    The function looks for a line that contains the label "Street Address"
    (case-insensitive, tolerant of common OCR artefacts such as extra
    spaces or punctuation) and returns the *next non-empty line* as the
    value.  If the value follows the label on the same line (``Street
    Address: Foo Bar``) that inline value is returned instead.

    Parameters
    ----------
    ocr_text:
        Raw text produced by :func:`ocr_page_text`.

    Returns
    -------
    str | None
        The extracted street address, or ``None`` if not found.
    """
    if not ocr_text:
        return None

    lines = ocr_text.splitlines()

    # Regex: "Street" followed (optionally) by whitespace/noise then "Address",
    # then an optional separator, then an optional inline value.
    label_re = re.compile(
        r"^[^a-zA-Z]*Street[\s._\-]*Address[\s:._\-]*(.*)$",
        re.IGNORECASE,
    )

    for i, line in enumerate(lines):
        m = label_re.match(line.strip())
        if m is None:
            continue

        inline = m.group(1).strip()
        if inline:
            return inline

        # Look for the next non-empty line
        for j in range(i + 1, len(lines)):
            candidate = lines[j].strip()
            if candidate:
                return candidate

    return None


def fill_missing_fields_with_ocr(
    fields: dict,
    pdf_path: str,
    page_index: int = 0,
) -> dict:
    """Fill a blank Street Address entry in *fields* using OCR.

    Only runs when:
    - OCR fallback is enabled (``OCR_FALLBACK_ENABLED != '0'``), and
    - the Street Address value is missing/blank.

    Both ``"Street Address"`` (display key) and ``"street_address"``
    (snake_case key) are checked and updated if present.

    Parameters
    ----------
    fields:
        Dict of field-name → value pairs, as returned by extraction
        routines.  Modified **in-place** and also returned.
    pdf_path:
        Path to the source PDF file.
    page_index:
        Zero-based page number to OCR (default: 0).

    Returns
    -------
    dict
        The (potentially updated) *fields* dict.
    """
    if not _ocr_enabled():
        return fields

    # Determine which key(s) represent Street Address and whether any is blank
    display_key = "Street Address"
    snake_key = "street_address"

    has_display = display_key in fields
    has_snake = snake_key in fields

    display_blank = has_display and not (fields.get(display_key) or "").strip()
    snake_blank = has_snake and not (fields.get(snake_key) or "").strip()

    # If neither key exists, initialise the display key so we can fill it
    if not has_display and not has_snake:
        fields[display_key] = ""
        display_blank = True

    if not (display_blank or snake_blank):
        # Both keys exist and at least one is non-blank — nothing to do
        return fields

    logger.info(
        "Street Address is blank — running EasyOCR fallback on page %d of %s",
        page_index, pdf_path,
    )

    dpi = int(os.environ.get("OCR_FALLBACK_DPI", "300"))
    ocr_text = ocr_page_text(pdf_path, page_index=page_index, dpi=dpi)

    if not ocr_text:
        logger.info("OCR fallback returned no text — Street Address remains blank.")
        return fields

    value = extract_street_address_from_ocr(ocr_text)
    if not value:
        logger.info("OCR fallback could not locate a Street Address line.")
        return fields

    logger.info("OCR fallback found Street Address: %r", value)

    if display_blank:
        fields[display_key] = value
    if snake_blank:
        fields[snake_key] = value

    return fields
