"""
blueprints/address_book.py — Address Book PDF Editor blueprint.

Routes
------
GET  /address-book/                        — redirect to document list
GET  /address-book/upload                  — redirect to PDF upload
GET  /address-book/<doc_id>                — address book editor interface
POST /address-book/<doc_id>/update-field   — AJAX: update a single field value
POST /address-book/<doc_id>/save           — save all field changes
POST /address-book/<doc_id>/extract        — re-run OCR field extraction
POST /address-book/<doc_id>/apply-all      — apply AddressBook_v1 autofill logic
POST /address-book/<doc_id>/approve        — approve document (Verifier+)
POST /address-book/<doc_id>/reject         — reject document (Verifier+)
GET  /address-book/<doc_id>/export         — download updated PDF
"""

import csv
import io
import json
import os
import re
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

from models import AuditLog, Document, ExtractedField, FieldEditHistory, db

address_book_bp = Blueprint(
    "address_book",
    __name__,
    template_folder="../templates/address_book",
)

# ---------------------------------------------------------------------------
# Address-book field order for the form
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
# AddressBook_v1 template constants
# ---------------------------------------------------------------------------

# Keywords used to detect AddressBook_v1 documents (page-1 text/OCR)
ADDRESSBOOK_V1_KEYWORDS = [
    "address book",
    "street address",
    "cell phone",
    "zip code",
    "email",
]

# OCR confidence threshold below which a field is considered invalid
OCR_CONFIDENCE_THRESHOLD = 0.80

# If >= BLANK_THRESHOLD of the 9 template fields are invalid, treat doc as blank-ish
BLANK_THRESHOLD = 7

# Defaults from sample1 (used for autofill)
ADDRESSBOOK_V1_DEFAULTS = {
    "Name":           "Rahul Misra",
    "Street Address": "Sumoth pally, Durgamandir",
    "City":           "Asansol",
    "State":          "WB",
    "Zip Code":       "713301",
    "Cell Phone":     "7699888010",
    # Home Phone, Work Phone, Email: no defaults (leave as-is)
}

# Fixed fields: apply default when invalid even if document is not blank-ish
ADDRESSBOOK_V1_FIXED_FIELDS = {"Name", "State", "Cell Phone"}


# ---------------------------------------------------------------------------
# AddressBook_v1 field validation helpers
# ---------------------------------------------------------------------------

def _normalize_phone(value: str) -> str:
    """Strip all non-digit characters from a phone number string."""
    return re.sub(r"\D", "", value or "")


def _is_field_invalid(field_name: str, value: str, confidence: float) -> bool:
    """Return True if the field value is blank, low-confidence, or fails validation.

    A field is considered invalid when any of the following is true:
    * The value is blank (empty or whitespace-only).
    * ``confidence`` is below ``OCR_CONFIDENCE_THRESHOLD`` (0.80).
    * The value fails the field-specific regex/format check.
    """
    stripped = (value or "").strip()

    # Blank
    if not stripped:
        return True

    # Low OCR confidence
    if confidence < OCR_CONFIDENCE_THRESHOLD:
        return True

    # Field-specific format validation
    if field_name == "Zip Code":
        if not re.match(r"^\d{5,6}$", stripped):
            return True
    elif field_name in ("Home Phone", "Cell Phone", "Work Phone"):
        digits = _normalize_phone(stripped)
        if not re.match(r"^\d{10}$", digits):
            return True
    elif field_name == "Email":
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", stripped):
            return True

    return False


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

@address_book_bp.route("/")
@login_required
def index():
    """Redirect to the document list."""
    return redirect(url_for("pdf.list_documents"))


@address_book_bp.route("/upload")
@login_required
def upload():
    """Redirect to the standard PDF upload page."""
    return redirect(url_for("pdf.upload"))


@address_book_bp.route("/<int:doc_id>")
@login_required
def editor(doc_id: int):
    """Render the address book editor for a given document."""
    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()

    # Build a field map keyed by field_name for easy lookup.
    field_map = {f.field_name: f for f in fields}

    ordered_fields = []
    for name in ADDRESS_BOOK_FIELDS:
        if name in field_map:
            ordered_fields.append(field_map[name])
        else:
            # Placeholder — will be created on first extract
            ordered_fields.append(None)

    # Include any extra extracted fields not in the standard address-book schema.
    extra_fields = [f for f in fields if f.field_name not in ADDRESS_BOOK_FIELDS]

    pdf_url = url_for("pdf.serve_pdf", doc_id=doc_id)
    return render_template(
        "editor.html",
        doc=doc,
        ordered_fields=list(zip(ADDRESS_BOOK_FIELDS, ordered_fields)),
        extra_fields=extra_fields,
        pdf_url=pdf_url,
    )


@address_book_bp.route("/<int:doc_id>/update-field", methods=["POST"])
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


@address_book_bp.route("/<int:doc_id>/save", methods=["POST"])
@login_required
def save(doc_id: int):
    """Save all field changes submitted from the address book form."""
    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    field_map = {f.id: f for f in fields}

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

    return redirect(url_for("address_book.editor", doc_id=doc_id))


@address_book_bp.route("/<int:doc_id>/extract", methods=["POST"])
@login_required
def extract(doc_id: int):
    """Re-run OCR and address book field mapping for the document."""
    doc = Document.query.get_or_404(doc_id)
    svc = _get_pdf_service()

    if svc is None:
        flash("PDF service unavailable — check backend dependencies.", "danger")
        return redirect(url_for("address_book.editor", doc_id=doc_id))

    try:
        if not os.path.exists(doc.file_path):
            flash("Extraction failed: uploaded file not found on disk.", "danger")
            return redirect(url_for("address_book.editor", doc_id=doc_id))

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

    return redirect(url_for("address_book.editor", doc_id=doc_id))


@address_book_bp.route("/<int:doc_id>/apply-all", methods=["POST"])
@login_required
def apply_all(doc_id: int):
    """Apply AddressBook_v1 autofill/correction logic to all template fields.

    Algorithm
    ---------
    1. Ensure every AddressBook_v1 template field exists in the database
       (creates an empty placeholder when missing so the UI can render it).
    2. For each field, determine whether it is *invalid* — blank, OCR
       confidence < 0.80, or fails the field-specific regex/format check.
    3. Count invalid fields; if >= 7/9 the document is *blank-ish*.
    4. Apply sample1 defaults:
       * Blank-ish  → autofill any field with a known default.
       * Not blank-ish → autofill only the fixed fields (Name, State,
         Cell Phone) when invalid; leave variable fields (Street Address,
         City, Zip Code, Home Phone, Work Phone, Email) untouched.
    5. Save changes and redirect back to the editor.
    """
    doc = Document.query.get_or_404(doc_id)

    # Step 1: Ensure all 9 template fields exist in the DB so the UI can
    # render edit rows for every field regardless of prior extraction.
    existing = ExtractedField.query.filter_by(document_id=doc_id).all()
    field_map = {f.field_name: f for f in existing}

    for name in ADDRESS_BOOK_FIELDS:
        if name not in field_map:
            placeholder = ExtractedField(
                document_id=doc_id,
                field_name=name,
                value="",
                confidence=0.0,
            )
            db.session.add(placeholder)
            field_map[name] = placeholder

    # Flush so newly inserted rows get their primary-key IDs before we
    # reference them in FieldEditHistory records.
    db.session.flush()

    # Step 2: Evaluate each field's validity.
    invalid_count = sum(
        1
        for name in ADDRESS_BOOK_FIELDS
        if _is_field_invalid(name, field_map[name].value or "", field_map[name].confidence)
    )

    # Step 3: Determine blank-ish threshold.
    is_blank_ish = invalid_count >= BLANK_THRESHOLD

    # Step 4: Apply defaults.
    changed_count = 0
    for name in ADDRESS_BOOK_FIELDS:
        field = field_map[name]

        # Skip valid fields — do not overwrite good data.
        if not _is_field_invalid(name, field.value or "", field.confidence):
            continue

        # Decide which default to apply, if any.
        if is_blank_ish:
            # Blank-ish document: autofill any field that has a sample1 default.
            default = ADDRESSBOOK_V1_DEFAULTS.get(name)
        elif name in ADDRESSBOOK_V1_FIXED_FIELDS:
            # Partially-filled document: only override fixed fields.
            default = ADDRESSBOOK_V1_DEFAULTS.get(name)
        else:
            # Variable field in a non-blank-ish document — leave as-is.
            default = None

        if not default:
            continue  # no default available or not applicable

        old_value = field.value or ""
        if old_value == default:
            continue  # already set — no change needed

        history = FieldEditHistory(
            field_id=field.id,
            old_value=old_value,
            new_value=default,
            edited_by=current_user.id,
        )
        db.session.add(history)

        if not field.is_edited:
            field.original_value = old_value
        field.value = default
        field.is_edited = True
        field.version += 1
        changed_count += 1

    doc.status = "edited"
    _log(
        current_user.id,
        "apply_all",
        "document",
        str(doc_id),
        f"blank_ish={is_blank_ish} invalid={invalid_count}/9 changed={changed_count}",
    )
    db.session.commit()

    doc_type = "blank-ish" if is_blank_ish else "partially-filled"
    flash(
        f"Apply All ({doc_type} document): {changed_count} field(s) updated.",
        "success",
    )
    return redirect(url_for("address_book.editor", doc_id=doc_id))


@address_book_bp.route("/<int:doc_id>/approve", methods=["POST"])
@login_required
@_require_role("Admin", "Verifier")
def approve(doc_id: int):
    """Mark the document as approved."""
    doc = Document.query.get_or_404(doc_id)
    doc.status = "approved"
    _log(current_user.id, "approve", "document", str(doc_id))
    db.session.commit()
    flash("Document approved.", "success")
    return redirect(url_for("address_book.editor", doc_id=doc_id))


@address_book_bp.route("/<int:doc_id>/reject", methods=["POST"])
@login_required
@_require_role("Admin", "Verifier")
def reject(doc_id: int):
    """Mark the document as rejected."""
    doc = Document.query.get_or_404(doc_id)
    doc.status = "rejected"
    _log(current_user.id, "reject", "document", str(doc_id))
    db.session.commit()
    flash("Document rejected.", "warning")
    return redirect(url_for("address_book.editor", doc_id=doc_id))


@address_book_bp.route("/<int:doc_id>/export")
@login_required
def export_pdf(doc_id: int):
    """Legacy route: redirect to PDF export."""
    return redirect(url_for("address_book.export", doc_id=doc_id, fmt="pdf"))


@address_book_bp.route("/<int:doc_id>/export/<fmt>")
@login_required
def export(doc_id: int, fmt: str):
    """Export the address book document's fields as CSV, XLSX, JSON, or PDF.

    All formats are served as browser downloads with clean naming:
    ``{stem}_address_book_edited.{ext}``
    """
    if fmt not in ("csv", "xlsx", "json", "pdf"):
        abort(400)

    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    rows = [{"field_name": f.field_name, "value": f.value or ""} for f in fields]
    stem = os.path.splitext(doc.filename)[0]
    safe_stem = secure_filename(stem) or f"address_book_{doc_id}"

    if fmt == "json":
        buf = io.BytesIO(json.dumps(rows, indent=2, ensure_ascii=False).encode("utf-8"))
        _log(current_user.id, "export_json", "document", str(doc_id))
        db.session.commit()
        return send_file(
            buf,
            mimetype="application/json",
            as_attachment=True,
            download_name=f"{safe_stem}_address_book_edited.json",
        )

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["field_name", "value"])
        writer.writeheader()
        writer.writerows(rows)
        buf = io.BytesIO(output.getvalue().encode("utf-8"))
        _log(current_user.id, "export_csv", "document", str(doc_id))
        db.session.commit()
        return send_file(
            buf,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{safe_stem}_address_book_edited.csv",
        )

    if fmt == "pdf":
        svc = _get_pdf_service()
        if svc is None:
            flash("PDF service unavailable — cannot export as PDF.", "danger")
            return redirect(url_for("address_book.editor", doc_id=doc_id))
        if not os.path.exists(doc.file_path):
            flash("Export failed: source file not found on disk.", "danger")
            return redirect(url_for("address_book.editor", doc_id=doc_id))

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
            _log(current_user.id, "export_pdf", "document", str(doc_id))
            db.session.commit()
            return send_file(
                buf,
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"{safe_stem}_address_book_edited.pdf",
            )
        except Exception as exc:
            current_app.logger.exception(
                "PDF export failed for doc %s: %s", doc_id, exc
            )
            flash(f"PDF export failed: {exc}", "danger")
            return redirect(url_for("address_book.editor", doc_id=doc_id))

    # xlsx
    try:
        import openpyxl
    except ImportError:
        flash("openpyxl is not installed — cannot export as XLSX.", "danger")
        return redirect(url_for("address_book.editor", doc_id=doc_id))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Address Book"
    ws.append(["Field", "Value"])
    for row in rows:
        ws.append([row["field_name"], row["value"]])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    _log(current_user.id, "export_xlsx", "document", str(doc_id))
    db.session.commit()
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"{safe_stem}_address_book_edited.xlsx",
    )


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
