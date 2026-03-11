"""
blueprints/pdf.py — PDF management blueprint.

Routes
------
GET  /pdf/                          — list uploaded documents
GET  /pdf/upload                    — render upload form
POST /pdf/upload                    — handle PDF upload
POST /pdf/<id>/extract              — run OCR + field mapping
GET  /pdf/<id>                      — view document detail + fields
POST /pdf/<id>/edit                 — save edited field values
POST /pdf/<id>/approve              — mark document approved (Verifier+)
POST /pdf/<id>/reject               — mark document rejected (Verifier+)
GET  /pdf/<id>/export/<fmt>         — export fields as csv / xlsx / json / pdf
GET  /pdf/<id>/serve-pdf            — serve the raw PDF file (for PDF.js)
GET  /pdf/<id>/extract-overlay      — PDF viewer with editable field overlays
GET  /pdf/<id>/rag-extract          — split-layout RAG extraction UI
"""

import csv
import io
import json
import os
import sys
import uuid
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
from werkzeug.utils import secure_filename

from models import AuditLog, Document, ExtractedField, db

pdf_bp = Blueprint("pdf", __name__, template_folder="../templates/pdf")

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
# PDF service import — backend/ is added to sys.path by app.py
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

@pdf_bp.route("/")
@login_required
def list_documents():
    """List all uploaded documents, newest first."""
    docs = Document.query.order_by(Document.created_at.desc()).all()
    return render_template("pdf/list.html", documents=docs)


@pdf_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    """Upload a new PDF file."""
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("No file selected.", "warning")
            return redirect(request.url)

        if not file.filename.lower().endswith(".pdf"):
            flash("Only PDF files are accepted.", "danger")
            return redirect(request.url)

        content = file.read()
        max_bytes = current_app.config.get("MAX_CONTENT_LENGTH", 50 * 1024 * 1024)
        if len(content) > max_bytes:
            flash(f"File exceeds maximum size ({max_bytes // (1024*1024)} MB).", "danger")
            return redirect(request.url)

        upload_dir = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_dir, exist_ok=True)

        safe_name = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4()}_{safe_name}"
        file_path = os.path.join(upload_dir, unique_name)
        with open(file_path, "wb") as fh:
            fh.write(content)

        doc = Document(
            filename=safe_name,
            file_path=file_path,
            status="uploaded",
            uploaded_by=current_user.id,
            file_size=len(content),
        )
        db.session.add(doc)
        db.session.flush()  # get doc.id before commit
        _log(current_user.id, "upload", "document", str(doc.id), safe_name)
        db.session.commit()

        flash(f"'{safe_name}' uploaded successfully.", "success")
        return redirect(url_for("pdf.detail", doc_id=doc.id))

    return render_template("pdf/upload.html")


@pdf_bp.route("/<int:doc_id>")
@login_required
def detail(doc_id: int):
    """Show document details and extracted fields."""
    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    return render_template("pdf/detail.html", doc=doc, fields=fields)


@pdf_bp.route("/<int:doc_id>/extract", methods=["POST"])
@login_required
def extract(doc_id: int):
    """Run OCR extraction and address-book field mapping on the document."""
    doc = Document.query.get_or_404(doc_id)
    svc = _get_pdf_service()
    if svc is None:
        flash("PDF service is not available — check backend dependencies.", "danger")
        return redirect(url_for("pdf.detail", doc_id=doc_id))

    try:
        if not os.path.exists(doc.file_path):
            flash("Extraction failed: uploaded file not found on disk.", "danger")
            return redirect(url_for("pdf.detail", doc_id=doc_id))

        text, _tables, page_count = svc.extract(doc.file_path)
        mapped = svc.map_address_book_fields(text)

        # Remove previous fields and replace with freshly mapped ones
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
        flash("Extraction complete.", "success")
    except (OSError, RuntimeError, ValueError) as exc:
        db.session.rollback()
        flash(f"Extraction failed: {exc}", "danger")
    except ImportError as exc:
        db.session.rollback()
        flash(f"Extraction failed — missing dependency: {exc}", "danger")
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Unexpected error during extraction for doc %s", doc_id)
        flash(f"Extraction failed (unexpected error): {exc}", "danger")

    return redirect(url_for("pdf.detail", doc_id=doc_id))


@pdf_bp.route("/<int:doc_id>/edit", methods=["POST"])
@login_required
def edit(doc_id: int):
    """Save edited field values."""
    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()

    for field in fields:
        new_val = request.form.get(f"field_{field.id}", field.value)
        if new_val != field.value:
            if not field.is_edited:
                field.original_value = field.value
            field.value = new_val
            field.is_edited = True

    doc.status = "edited"
    _log(current_user.id, "edit", "document", str(doc_id))
    db.session.commit()
    flash("Fields saved.", "success")
    return redirect(url_for("pdf.detail", doc_id=doc_id))


@pdf_bp.route("/<int:doc_id>/approve", methods=["POST"])
@login_required
@_require_role("Admin", "Verifier")
def approve(doc_id: int):
    """Mark the document as approved."""
    doc = Document.query.get_or_404(doc_id)
    doc.status = "approved"
    _log(current_user.id, "approve", "document", str(doc_id))
    db.session.commit()
    flash("Document approved.", "success")
    return redirect(url_for("pdf.detail", doc_id=doc_id))


@pdf_bp.route("/<int:doc_id>/reject", methods=["POST"])
@login_required
@_require_role("Admin", "Verifier")
def reject(doc_id: int):
    """Mark the document as rejected."""
    doc = Document.query.get_or_404(doc_id)
    doc.status = "rejected"
    _log(current_user.id, "reject", "document", str(doc_id))
    db.session.commit()
    flash("Document rejected.", "warning")
    return redirect(url_for("pdf.detail", doc_id=doc_id))


@pdf_bp.route("/<int:doc_id>/export/<fmt>")
@login_required
def export(doc_id: int, fmt: str):
    """Export the document's extracted fields as CSV, XLSX, JSON, or PDF."""
    if fmt not in ("csv", "xlsx", "json", "pdf"):
        abort(400)

    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    rows = [{"field_name": f.field_name, "value": f.value} for f in fields]

    if fmt == "json":
        buf = io.BytesIO(json.dumps(rows, indent=2, ensure_ascii=False).encode("utf-8"))
        return send_file(
            buf,
            mimetype="application/json",
            as_attachment=True,
            download_name=f"{doc.filename}_fields.json",
        )

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["field_name", "value"])
        writer.writeheader()
        writer.writerows(rows)
        buf = io.BytesIO(output.getvalue().encode("utf-8"))
        return send_file(
            buf,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{doc.filename}_fields.csv",
        )

    if fmt == "pdf":
        svc = _get_pdf_service()
        if svc is None:
            flash("PDF service unavailable — cannot export as PDF.", "danger")
            return redirect(url_for("pdf.detail", doc_id=doc_id))
        if not os.path.exists(doc.file_path):
            flash("Export failed: source file not found on disk.", "danger")
            return redirect(url_for("pdf.detail", doc_id=doc_id))

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
                download_name=f"{stem}_fields.pdf",
            )
        except Exception as exc:
            current_app.logger.exception(
                "PDF export failed for doc %s: %s", doc_id, exc
            )
            flash("PDF export failed — please try again or contact support.", "danger")
            return redirect(url_for("pdf.detail", doc_id=doc_id))

    # xlsx
    try:
        import openpyxl
    except ImportError:
        flash("openpyxl is not installed — cannot export as XLSX.", "danger")
        return redirect(url_for("pdf.detail", doc_id=doc_id))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Fields"
    ws.append(["field_name", "value"])
    for row in rows:
        ws.append([row["field_name"], row["value"]])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"{doc.filename}_fields.xlsx",
    )


@pdf_bp.route("/<int:doc_id>/serve-pdf")
@login_required
def serve_pdf(doc_id: int):
    """Serve the raw PDF file so PDF.js can load it in the browser."""
    doc = Document.query.get_or_404(doc_id)
    if not os.path.exists(doc.file_path):
        abort(404)
    return send_file(doc.file_path, mimetype="application/pdf")


@pdf_bp.route("/<int:doc_id>/viewer")
@login_required
def pdf_viewer(doc_id: int):
    """Render a full-page PDF viewer using PDF.js.

    All pages are rendered sequentially in a scrollable container.
    Interactive form fields (PDF Widget annotations — text, checkbox,
    radio, select) are automatically detected from the PDF itself and
    rendered as editable HTML inputs placed exactly on top of the
    matching regions.  No pre-extracted field data is required.
    """
    doc = Document.query.get_or_404(doc_id)
    pdf_url = url_for("pdf.serve_pdf", doc_id=doc_id)
    return render_template("pdf/pdf_viewer.html", doc=doc, pdf_url=pdf_url)


@pdf_bp.route("/<int:doc_id>/extract-overlay")
@login_required
def extract_overlay(doc_id: int):
    """Render a PDF.js viewer with editable address-book field overlays.

    The nine address-book fields (Name, Street Address, City, State, Zip Code,
    Home Phone, Cell Phone, Work Phone, Email) are displayed as highlighted
    overlays on top of the PDF.  Each overlay is also mirrored in a backup
    editable form below the viewer.

    Bounding-box note
    -----------------
    ``PDFService.map_address_book_fields()`` returns ``{"field_name", "value"}``
    dicts but does *not* currently provide bounding-box coordinates.  Until real
    bounding boxes are available the template uses fixed demo positions on page 1.
    To extend this with real coordinates, update ``map_address_book_fields`` to
    include ``"bounding_box": {"page": 1, "x": …, "y": …, "w": …, "h": …}`` in
    each returned dict and pass them to the template via the ``fields`` list.
    """
    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()

    # Build a list of field dicts that the template can use.  Bounding boxes are
    # intentionally left as None here; the template falls back to demo positions.
    field_data = [
        {
            "id": f.id,
            "field_name": f.field_name,
            "value": f.value or "",
            "bounding_box": None,  # extend here when real coords are available
        }
        for f in fields
    ]

    pdf_url = url_for("pdf.serve_pdf", doc_id=doc_id)
    return render_template(
        "pdf/extract_overlay.html",
        doc=doc,
        fields=field_data,
        pdf_url=pdf_url,
    )


@pdf_bp.route("/<int:doc_id>/rag-extract")
@login_required
def rag_extract_view(doc_id: int):
    """Render the split-layout RAG extraction UI for a document."""
    doc = Document.query.get_or_404(doc_id)
    pdf_url = url_for("pdf.serve_pdf", doc_id=doc_id)
    return render_template("pdf/rag_extraction.html", doc=doc, pdf_url=pdf_url)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(user_id: int, action: str, resource_type: str, resource_id: str,
         details: str = "") -> None:
    """Insert an AuditLog entry (caller must commit the session)."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or None,
    )
    db.session.add(entry)
