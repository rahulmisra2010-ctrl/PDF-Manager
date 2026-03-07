"""
blueprints/address_book_live.py — Live Overlay Address Book PDF Editor blueprint.

Routes
------
GET  /address-book-live/                        — redirect to document list
GET  /address-book-live/upload                  — redirect to PDF upload
GET  /address-book-live/<doc_id>                — live overlay editor interface
POST /address-book-live/<doc_id>/update-field   — AJAX: update a single field value
POST /address-book-live/<doc_id>/save           — save all field changes
POST /address-book-live/<doc_id>/extract        — re-run OCR field extraction
GET  /address-book-live/<doc_id>/export         — download updated PDF
"""

import io
import os
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from models import AuditLog, Document, ExtractedField, FieldEditHistory, db

address_book_live_bp = Blueprint(
    "address_book_live",
    __name__,
    template_folder="../templates/address_book_live",
)

# ---------------------------------------------------------------------------
# Address-book field order
# ---------------------------------------------------------------------------

ADDRESS_BOOK_FIELDS = [
    "Name",
    "Street Address",
    "City",
    "State",
    "Zip Code",
    "Home Phone",
    "Cell Phone",
    "Work Phone",
    "Email",
]


# ---------------------------------------------------------------------------
# Role guard
# ---------------------------------------------------------------------------

def _require_role(*roles):
    """Decorator: abort 403 if the current user's role is not in *roles*."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------------------
# PDF service loader
# ---------------------------------------------------------------------------

def _get_pdf_service():
    """Lazily import PDFService (backend/ must be on sys.path)."""
    try:
        from services.pdf_service import PDFService  # type: ignore[import]
        return PDFService()
    except ImportError:
        return None
    except Exception:
        current_app.logger.exception("Failed to initialize PDFService")
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@address_book_live_bp.route("/")
@login_required
def index():
    """Redirect to the document list."""
    return redirect(url_for("pdf.list_documents"))


@address_book_live_bp.route("/upload")
@login_required
def upload():
    """Redirect to the standard PDF upload page."""
    return redirect(url_for("pdf.upload"))


@address_book_live_bp.route("/<int:doc_id>")
@login_required
def editor(doc_id: int):
    """Render the live overlay address book editor for a given document."""
    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()

    field_data = []
    for f in fields:
        field_data.append({
            "id": f.id,
            "field_name": f.field_name,
            "value": f.value or "",
            "confidence": round(f.confidence, 2),
            "is_edited": f.is_edited,
            "original_value": f.original_value or "",
            "page_number": f.page_number or 1,
            "bbox": {
                "x": f.bbox_x,
                "y": f.bbox_y,
                "width": f.bbox_width,
                "height": f.bbox_height,
            } if f.bbox_x is not None else None,
        })

    pdf_url = url_for("pdf.serve_pdf", doc_id=doc_id)
    return render_template(
        "editor.html",
        doc=doc,
        fields=field_data,
        pdf_url=pdf_url,
    )


@address_book_live_bp.route("/<int:doc_id>/update-field", methods=["POST"])
@login_required
def update_field(doc_id: int):
    """AJAX endpoint: update a single extracted field value.

    Expects JSON body::

        {"field_id": 42, "value": "new value"}

    Returns JSON::

        {"ok": true, "field_id": 42, "value": "new value"}
    """
    Document.query.get_or_404(doc_id)
    data = request.get_json(silent=True) or {}
    field_id = data.get("field_id")
    new_value = data.get("value", "")

    if field_id is None:
        return jsonify({"ok": False, "error": "field_id is required"}), 400

    field = ExtractedField.query.filter_by(
        id=field_id, document_id=doc_id
    ).first_or_404()

    if str(new_value) != (field.value or ""):
        history = FieldEditHistory(
            field_id=field.id,
            old_value=field.value,
            new_value=str(new_value),
            edited_by=current_user.id,
        )
        db.session.add(history)
        if not field.is_edited:
            field.original_value = field.value
        field.value = str(new_value)
        field.is_edited = True
        field.version += 1

        _log(current_user.id, "edit_field", "extracted_field", str(field_id))
        db.session.commit()

    return jsonify({"ok": True, "field_id": field.id, "value": field.value})


@address_book_live_bp.route("/<int:doc_id>/save", methods=["POST"])
@login_required
def save(doc_id: int):
    """Save all field changes submitted from the live editor form."""
    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()

    changed = 0
    for field in fields:
        new_val = request.form.get(f"field_{field.id}", field.value)
        if new_val != (field.value or ""):
            history = FieldEditHistory(
                field_id=field.id,
                old_value=field.value,
                new_value=new_val,
                edited_by=current_user.id,
            )
            db.session.add(history)
            if not field.is_edited:
                field.original_value = field.value
            field.value = new_val
            field.is_edited = True
            field.version += 1
            changed += 1

    if changed:
        doc.status = "edited"
        _log(current_user.id, "save_fields", "document", str(doc_id))
        db.session.commit()
        flash(f"{changed} field(s) saved successfully.", "success")
    else:
        flash("No changes detected.", "info")

    return redirect(url_for("address_book_live.editor", doc_id=doc_id))


@address_book_live_bp.route("/<int:doc_id>/extract", methods=["POST"])
@login_required
def extract(doc_id: int):
    """Re-run OCR and address book field mapping for the document."""
    doc = Document.query.get_or_404(doc_id)
    svc = _get_pdf_service()

    if svc is None:
        flash("PDF service unavailable — check backend dependencies.", "danger")
        return redirect(url_for("address_book_live.editor", doc_id=doc_id))

    try:
        if not os.path.exists(doc.file_path):
            flash("Extraction failed: uploaded file not found on disk.", "danger")
            return redirect(url_for("address_book_live.editor", doc_id=doc_id))

        text, _tables, page_count = svc.extract(doc.file_path)
        mapped = svc.map_address_book_fields(text)

        ExtractedField.query.filter_by(document_id=doc_id).delete()

        for item in mapped:
            field = ExtractedField(
                document_id=doc_id,
                field_name=item["field_name"],
                value=item["value"],
                confidence=1.0,
            )
            db.session.add(field)

        doc.status = "extracted"
        doc.page_count = page_count
        _log(current_user.id, "extract", "document", str(doc_id))
        db.session.commit()
        flash("Address book fields extracted successfully.", "success")
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(
            "Extraction failed for doc %s: %s", doc_id, exc
        )
        flash(f"Extraction failed: {exc}", "danger")

    return redirect(url_for("address_book_live.editor", doc_id=doc_id))


@address_book_live_bp.route("/<int:doc_id>/export")
@login_required
def export_pdf(doc_id: int):
    """Download an updated PDF with edited address book fields overlaid."""
    doc = Document.query.get_or_404(doc_id)
    svc = _get_pdf_service()

    if svc is None:
        flash("PDF service unavailable — cannot export.", "danger")
        return redirect(url_for("address_book_live.editor", doc_id=doc_id))

    if not os.path.exists(doc.file_path):
        flash("Export failed: source file not found on disk.", "danger")
        return redirect(url_for("address_book_live.editor", doc_id=doc_id))

    fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    field_dicts = [
        {
            "field_name": f.field_name,
            "value": f.value or "",
            "bbox_x": f.bbox_x,
            "bbox_y": f.bbox_y,
            "bbox_width": f.bbox_width,
            "bbox_height": f.bbox_height,
            "page_number": f.page_number or 1,
        }
        for f in fields
    ]

    buf = io.BytesIO()
    try:
        svc._export_as_pdf(doc.file_path, field_dicts, buf)
        buf.seek(0)
        stem = os.path.splitext(doc.filename)[0]
        _log(current_user.id, "export_pdf", "document", str(doc_id))
        db.session.commit()
        return send_file(
            buf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{stem}_live_address_book.pdf",
        )
    except Exception as exc:
        current_app.logger.exception(
            "PDF export failed for doc %s: %s", doc_id, exc
        )
        flash(f"PDF export failed: {exc}", "danger")
        return redirect(url_for("address_book_live.editor", doc_id=doc_id))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: str,
    details: str = "",
) -> None:
    """Insert an AuditLog entry (caller must commit the session)."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or None,
    )
    db.session.add(entry)
