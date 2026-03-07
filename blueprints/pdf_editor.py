"""
blueprints/pdf_editor.py — Live PDF Editor blueprint.

Routes
------
GET  /live-pdf/                         — redirect to document list
GET  /live-pdf/upload                   — redirect to PDF upload
GET  /live-pdf/<doc_id>                 — main live editor interface
POST /live-pdf/<doc_id>/update-field    — AJAX: update a single field value
POST /live-pdf/<doc_id>/save            — save all field changes
POST /live-pdf/<doc_id>/extract         — re-run OCR field extraction
POST /live-pdf/<doc_id>/approve         — approve document (Verifier+)
POST /live-pdf/<doc_id>/reject          — reject document (Verifier+)
"""

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
    url_for,
)
from flask_login import current_user, login_required

from models import AuditLog, Document, ExtractedField, FieldEditHistory, db

pdf_editor_bp = Blueprint(
    "pdf_editor",
    __name__,
    template_folder="../templates/live_pdf",
)


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

@pdf_editor_bp.route("/")
@login_required
def index():
    """Redirect to the document list."""
    return redirect(url_for("pdf.list_documents"))


@pdf_editor_bp.route("/upload")
@login_required
def upload():
    """Redirect to the standard PDF upload page."""
    return redirect(url_for("pdf.upload"))


@pdf_editor_bp.route("/<int:doc_id>")
@login_required
def editor(doc_id: int):
    """Render the live PDF editor for a given document."""
    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()

    field_data = [
        {
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
        }
        for f in fields
    ]

    pdf_url = url_for("pdf.serve_pdf", doc_id=doc_id)
    return render_template(
        "editor.html",
        doc=doc,
        fields=field_data,
        pdf_url=pdf_url,
    )


@pdf_editor_bp.route("/<int:doc_id>/update-field", methods=["POST"])
@login_required
def update_field(doc_id: int):
    """AJAX endpoint: update a single extracted field value.

    Expects JSON body::

        {"field_id": 42, "value": "new value"}

    Returns JSON::

        {"ok": true, "field_id": 42, "value": "new value"}
    """
    Document.query.get_or_404(doc_id)  # ensure doc exists
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


@pdf_editor_bp.route("/<int:doc_id>/save", methods=["POST"])
@login_required
def save(doc_id: int):
    """Save all field changes submitted from the editor form."""
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

    return redirect(url_for("pdf_editor.editor", doc_id=doc_id))


@pdf_editor_bp.route("/<int:doc_id>/extract", methods=["POST"])
@login_required
def extract(doc_id: int):
    """Re-run OCR and field mapping for the document."""
    doc = Document.query.get_or_404(doc_id)
    svc = _get_pdf_service()

    if svc is None:
        flash("PDF service unavailable — check backend dependencies.", "danger")
        return redirect(url_for("pdf_editor.editor", doc_id=doc_id))

    try:
        if not os.path.exists(doc.file_path):
            flash("Extraction failed: uploaded file not found on disk.", "danger")
            return redirect(url_for("pdf_editor.editor", doc_id=doc_id))

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
        flash("Field extraction complete.", "success")
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(
            "Extraction failed for doc %s: %s", doc_id, exc
        )
        flash(f"Extraction failed: {exc}", "danger")

    return redirect(url_for("pdf_editor.editor", doc_id=doc_id))


@pdf_editor_bp.route("/<int:doc_id>/approve", methods=["POST"])
@login_required
@_require_role("Admin", "Verifier")
def approve(doc_id: int):
    """Mark the document as approved."""
    doc = Document.query.get_or_404(doc_id)
    doc.status = "approved"
    _log(current_user.id, "approve", "document", str(doc_id))
    db.session.commit()
    flash("Document approved.", "success")
    return redirect(url_for("pdf_editor.editor", doc_id=doc_id))


@pdf_editor_bp.route("/<int:doc_id>/reject", methods=["POST"])
@login_required
@_require_role("Admin", "Verifier")
def reject(doc_id: int):
    """Mark the document as rejected."""
    doc = Document.query.get_or_404(doc_id)
    doc.status = "rejected"
    _log(current_user.id, "reject", "document", str(doc_id))
    db.session.commit()
    flash("Document rejected.", "warning")
    return redirect(url_for("pdf_editor.editor", doc_id=doc_id))


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
