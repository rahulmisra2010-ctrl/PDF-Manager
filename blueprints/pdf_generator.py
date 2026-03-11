"""
blueprints/pdf_generator.py — PDF Generation Helper for PDF-Manager.

Provides the ``generate_updated_pdf`` helper that fills extracted field
values into a copy of the original PDF and writes the result to the
configured export directory.

Usage::

    from blueprints.pdf_generator import generate_updated_pdf

    result = generate_updated_pdf(doc_id=5, selected_fields={"Name": "John Smith"})
    # {"ok": True, "path": "/exports/form_updated.pdf", "filename": "form_updated.pdf"}
"""

import io
import os

from flask import current_app
from werkzeug.utils import secure_filename

from models import Document, ExtractedField


def generate_updated_pdf(doc_id: int, selected_fields: dict | None = None) -> dict:
    """Generate a PDF with corrected / filled-in field values.

    Reads the original PDF for *doc_id*, overlays the current (edited)
    ``ExtractedField`` values plus any overrides from *selected_fields*, and
    writes the result to the configured ``PDF_EXPORT_FOLDER``.

    Args:
        doc_id:          Database ID of the target document.
        selected_fields: Optional ``{field_name: value}`` overrides that take
                         priority over the database values.

    Returns::

        {
            "ok": True,
            "path": "/absolute/path/to/updated.pdf",
            "filename": "original_updated.pdf",
        }

    Raises:
        FileNotFoundError: If the source PDF is missing from disk.
        RuntimeError:      If PDFService is unavailable or export fails.
    """
    doc = Document.query.get_or_404(doc_id)

    if not os.path.exists(doc.file_path):
        raise FileNotFoundError(f"Source PDF not found: {doc.file_path}")

    # Lazy-import PDFService (backend/ must be on sys.path)
    try:
        import sys as _sys
        _backend = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "backend"
        )
        if _backend not in _sys.path:
            _sys.path.append(_backend)
        from services.pdf_service import PDFService  # type: ignore[import]
        svc = PDFService()
    except ImportError as exc:
        raise RuntimeError(f"PDFService unavailable: {exc}") from exc

    # Build field list from DB, then apply selected_fields overrides
    db_fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    overrides = selected_fields or {}

    field_dicts = []
    for f in db_fields:
        value = overrides.get(f.field_name, f.value or "")
        field_dicts.append({
            "field_name": f.field_name,
            "value": value,
            "page_number": f.page_number or 1,
            "bounding_box": (
                {
                    "x0": f.bbox_x,
                    "y0": f.bbox_y,
                    "x1": f.bbox_x + (f.bbox_width or 0),
                    "y1": f.bbox_y + (f.bbox_height or 0),
                }
                if f.bbox_x is not None and f.bbox_y is not None
                else None
            ),
        })

    buf = io.BytesIO()
    try:
        svc._export_as_pdf(doc.file_path, field_dicts, buf)
    except Exception as exc:
        raise RuntimeError(f"PDF export failed: {exc}") from exc

    buf.seek(0)
    stem = os.path.splitext(doc.filename)[0]
    dest_dir = current_app.config.get(
        "PDF_EXPORT_FOLDER",
        current_app.config.get("EXPORT_FOLDER", "exports"),
    )
    os.makedirs(dest_dir, exist_ok=True)
    out_filename = secure_filename(f"{stem}_updated.pdf")
    dest_path = os.path.join(dest_dir, out_filename)

    with open(dest_path, "wb") as fh:
        fh.write(buf.read())

    return {
        "ok": True,
        "path": dest_path,
        "filename": out_filename,
    }
