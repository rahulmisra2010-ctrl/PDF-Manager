"""
backend/services/ocr_utils.py — EasyOCR fallback for image-based PDFs.

When pdfplumber / PyMuPDF text extraction yields no usable content (e.g. the
PDF page is a scanned image), this module renders the page to a raster image
with PyMuPDF and runs EasyOCR to recover the text.

Public API
----------
ocr_page_text(pdf_path, page_index=0, dpi=300) -> str
    Render a single PDF page and return its OCR text.

ocr_image_text(image_path) -> str
    Load a real image file (PNG/JPG) with OpenCV and return its OCR text.
    Raises ValueError if the file is actually a PDF (detected by magic bytes).
    Raises ValueError if OpenCV cannot open the file.

extract_street_address_from_ocr(ocr_text) -> str | None
    Find the line that follows a "Street Address" header (case-insensitive,
    tolerant of minor OCR noise).

extract_cell_phone_from_ocr(ocr_text) -> str | None
    Find a 10-digit Cell Phone number that follows a "Cell Phone:" label.

fill_missing_fields_with_ocr(fields, pdf_path, page_index=0) -> dict
    Given an already-extracted fields dict, fill any blank "Street Address"
    (or "street_address") and "Cell Phone" (or "cell_phone") entries using
    OCR.  Other fields are untouched.

Environment / configuration
---------------------------
OCR_FALLBACK_ENABLED  — set to "0" or "false" to disable (default: enabled)
OCR_FALLBACK_DPI      — render resolution (default: 300)
OCR_FALLBACK_PAGE     — zero-based page index to OCR (default: 0)
"""

from __future__ import annotations

import io
import logging
import os
import re
from typing import Optional

# Known file-signature (magic-byte) constants
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"   # 89 50 4E 47 0D 0A 1A 0A
_PDF_SIGNATURE = b"%PDF"

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

        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_array = np.array(img)
        results = reader.readtext(img_array, detail=0, paragraph=False)
        text = "\n".join(str(r) for r in results)
        logger.debug("ocr_page_text: extracted %d chars from page %d", len(text), page_index)
        return text
    except Exception as exc:
        logger.warning("ocr_page_text: EasyOCR failed on page %d: %s", page_index, exc)
        return ""


def ocr_image_text(image_path: str) -> str:
    """Run EasyOCR on an image file (PNG, JPG, etc.) and return the text.

    Uses OpenCV (``cv2.imread``) to load the image, which avoids missing
    back-end issues that can occur with ``skimage.io.imread``.  The file's
    magic bytes are checked before loading so that a PDF renamed with a
    ``.png`` extension is detected early and a clear error is raised.

    Parameters
    ----------
    image_path:
        Absolute (or relative) path to a real image file (PNG, JPG, BMP, …).
        Must **not** be a PDF — pass PDF files to :func:`ocr_page_text` instead.

    Returns
    -------
    str
        The recognised text joined with newlines, or an empty string if OCR
        is unavailable or the image cannot be read.

    Raises
    ------
    FileNotFoundError
        If *image_path* does not exist on disk.
    ValueError
        If the file signature indicates a PDF rather than an image, or if
        OpenCV cannot decode the file.
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(
            f"Image file not found: {image_path!r}\n"
            "Check that the path is correct and that the file exists."
        )

    # -----------------------------------------------------------------------
    # Inspect magic bytes to catch common mistake of a PDF renamed to .png
    # -----------------------------------------------------------------------
    try:
        with open(image_path, "rb") as _f:
            header = _f.read(8)
    except OSError as exc:
        raise OSError(f"Cannot read file {image_path!r}: {exc}") from exc

    if header[:4] == _PDF_SIGNATURE:
        raise ValueError(
            f"{image_path!r} appears to be a PDF file (file starts with %PDF), "
            "not a real image.\n"
            "To verify in PowerShell: "
            "(Get-Content -Path '<file>' -Encoding Byte -TotalCount 4) -join ' '\n"
            "A real PNG file starts with (hex): 89 50 4E 47 (decimal: 137 80 78 71).\n"
            "Use ocr_page_text() for PDF files, or create a genuine PNG screenshot "
            "with the Snipping Tool (Win+Shift+S) and save it as a .png file."
        )

    reader = _get_reader()
    if reader is None:
        return ""

    # -----------------------------------------------------------------------
    # Load with OpenCV (BGR → RGB for EasyOCR)
    # -----------------------------------------------------------------------
    try:
        import cv2  # type: ignore[import]
        img_array = cv2.imread(image_path)
        if img_array is None:
            raise ValueError(
                f"OpenCV could not open {image_path!r}.\n"
                "Possible causes:\n"
                "  • The path is wrong or contains unexpected characters — "
                "double-check every folder name and the file extension.\n"
                "  • The file is not a supported image format "
                "(PNG, JPG, BMP, TIFF are all fine).\n"
                f"  • File header bytes: {header!r}"
            )
        img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
    except ImportError:
        logger.warning(
            "opencv-python (cv2) is not installed — falling back to PIL. "
            "Install it with: pip install opencv-python"
        )
        try:
            import numpy as np  # type: ignore[import]
            from PIL import Image  # type: ignore[import]
            img = Image.open(image_path).convert("RGB")
            img_array = np.array(img)
        except Exception as exc:
            raise RuntimeError(
                f"Cannot load image {image_path!r}: {exc}\n"
                "Install opencv-python for best results: pip install opencv-python"
            ) from exc

    try:
        results = reader.readtext(img_array, detail=0, paragraph=False)
        text = "\n".join(str(r) for r in results)
        logger.debug("ocr_image_text: extracted %d chars from %s", len(text), image_path)
        return text
    except Exception as exc:
        logger.warning("ocr_image_text: EasyOCR failed on %s: %s", image_path, exc)
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


def extract_cell_phone_from_ocr(ocr_text: str) -> Optional[str]:
    """Find a Cell Phone number embedded in OCR text.

    Looks for a "Cell Phone" label (case-insensitive, tolerant of extra
    spaces or punctuation) followed by a sequence of digits.  Returns the
    first 10-digit number found after the label, or ``None`` if not found.

    Parameters
    ----------
    ocr_text:
        Raw text produced by :func:`ocr_page_text` or :func:`ocr_image_text`.

    Returns
    -------
    str | None
        A 10-digit phone number string (digits only), or ``None`` if not found.
    """
    if not ocr_text:
        return None

    # Match "Cell Phone" label with optional separators, then capture digits
    pattern = re.compile(
        r"Cell[\s._\-]*Phone[\s:._\-]*([\d][\d\s\-\(\)\.]{7,}[\d])",
        re.IGNORECASE,
    )

    m = pattern.search(ocr_text)
    if m:
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) == 10:
            return digits

    return None


def fill_missing_fields_with_ocr(
    fields: dict,
    pdf_path: str,
    page_index: int = 0,
) -> dict:
    """Fill blank Street Address and Cell Phone entries in *fields* using OCR.

    Only runs when:
    - OCR fallback is enabled (``OCR_FALLBACK_ENABLED != '0'``), and
    - the Street Address or Cell Phone value is missing/blank.

    Both ``"Street Address"`` (display key) and ``"street_address"``
    (snake_case key) are checked and updated if present.  Likewise for
    ``"Cell Phone"`` / ``"cell_phone"``.

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

    # -----------------------------------------------------------------------
    # Street Address
    # -----------------------------------------------------------------------
    addr_display_key = "Street Address"
    addr_snake_key = "street_address"

    addr_has_display = addr_display_key in fields
    addr_has_snake = addr_snake_key in fields

    addr_display_blank = addr_has_display and not (fields.get(addr_display_key) or "").strip()
    addr_snake_blank = addr_has_snake and not (fields.get(addr_snake_key) or "").strip()

    # If neither key exists, initialise the display key so we can fill it
    if not addr_has_display and not addr_has_snake:
        fields[addr_display_key] = ""
        addr_display_blank = True

    # -----------------------------------------------------------------------
    # Cell Phone
    # -----------------------------------------------------------------------
    phone_display_key = "Cell Phone"
    phone_snake_key = "cell_phone"

    phone_display_blank = phone_display_key in fields and not (fields.get(phone_display_key) or "").strip()
    phone_snake_blank = phone_snake_key in fields and not (fields.get(phone_snake_key) or "").strip()

    needs_addr = addr_display_blank or addr_snake_blank
    needs_phone = phone_display_blank or phone_snake_blank

    if not (needs_addr or needs_phone):
        return fields

    logger.info(
        "Running EasyOCR fallback on page %d of %s (street_address_blank=%s, cell_phone_blank=%s)",
        page_index, pdf_path, needs_addr, needs_phone,
    )

    dpi = int(os.environ.get("OCR_FALLBACK_DPI", "300"))
    ocr_text = ocr_page_text(pdf_path, page_index=page_index, dpi=dpi)

    if not ocr_text:
        logger.info("OCR fallback returned no text — fields remain blank.")
        return fields

    if needs_addr:
        value = extract_street_address_from_ocr(ocr_text)
        if value:
            logger.info("OCR fallback found Street Address: %r", value)
            if addr_display_blank:
                fields[addr_display_key] = value
            if addr_snake_blank:
                fields[addr_snake_key] = value
        else:
            logger.info("OCR fallback could not locate a Street Address line.")

    if needs_phone:
        phone = extract_cell_phone_from_ocr(ocr_text)
        if phone:
            logger.info("OCR fallback found Cell Phone: %r", phone)
            if phone_display_blank:
                fields[phone_display_key] = phone
            if phone_snake_blank:
                fields[phone_snake_key] = phone
        else:
            logger.info("OCR fallback could not locate a Cell Phone number.")

    return fields
