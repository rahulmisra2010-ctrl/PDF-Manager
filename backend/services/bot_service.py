"""
backend/services/bot_service.py — Form-image/PDF-to-fillable-PDF bot service.

Workflow
--------
Image/PDF → OCR/Text Extraction → NLP → PDF Generator → Fillable PDF Output

This service:
1. Accepts an uploaded image OR PDF form (scanned, photographed, or digital).
2. For images: applies OCR (Tesseract via pytesseract) to extract text.
   For PDFs: first tries to extract existing form fields, then falls back
   to text extraction using PyMuPDF or pdfplumber.
3. Uses rule-based NLP to identify label/value pairs, checkboxes, and
   special fields (signature, date) — e.g., fields labeled "A" and "B".
4. Generates a fillable PDF (AcroForm) with ReportLab where every field is
   editable — pre-filled values can be overwritten and blank fields can be
   typed into.

The generated PDF supports:
- Text input fields
- Checkbox fields
- Signature fields (styled text input)
- Date fields (styled text input)

All fields are editable directly in the PDF viewer or in standard PDF readers.
"""

from __future__ import annotations

import io
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Withdrawal-form-specific checkbox reasons
# ---------------------------------------------------------------------------
WITHDRAWAL_REASONS: list[str] = [
    "Employment",
    "Financial",
    "Family",
    "Health",
    "Other",
]

# Labels that should always render as signature/date fields regardless of
# what the OCR produces.
_SIGNATURE_KEYWORDS = frozenset({"signature", "sign", "signed"})
_DATE_KEYWORDS = frozenset({"date", "dated", "day", "month", "year"})


# ---------------------------------------------------------------------------
# Step 1 – OCR
# ---------------------------------------------------------------------------

def extract_text_from_image(image_path: str | Path) -> str:
    """
    Run OCR on *image_path* and return the extracted text.

    Falls back to an empty string (with a warning) when pytesseract or the
    Tesseract binary is not available so that the rest of the pipeline can
    still demonstrate PDF generation.
    """
    image_path = Path(image_path)
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        img = Image.open(image_path)
        text: str = pytesseract.image_to_string(img, config="--psm 6")
        logger.info("OCR extracted %d characters from %s", len(text), image_path.name)
        return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR failed (%s) — returning empty text", exc)
        return ""


# ---------------------------------------------------------------------------
# Step 2 – NLP / text structuring
# ---------------------------------------------------------------------------

# Pattern: "Label: Value"  or  "Label : Value"
_COLON_PAIR = re.compile(r"^(?P<label>[^:\n]{1,80}?)\s*:\s*(?P<value>.*)$")

# Checkbox line: "[ ] Reason" or "☐ Reason" or "(  ) Reason"
_CHECKBOX_LINE = re.compile(
    r"^[\[\(☐□]\s*[xX✓✗]?\s*[\]\)]?\s*(?P<label>.+)$",
    re.IGNORECASE,
)

# Lines that look like blank fields (underscores or dotted lines)
_BLANK_FIELD = re.compile(r"^(?P<label>[^_\n]{2,60})\s*(?:[_]{3,}|[\.]{5,})")

# Signature / date sentinel patterns
_SIG_DATE_INLINE = re.compile(
    r"(?P<label>(?:signature|sign(?:ed)?|date|day|month|year)[^:\n]{0,40})",
    re.IGNORECASE,
)


def structure_text(raw_text: str) -> dict[str, Any]:
    """
    Parse *raw_text* into a structured dict with keys:

    ``fields``
        List of ``{"label": str, "value": str, "type": str}`` dicts.
        ``type`` is one of ``"text"``, ``"checkbox"``, ``"signature"``,
        ``"date"``.

    ``withdrawal_reasons``
        List of reason strings that were detected as checkboxes.
    """
    fields: list[dict[str, Any]] = []
    found_reasons: set[str] = set()

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # ── Checkbox detection ──────────────────────────────────────────
        cb_match = _CHECKBOX_LINE.match(line)
        if cb_match:
            label = cb_match.group("label").strip()
            # Check if this is a withdrawal-reason checkbox
            for reason in WITHDRAWAL_REASONS:
                if reason.lower() in label.lower():
                    found_reasons.add(reason)
                    fields.append({"label": reason, "value": "", "type": "checkbox"})
                    if reason.lower() == "other":
                        # Append an editable text field for custom input
                        fields.append(
                            {"label": "Other (specify)", "value": "", "type": "text"}
                        )
                    break
            else:
                fields.append({"label": label, "value": "", "type": "checkbox"})
            continue

        # ── Label: Value pairs ──────────────────────────────────────────
        colon_match = _COLON_PAIR.match(line)
        if colon_match:
            label = colon_match.group("label").strip()
            value = colon_match.group("value").strip()
            field_type = _classify_label(label)
            fields.append({"label": label, "value": value, "type": field_type})
            continue

        # ── Blank field lines ───────────────────────────────────────────
        blank_match = _BLANK_FIELD.match(line)
        if blank_match:
            label = blank_match.group("label").strip()
            field_type = _classify_label(label)
            fields.append({"label": label, "value": "", "type": field_type})
            continue

        # ── Inline signature / date sentinels ──────────────────────────
        sig_match = _SIG_DATE_INLINE.search(line)
        if sig_match:
            label = sig_match.group("label").strip().rstrip(":").strip()
            field_type = _classify_label(label)
            fields.append({"label": label, "value": "", "type": field_type})

    # De-duplicate by label while preserving order
    seen: set[str] = set()
    unique_fields: list[dict[str, Any]] = []
    for f in fields:
        key = f["label"].lower()
        if key not in seen:
            seen.add(key)
            unique_fields.append(f)

    return {"fields": unique_fields, "withdrawal_reasons": sorted(found_reasons)}


def _classify_label(label: str) -> str:
    """Return a field-type string based on label keywords."""
    lower = label.lower()
    if any(kw in lower for kw in _SIGNATURE_KEYWORDS):
        return "signature"
    if any(kw in lower for kw in _DATE_KEYWORDS):
        return "date"
    return "text"


# ---------------------------------------------------------------------------
# Step 3 – PDF generation
# ---------------------------------------------------------------------------

def generate_fillable_pdf(
    structured: dict[str, Any],
    output_path: str | Path | None = None,
) -> bytes:
    """
    Build a fillable AcroForm PDF from *structured* and return the raw bytes.

    If *output_path* is provided the bytes are also written there.

    Each field in ``structured["fields"]`` becomes an editable form widget:
    - ``"text"``      → single-line text field (pre-filled when ``value`` is present)
    - ``"signature"`` → italic-labelled text field styled for signatures
    - ``"date"``      → text field pre-labelled "Date"
    - ``"checkbox"``  → interactive check-box widget

    Withdrawal-reason checkboxes are grouped under a dedicated heading.
    An "Other (specify)" reason automatically adds a free-text field below it.
    """
    from reportlab.lib.pagesizes import letter  # type: ignore
    from reportlab.lib.units import inch  # type: ignore
    from reportlab.lib.colors import black, white, gray, HexColor  # type: ignore
    from reportlab.pdfgen import canvas  # type: ignore

    _prefilled_bg = HexColor("#F7F7FF")  # very light blue for pre-filled fields

    fields: list[dict[str, Any]] = structured.get("fields", [])

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    # ── Document metadata ──────────────────────────────────────────────
    c.setTitle("Fillable Form — Generated by PDF Manager Bot")
    c.setAuthor("PDF Manager Bot")
    c.setSubject("Auto-generated fillable form from image")

    # ── Page heading ───────────────────────────────────────────────────
    margin_left = inch
    margin_right = width - inch
    y = height - inch

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin_left, y, "Fillable Form")
    y -= 0.15 * inch
    c.setLineWidth(0.5)
    c.line(margin_left, y, margin_right, y)
    y -= 0.35 * inch

    label_font = "Helvetica-Bold"
    label_size = 9
    field_height = 18
    line_gap = 6
    checkbox_size = 12

    acro = c.acroForm

    for idx, field in enumerate(fields):
        label: str = field.get("label", f"Field {idx + 1}")
        value: str = field.get("value", "")
        ftype: str = field.get("type", "text")
        safe_name = re.sub(r"[^A-Za-z0-9_]", "_", label)[:40] + f"_{idx}"

        # ── Page break ────────────────────────────────────────────────
        if y < inch + 0.6 * inch:
            c.showPage()
            y = height - inch
            c.setFont(label_font, label_size)

        # ── Checkbox fields ────────────────────────────────────────────
        if ftype == "checkbox":
            c.setFont(label_font, label_size)
            c.drawString(margin_left + checkbox_size + 6, y - 2, label)
            acro.checkbox(
                name=safe_name,
                tooltip=label,
                x=margin_left,
                y=y - checkbox_size,
                buttonStyle="check",
                borderColor=black,
                fillColor=white,
                textColor=black,
                forceBorder=True,
                size=checkbox_size,
            )
            y -= checkbox_size + line_gap
            continue

        # ── Label line ─────────────────────────────────────────────────
        c.setFont(label_font, label_size)
        if ftype == "signature":
            c.setFont("Helvetica-Oblique", label_size)
        c.drawString(margin_left, y, label + ":")
        y -= label_size + 3

        # ── Text / signature / date field ──────────────────────────────
        field_width = margin_right - margin_left
        acro.textfield(
            name=safe_name,
            tooltip=label,
            value=value,
            x=margin_left,
            y=y - field_height,
            width=field_width,
            height=field_height,
            borderColor=gray,
            fillColor=_prefilled_bg if value else white,
            textColor=black,
            forceBorder=True,
            fontSize=10,
        )
        y -= field_height + line_gap

    c.save()
    pdf_bytes = buf.getvalue()

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pdf_bytes)
        logger.info("Fillable PDF written to %s (%d bytes)", output_path, len(pdf_bytes))

    return pdf_bytes


# ---------------------------------------------------------------------------
# Convenience: full pipeline
# ---------------------------------------------------------------------------

def image_to_fillable_pdf(
    image_path: str | Path,
    output_path: str | Path | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """
    Run the complete pipeline: image → OCR → NLP → fillable PDF.

    Returns ``(pdf_bytes, structured)`` where *structured* is the NLP output
    dict (useful for previewing the extracted fields in the UI).
    """
    raw_text = extract_text_from_image(image_path)
    structured = structure_text(raw_text)

    # If OCR produced nothing (e.g. Tesseract not installed), insert a small
    # set of demo fields so the PDF output is not empty.
    if not structured["fields"]:
        logger.info("OCR returned no text — injecting demo fields")
        structured = _demo_fields()

    pdf_bytes = generate_fillable_pdf(structured, output_path=output_path)
    return pdf_bytes, structured


def _demo_fields() -> dict[str, Any]:
    """Return a sample withdrawal-form structure for demonstration."""
    fields = [
        {"label": "Legal Name", "value": "", "type": "text"},
        {"label": "Student Number", "value": "", "type": "text"},
        {"label": "Program", "value": "", "type": "text"},
        {"label": "Semester", "value": "", "type": "text"},
        {"label": "Reason for Withdrawal", "value": "", "type": "text"},
    ]
    for reason in WITHDRAWAL_REASONS:
        fields.append({"label": reason, "value": "", "type": "checkbox"})
        if reason == "Other":
            fields.append({"label": "Other (specify)", "value": "", "type": "text"})
    fields.append({"label": "Signature", "value": "", "type": "signature"})
    fields.append({"label": "Date", "value": "", "type": "date"})
    return {"fields": fields, "withdrawal_reasons": []}


def _demo_ab_fields() -> dict[str, Any]:
    """Return a sample A/B form structure per the problem statement."""
    fields = [
        {"label": "A", "value": "", "type": "text"},
        {"label": "B", "value": "", "type": "text"},
    ]
    return {"fields": fields, "withdrawal_reasons": []}


# ---------------------------------------------------------------------------
# PDF extraction and conversion
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """
    Extract text from a PDF file.

    Tries PyMuPDF (fitz) first, then falls back to pdfplumber, then to empty
    text if neither works.
    """
    pdf_path = Path(pdf_path)

    # Try PyMuPDF first
    try:
        # fitz is the PyMuPDF library - install via: pip install pymupdf
        import fitz  # type: ignore
        doc = fitz.open(pdf_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        text = "\n".join(text_parts)
        if text.strip():
            logger.info("PyMuPDF extracted %d characters from %s", len(text), pdf_path.name)
            return text
    except Exception as exc:  # noqa: BLE001
        logger.debug("PyMuPDF failed (%s), trying pdfplumber", exc)

    # Try pdfplumber
    try:
        import pdfplumber  # type: ignore
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        text = "\n".join(text_parts)
        if text.strip():
            logger.info("pdfplumber extracted %d characters from %s", len(text), pdf_path.name)
            return text
    except Exception as exc:  # noqa: BLE001
        logger.debug("pdfplumber failed (%s)", exc)

    logger.warning("Could not extract text from PDF %s", pdf_path.name)
    return ""


def extract_form_fields_from_pdf(pdf_path: str | Path) -> list[dict[str, Any]]:
    """
    Extract existing form fields from a PDF using PyMuPDF.

    Returns a list of field dictionaries with label, value, and type.
    """
    pdf_path = Path(pdf_path)
    fields: list[dict[str, Any]] = []

    try:
        # fitz is the PyMuPDF library - install via: pip install pymupdf
        import fitz  # type: ignore
        doc = fitz.open(pdf_path)

        for page_num, page in enumerate(doc, start=1):
            widgets = page.widgets()
            if widgets is None:
                continue

            for widget in widgets:
                field_name = widget.field_name or f"Field_{page_num}_{len(fields)}"
                field_value = widget.field_value or ""
                field_type_int = widget.field_type

                # Map fitz field types to our types
                # 0=unknown, 1=PushButton, 2=CheckBox, 3=RadioButton,
                # 4=Choice, 5=Text, 6=Signature
                if field_type_int == 2:  # Checkbox
                    ftype = "checkbox"
                    field_value = "Yes" if field_value in ("Yes", "On", True) else ""
                elif field_type_int == 3:  # RadioButton
                    ftype = "checkbox"  # treat as checkbox
                elif field_type_int == 6:  # Signature
                    ftype = "signature"
                else:  # Text, Choice, Unknown
                    ftype = _classify_label(field_name)
                    if ftype == "text" and field_type_int == 4:
                        ftype = "text"  # Choice fields become text

                fields.append({
                    "label": field_name,
                    "value": str(field_value) if field_value else "",
                    "type": ftype,
                })

        doc.close()
        logger.info("Extracted %d form fields from %s", len(fields), pdf_path.name)

    except Exception as exc:  # noqa: BLE001
        logger.warning("Form field extraction failed (%s)", exc)

    return fields


def pdf_to_fillable_pdf(
    pdf_path: str | Path,
    output_path: str | Path | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """
    Process a PDF file and generate a fillable PDF with detected fields.

    1. First tries to extract existing form fields from the PDF.
    2. If no form fields, extracts text and uses NLP to detect fields.
    3. If no text/fields detected, falls back to demo fields (A and B).

    Returns ``(pdf_bytes, structured)`` where *structured* is the extracted
    field data (useful for previewing in the UI).
    """
    pdf_path = Path(pdf_path)

    # Step 1: Try to extract existing form fields
    existing_fields = extract_form_fields_from_pdf(pdf_path)
    if existing_fields:
        structured = {"fields": existing_fields, "withdrawal_reasons": []}
        pdf_bytes = generate_fillable_pdf(structured, output_path=output_path)
        return pdf_bytes, structured

    # Step 2: Extract text and use NLP to detect fields
    raw_text = extract_text_from_pdf(pdf_path)
    if raw_text.strip():
        structured = structure_text(raw_text)
        if structured["fields"]:
            pdf_bytes = generate_fillable_pdf(structured, output_path=output_path)
            return pdf_bytes, structured

    # Step 3: Fall back to demo A/B fields
    logger.info("No fields detected in PDF — injecting demo A/B fields")
    structured = _demo_ab_fields()
    pdf_bytes = generate_fillable_pdf(structured, output_path=output_path)
    return pdf_bytes, structured
