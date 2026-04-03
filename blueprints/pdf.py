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
import hashlib
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

from models import AuditLog, Document, DocumentSchema, ExtractedField, db

pdf_bp = Blueprint("pdf", __name__, template_folder="../templates/pdf")

# ---------------------------------------------------------------------------
# Template-key computation
# ---------------------------------------------------------------------------

# Number of raw file bytes read when PyMuPDF is unavailable (fallback hashing).
# 4 KB is large enough to cover the PDF header and the start of the first
# page's content stream, which remains stable across differently-filled copies
# of the same blank form.
_FALLBACK_READ_BYTES = 4096


def compute_template_key(file_path: str) -> str:
    """Return a stable sha256 hex identifier for the PDF *template* structure.

    The key is derived from the first page's **layout** (text-block bounding
    boxes + drawing primitives), not from the actual text content.  This means
    two filled copies of the same blank form produce the same key, while two
    structurally different forms (e.g. address-book vs. withdrawal form)
    produce different keys.

    Falls back to a sha256 of the first 4 KB of file bytes when PyMuPDF is
    unavailable (e.g. in unit tests that pass ``/tmp/fake.pdf``).
    """
    try:
        import fitz  # type: ignore[import]  # PyMuPDF

        with fitz.open(file_path) as pdf_doc:
            page_count = len(pdf_doc)
            if page_count == 0:
                raise ValueError("Empty PDF")
            page = pdf_doc[0]

            # Text block bounding boxes — positions only, ignore text content
            blocks = page.get_text("blocks")  # (x0,y0,x1,y1,text,blk_no,blk_type)
            bbox_parts = [
                f"{b[0]:.1f},{b[1]:.1f},{b[2]:.1f},{b[3]:.1f}"
                for b in sorted(blocks, key=lambda b: (round(b[1]), round(b[0])))
                if b[6] == 0  # block_type 0 = text
            ]

            # Drawing primitives (lines / rectangles) — structural skeleton
            drawings = page.get_drawings() or []
            draw_parts = [
                f"{d['rect'].x0:.1f},{d['rect'].y0:.1f},"
                f"{d['rect'].x1:.1f},{d['rect'].y1:.1f}"
                for d in sorted(
                    drawings,
                    key=lambda d: (round(d["rect"].y0), round(d["rect"].x0)),
                )
            ]

            payload = (
                f"pages={page_count}"
                f"|blocks={'|'.join(bbox_parts)}"
                f"|draws={'|'.join(draw_parts)}"
            )
    except Exception:
        # Fallback: hash the first _FALLBACK_READ_BYTES of raw file bytes.
        # 4 KB is enough to capture PDF header metadata and the start of the
        # first page's cross-reference structure, which is stable across
        # different filled copies of the same blank form.
        try:
            with open(file_path, "rb") as fh:
                raw = fh.read(_FALLBACK_READ_BYTES)
            payload = raw.hex()
        except OSError:
            payload = os.path.basename(file_path)

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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

        # Compute stable template identifier from the PDF layout structure.
        tpl_key = compute_template_key(file_path)

        doc = Document(
            filename=safe_name,
            file_path=file_path,
            status="uploaded",
            uploaded_by=current_user.id,
            file_size=len(content),
            template_key=tpl_key,
        )
        db.session.add(doc)
        db.session.flush()  # get doc.id before commit
        current_app.logger.info(
            "Uploaded '%s' (doc %s) — template_key=%s", safe_name, doc.id, tpl_key
        )
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
    schema = DocumentSchema.query.filter_by(document_id=doc_id).first()
    return render_template("pdf/detail.html", doc=doc, fields=fields, schema=schema)


def _ensure_backend_on_path() -> None:
    """Add backend/ directory to sys.path if not already present."""
    _here = os.path.dirname(os.path.abspath(__file__))
    _backend = os.path.abspath(os.path.join(_here, "..", "backend"))
    if _backend not in sys.path:
        sys.path.insert(0, _backend)


@pdf_bp.route("/<int:doc_id>/extract", methods=["POST"])
@login_required
def extract(doc_id: int):
    """Run extraction on the document.

    Strategy:
    1. Try dynamic label/value discovery (works for any PDF/image type).
       a. If no per-document schema exists yet, create one from discovered labels.
       b. If a schema already exists, map discovered labels to it using exact,
          normalised, and fuzzy matching so the field list stays stable.
    2. If dynamic extraction yields no pairs AND this document has no schema yet,
       fall back to the address-book mapping (legacy behaviour) for address-book
       PDFs.  Documents that already have a schema keep their existing fields.
    """
    doc = Document.query.get_or_404(doc_id)

    if not os.path.exists(doc.file_path):
        flash("Extraction failed: uploaded file not found on disk.", "danger")
        return redirect(url_for("pdf.detail", doc_id=doc_id))

    _ensure_backend_on_path()

    # ------------------------------------------------------------------
    # 1. Dynamic extraction (preferred)
    # ------------------------------------------------------------------
    dynamic_pairs: list[dict] = []
    dyn_exc_msg: str = ""
    try:
        from services.dynamic_extraction import (  # type: ignore[import]
            create_schema_from_pairs,
            extract_dynamic_fields,
            map_pairs_to_schema,
        )
        dynamic_pairs = extract_dynamic_fields(doc.file_path, page_index=0)
    except Exception as _dyn_exc:
        dyn_exc_msg = str(_dyn_exc)
        current_app.logger.warning(
            "Dynamic extraction failed for doc %s: %s", doc_id, _dyn_exc
        )

    if dynamic_pairs:
        try:
            # Load or create the per-document schema
            schema = DocumentSchema.query.filter_by(document_id=doc_id).first()
            if schema is None:
                # First extraction — build schema from discovered labels.
                # Stamp the schema with this document's template_key so it is
                # never accidentally reused for a document with a different
                # template structure.
                schema = DocumentSchema(
                    document_id=doc_id,
                    template_key=doc.template_key,
                )
                schema.labels = create_schema_from_pairs(dynamic_pairs)
                db.session.add(schema)
                pairs_to_save = dynamic_pairs
                current_app.logger.info(
                    "Created new schema for doc %s (tpl=%s): %d labels",
                    doc_id, doc.template_key or "legacy", len(schema.labels),
                )
            else:
                # Re-extraction — map to existing schema.
                # If the stored schema has no template_key (legacy row), update
                # it now so it benefits from isolation going forward.
                if schema.template_key is None and doc.template_key is not None:
                    schema.template_key = doc.template_key
                pairs_to_save = map_pairs_to_schema(dynamic_pairs, schema.labels)
                current_app.logger.info(
                    "Mapped %d discovered pair(s) to schema (%d labels) for doc %s",
                    len(dynamic_pairs), len(schema.labels), doc_id,
                )

            ExtractedField.query.filter_by(document_id=doc_id).delete()

            for pair in pairs_to_save:
                # extract_dynamic_fields uses 'label'; map_pairs_to_schema
                # also uses 'label'.  The 'field_name' fallback handles any
                # legacy dicts that may use the alternative key.
                label = pair.get("label") or pair.get("field_name", "")
                bbox = pair.get("bbox") or {}
                field = ExtractedField(
                    document_id=doc_id,
                    field_name=label,
                    value=pair.get("value", ""),
                    confidence=pair.get("confidence", 1.0),
                    page_number=pair.get("page_number", 1),
                    bbox_x=bbox.get("x"),
                    bbox_y=bbox.get("y"),
                    bbox_width=bbox.get("width"),
                    bbox_height=bbox.get("height"),
                )
                db.session.add(field)

            # Determine page count
            try:
                import fitz  # type: ignore[import]
                with fitz.open(doc.file_path) as _fitz_doc:
                    doc.page_count = len(_fitz_doc)
            except Exception:
                doc.page_count = 1

            doc.status = "extracted"
            _log(current_user.id, "extract", "document", str(doc_id), "dynamic")
            db.session.commit()
            flash(
                f"Extraction complete — {len(pairs_to_save)} field(s) found.",
                "success",
            )
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception(
                "Error saving dynamic fields for doc %s: %s", doc_id, exc
            )
            flash(f"Extraction failed while saving fields: {exc}", "danger")

        return redirect(url_for("pdf.detail", doc_id=doc_id))

    # ------------------------------------------------------------------
    # Dynamic extraction returned no pairs.
    # If this document already has a schema, keep existing fields unchanged.
    # ------------------------------------------------------------------
    existing_schema = DocumentSchema.query.filter_by(document_id=doc_id).first()
    if existing_schema is not None:
        msg = "No new fields discovered"
        if dyn_exc_msg:
            msg += f" ({dyn_exc_msg})"
        flash(f"{msg} — keeping existing extracted fields.", "info")
        return redirect(url_for("pdf.detail", doc_id=doc_id))

    # ------------------------------------------------------------------
    # 2. No fields found — report gracefully without applying a global schema
    # ------------------------------------------------------------------
    # The previous behaviour fell back to an address-book field mapper here,
    # which silently wrote generic field names (Name, Street Address, Cell
    # Phone, etc.) into the ExtractedField table for ANY document type.  That
    # caused cross-document/template leakage: opening a non-address-book PDF
    # in the AI view would show address-book fields that never belonged to it.
    #
    # The correct fix is document/template isolation: only store fields that
    # were actually discovered in THIS document's content.  If dynamic
    # extraction found nothing, we keep any existing fields and tell the user.
    # Address-book PDFs have their own dedicated blueprint and extraction flow
    # (blueprints/address_book.py) which is the right place for that mapping.
    msg = "No fields could be discovered in this document"
    if dyn_exc_msg:
        msg += f" ({dyn_exc_msg})"
    flash(
        f"{msg}. Open the AI Extraction view (the \u201cAI Extract\u201d button on the document page) "
        "to annotate fields manually.",
        "info",
    )
    current_app.logger.info(
        "extract: doc=%s — dynamic extraction found no pairs; "
        "skipping address-book fallback to prevent cross-template field leakage.",
        doc_id,
    )
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
