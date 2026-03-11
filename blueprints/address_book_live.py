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
GET  /address-book-live/<doc_id>/prefill        — return saved field suggestions
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
from werkzeug.utils import secure_filename

from models import AuditLog, Document, ExtractedField, FieldEditHistory, ValidationLog, FieldCorrection, TrainingExample, db
from blueprints.validation import validate_fields_data
from blueprints.training_matcher import find_best_matches

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


@address_book_live_bp.route("/<int:doc_id>/train-me", methods=["POST"])
@login_required
def train_me(doc_id: int):
    """Train Me endpoint: validate extracted fields against reference data.

    Expects JSON body::

        {
          "reference_set": "mat_pdf_v1",
          "fields": [
            {"field_id": 1, "field_name": "Name", "value": "Rahul Misra"},
            ...
          ]
        }

    Returns a structured validation result and persists a ``ValidationLog``
    (and ``FieldCorrection`` rows) to the database.
    """
    Document.query.get_or_404(doc_id)
    data = request.get_json(silent=True) or {}

    reference_set = data.get("reference_set", "mat_pdf_v1")
    fields = data.get("fields", [])

    if not isinstance(fields, list):
        return jsonify({"ok": False, "error": "'fields' must be a list"}), 400

    # ------------------------------------------------------------------
    # Run validation
    # ------------------------------------------------------------------
    try:
        import json as _json
        import sys as _sys
        import os as _os
        _backend = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "backend")
        if _backend not in _sys.path:
            _sys.path.append(_backend)
        from services.validation_service import validate_document  # type: ignore[import]
    except ImportError as exc:
        current_app.logger.exception("Could not import validation_service: %s", exc)
        return jsonify({"ok": False, "error": "Validation service unavailable"}), 503

    try:
        result = validate_document(doc_id, fields, reference_set)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Validation failed for doc %s: %s", doc_id, exc)
        return jsonify({"ok": False, "error": "Validation failed"}), 500

    # ------------------------------------------------------------------
    # Persist ValidationLog and FieldCorrection records
    # ------------------------------------------------------------------
    try:
        meta = result["validation_metadata"]
        log = ValidationLog(
            document_id=doc_id,
            reference_set=reference_set,
            total_fields=meta["total_fields"],
            validated_count=meta["validated"],
            accuracy_score=meta["accuracy"],
            results_json=_json.dumps(result["results"]),
            created_by=current_user.id,
        )
        db.session.add(log)
        db.session.flush()  # get log.id before adding corrections

        for r in result["results"]:
            if r.get("corrected"):
                correction = FieldCorrection(
                    validation_log_id=log.id,
                    field_id=r.get("field_id"),
                    field_name=r["field_name"],
                    original_value=r.get("extracted_value", ""),
                    corrected_value=r.get("corrected_to", ""),
                    correction_source="train_me",
                )
                db.session.add(correction)

        _log(
            current_user.id,
            "train_me",
            "document",
            str(doc_id),
            details=f"ref={reference_set} acc={meta['accuracy']:.2f}",
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to persist validation log for doc %s: %s", doc_id, exc
        )
        # Return the validation result even if persistence failed
        result["_warning"] = "Validation results could not be saved to the database."

    return jsonify(result)


@address_book_live_bp.route("/<int:doc_id>/prefill")
@login_required
def prefill(doc_id: int):
    """Return saved/most-used field values as pre-fill suggestions.

    Aggregates corrected values from ``FieldCorrection`` (Train Me runs) and
    confirmed values from ``TrainingExample`` records, returning the most
    frequently used values for each address-book field.

    Returns JSON::

        {
          "ok": true,
          "suggestions": {
            "Name":  ["Alice Smith", "Bob Jones"],
            "Email": ["alice@example.com"],
            ...
          }
        }
    """
    Document.query.get_or_404(doc_id)  # verify document exists (404 if not)

    MAX_PER_FIELD = 5
    suggestions: dict = {}

    # --- FieldCorrection records (from Train Me runs) ---
    correction_rows = (
        db.session.query(
            FieldCorrection.field_name,
            FieldCorrection.corrected_value,
            db.func.count(FieldCorrection.corrected_value).label("cnt"),
        )
        .filter(
            FieldCorrection.corrected_value.isnot(None),
            FieldCorrection.corrected_value != "",
        )
        .group_by(FieldCorrection.field_name, FieldCorrection.corrected_value)
        .order_by(db.desc("cnt"))
        .all()
    )

    for row in correction_rows:
        field_name = row.field_name
        value = row.corrected_value
        bucket = suggestions.setdefault(field_name, [])
        if value not in bucket and len(bucket) < MAX_PER_FIELD:
            bucket.append(value)

    # --- TrainingExample records ---
    training_rows = (
        db.session.query(
            TrainingExample.field_name,
            db.func.coalesce(TrainingExample.field_value, TrainingExample.correct_value).label("val"),
            db.func.count(
                db.func.coalesce(TrainingExample.field_value, TrainingExample.correct_value)
            ).label("cnt"),
        )
        .filter(
            db.func.coalesce(TrainingExample.field_value, TrainingExample.correct_value).isnot(None),
            db.func.coalesce(TrainingExample.field_value, TrainingExample.correct_value) != "",
        )
        .group_by(
            TrainingExample.field_name,
            db.func.coalesce(TrainingExample.field_value, TrainingExample.correct_value),
        )
        .order_by(db.desc("cnt"))
        .all()
    )

    for row in training_rows:
        field_name = row.field_name
        value = row.val
        if value:
            bucket = suggestions.setdefault(field_name, [])
            if value not in bucket and len(bucket) < MAX_PER_FIELD:
                bucket.append(value)

    return jsonify({"ok": True, "suggestions": suggestions})


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
        }
        for f in fields
    ]

    buf = io.BytesIO()
    try:
        svc._export_as_pdf(doc.file_path, field_dicts, buf)
        buf.seek(0)
        stem = os.path.splitext(doc.filename)[0]
        dest_dir = current_app.config.get("PDF_EXPORT_FOLDER", r"D:\destination_folder")
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, secure_filename(f"{stem}_live_address_book.pdf"))
        with open(dest_path, "wb") as fh:
            fh.write(buf.read())
        _log(current_user.id, "export_pdf", "document", str(doc_id))
        db.session.commit()
        flash(f"PDF exported successfully to {dest_path}", "success")
        return redirect(url_for("address_book_live.editor", doc_id=doc_id))
    except Exception as exc:
        current_app.logger.exception(
            "PDF export failed for doc %s: %s", doc_id, exc
        )
        flash(f"PDF export failed: {exc}", "danger")
        return redirect(url_for("address_book_live.editor", doc_id=doc_id))


@address_book_live_bp.route("/<int:doc_id>/validate-and-suggest")
@login_required
def validate_and_suggest(doc_id: int):
    """Complete pipeline: validate fields → find training-data suggestions.

    Step 1 — validates extracted fields (blank, wrong format, low confidence).
    Step 2 — queries training data for top suggestions on problem fields.

    Returns JSON::

        {
            "ok": true,
            "doc_id": <int>,
            "extracted": [...],
            "issues": [...],
            "fields": {...},
            "blank_fields": [...],
            "suggestions": {"Name": [{"value": ..., "confidence": ..., ...}], ...}
        }
    """
    Document.query.get_or_404(doc_id)
    db_fields = ExtractedField.query.filter_by(document_id=doc_id).all()

    field_dicts = [
        {
            "field_id": f.id,
            "field_name": f.field_name,
            "value": f.value or "",
            "confidence": f.confidence,
        }
        for f in db_fields
    ]

    # Step 1: Validate
    validation_result = validate_fields_data(field_dicts)

    # Step 2: Collect field names that need suggestions
    problem_fields = list(validation_result["blank_fields"])
    for issue in validation_result["issues"]:
        fn = issue["field_name"]
        if issue["issue_type"] in ("invalid_format", "low_confidence") and fn not in problem_fields:
            problem_fields.append(fn)

    suggestions = find_best_matches(doc_id, problem_fields)

    return jsonify({
        "ok": True,
        "doc_id": doc_id,
        "extracted": field_dicts,
        "issues": validation_result["issues"],
        "fields": validation_result["fields"],
        "blank_fields": validation_result["blank_fields"],
        "suggestions": suggestions,
    })


@address_book_live_bp.route("/<int:doc_id>/apply-selections", methods=["POST"])
@login_required
def apply_selections(doc_id: int):
    """Apply user-chosen values to document fields.

    Expects JSON body::

        {"selections": {"Name": "John Smith", "Email": "john@example.com"}}

    Returns::

        {"ok": true, "applied": {"Name": "John Smith", ...}, "updated_count": 2}
    """
    Document.query.get_or_404(doc_id)
    data = request.get_json(silent=True) or {}
    selections = data.get("selections", {})

    if not selections:
        return jsonify({"ok": False, "error": "No selections provided"}), 400

    updated: dict = {}
    for field_name, new_value in selections.items():
        field = ExtractedField.query.filter_by(
            document_id=doc_id,
            field_name=field_name,
        ).first()

        if field and str(new_value) != (field.value or ""):
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
            updated[field_name] = new_value

    if updated:
        _log(
            current_user.id,
            "apply_selections",
            "document",
            str(doc_id),
            details=f"Applied {len(updated)} field selection(s) from validator",
        )
        db.session.commit()

    return jsonify({
        "ok": True,
        "applied": updated,
        "updated_count": len(updated),
    })


@address_book_live_bp.route("/<int:doc_id>/validator")
@login_required
def validator_page(doc_id: int):
    """Render the smart field validator / suggestion UI for *doc_id*."""
    doc = Document.query.get_or_404(doc_id)
    return render_template(
        "validator.html",
        doc=doc,
        validate_url=url_for("address_book_live.validate_and_suggest", doc_id=doc_id),
        apply_url=url_for("address_book_live.apply_selections", doc_id=doc_id),
        export_url=url_for("address_book_live.export_pdf", doc_id=doc_id),
        editor_url=url_for("address_book_live.editor", doc_id=doc_id),
        csrf_token=current_app.jinja_env.globals["csrf_token"](),
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
