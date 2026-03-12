"""
blueprints/training.py — Training examples API and UI blueprint.

Routes
------
POST /api/v1/training/add         — save labeled training examples for a document
GET  /api/v1/training/examples    — list all training examples as JSON
GET  /training/examples           — HTML view of all training examples
GET  /training/upload-sample      — form UI to create a sample training entry
POST /training/upload-sample      — process the uploaded sample form
POST /training/examples/<id>/delete — delete a training example group (document)
"""

from __future__ import annotations

import os

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from models import AuditLog, Document, ExtractedField, TrainingExample, db

# Document types available for the upload-sample form
DOCUMENT_TYPES = [
    "Address Book",
    "Invoice",
    "Receipt",
    "Contract",
    "Resume",
    "Medical Record",
    "Tax Form",
    "Bank Statement",
    "Other",
]

training_bp = Blueprint("training", __name__)


# ---------------------------------------------------------------------------
# POST /api/v1/training/add
# ---------------------------------------------------------------------------

@training_bp.route("/api/v1/training/add", methods=["POST"])
@login_required
def add_training():
    """Save labeled training examples for a document.

    Accepts JSON body::

        {
          "document_id": 1,
          "fields": {
            "Name": "Rahul Misra",
            "City": "Asansol",
            ...
          }
        }

    Replaces any existing training examples for the document with the new
    set, then rebuilds RAG embeddings so that future extractions benefit from
    the training data.

    Returns::

        {"ok": true, "document_id": 1, "saved": [{"field_name": ..., "correct_value": ...}, ...]}
    """
    data = request.get_json(silent=True) or {}
    document_id = data.get("document_id")
    fields = data.get("fields")

    if not document_id:
        return jsonify({"ok": False, "error": "document_id is required"}), 400

    if not isinstance(fields, dict) or not fields:
        return jsonify({"ok": False, "error": "'fields' must be a non-empty object"}), 400

    # Validate document exists
    Document.query.get_or_404(document_id)

    # Replace existing examples for this document
    TrainingExample.query.filter_by(document_id=document_id).delete()

    saved: list[dict] = []
    for field_name, correct_value in fields.items():
        correct_value = str(correct_value).strip() if correct_value is not None else ""
        if not correct_value:
            continue  # skip blank values
        ex = TrainingExample(
            document_id=document_id,
            field_name=str(field_name).strip(),
            correct_value=correct_value,
        )
        db.session.add(ex)
        saved.append({"field_name": ex.field_name, "correct_value": ex.correct_value})

    _log(
        current_user.id,
        "add_training",
        "document",
        str(document_id),
        details=f"fields={list(fields.keys())}",
    )
    db.session.commit()

    # Rebuild RAG embeddings if RAGService is available
    _rebuild_rag_embeddings(document_id)

    return jsonify({"ok": True, "document_id": document_id, "saved": saved})


# ---------------------------------------------------------------------------
# GET /api/v1/training/examples
# ---------------------------------------------------------------------------

@training_bp.route("/api/v1/training/examples", methods=["GET"])
@login_required
def list_examples_json():
    """Return all training examples as JSON."""
    examples = TrainingExample.query.order_by(TrainingExample.created_at.desc()).all()
    return jsonify(
        {
            "count": len(examples),
            "examples": [ex.to_dict() for ex in examples],
        }
    )


# ---------------------------------------------------------------------------
# GET /training/examples
# ---------------------------------------------------------------------------

@training_bp.route("/training/examples")
@login_required
def examples_list():
    """HTML view — display all training examples grouped by document."""
    examples = (
        TrainingExample.query
        .order_by(TrainingExample.document_id, TrainingExample.field_name)
        .all()
    )

    # Group by document
    grouped: dict[int, dict] = {}
    for ex in examples:
        doc_id = ex.document_id
        if doc_id not in grouped:
            doc = Document.query.get(doc_id)
            grouped[doc_id] = {
                "document": doc,
                "examples": [],
            }
        grouped[doc_id]["examples"].append(ex)

    return render_template(
        "training/examples_list.html",
        grouped=grouped,
        total=len(examples),
    )


# ---------------------------------------------------------------------------
# GET /training/upload-sample   — render the upload form
# POST /training/upload-sample  — process the form submission
# ---------------------------------------------------------------------------

@training_bp.route("/training/upload-sample", methods=["GET", "POST"])
@login_required
def upload_sample():
    """Form-based UI for uploading a named training sample with field-value pairs."""
    if request.method == "POST":
        sample_name = request.form.get("sample_name", "").strip()
        document_type = request.form.get("document_type", "").strip()
        field_names = request.form.getlist("field_name[]")
        field_values = request.form.getlist("field_value[]")

        if not sample_name:
            flash("Sample name is required.", "danger")
            return render_template(
                "training/upload_sample.html",
                document_types=DOCUMENT_TYPES,
            )

        # Build field dict, skip completely blank pairs
        fields: dict[str, str] = {}
        for fname, fval in zip(field_names, field_values):
            fname = fname.strip()
            fval = fval.strip()
            if fname and fval:
                fields[fname] = fval

        if not fields:
            flash("Please provide at least one field name and value.", "danger")
            return render_template(
                "training/upload_sample.html",
                document_types=DOCUMENT_TYPES,
            )

        # Create a placeholder Document record with status="training"
        safe_name = secure_filename(sample_name) or "sample"
        placeholder_path = os.path.join(
            current_app.config.get("UPLOAD_FOLDER", "uploads"),
            f"{safe_name}.training",
        )
        display_name = f"{sample_name} [{document_type}]" if document_type else sample_name
        doc = Document(
            filename=display_name,
            file_path=placeholder_path,
            status="training",
            uploaded_by=current_user.id,
        )
        db.session.add(doc)
        db.session.flush()  # get doc.id before committing

        # Persist field-value pairs as TrainingExample rows
        saved: list[dict] = []
        for fname, fval in fields.items():
            ex = TrainingExample(
                document_id=doc.id,
                field_name=fname,
                correct_value=fval,
                created_by=current_user.id,
            )
            db.session.add(ex)
            saved.append({"field_name": fname, "correct_value": fval})

        _log(
            current_user.id,
            "upload_sample",
            "document",
            str(doc.id),
            details=f"sample_name={sample_name!r}, document_type={document_type!r}, fields={list(fields.keys())}",
        )
        db.session.commit()

        flash(
            f"Sample '{sample_name}' uploaded successfully with {len(saved)} field(s).",
            "success",
        )
        return redirect(url_for("training.examples_list"))

    return render_template(
        "training/upload_sample.html",
        document_types=DOCUMENT_TYPES,
    )


# ---------------------------------------------------------------------------
# POST /training/examples/<doc_id>/delete — remove a sample and its examples
# ---------------------------------------------------------------------------

@training_bp.route("/training/examples/<int:doc_id>/delete", methods=["POST"])
@login_required
def delete_sample(doc_id: int):
    """Delete all training examples for a document (and the document if it is a training placeholder)."""
    doc = Document.query.get_or_404(doc_id)

    # Remove all training examples linked to this document
    deleted_count = TrainingExample.query.filter_by(document_id=doc_id).delete()

    _log(
        current_user.id,
        "delete_sample",
        "document",
        str(doc_id),
        details=f"deleted {deleted_count} training example(s) for doc '{doc.filename}'",
    )

    # Remove the document record if it was a training placeholder
    if doc.status == "training":
        db.session.delete(doc)

    db.session.commit()

    flash(f"Sample deleted ({deleted_count} field(s) removed).", "success")
    return redirect(url_for("training.examples_list"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rebuild_rag_embeddings(document_id: int) -> None:
    """Attempt to rebuild RAG embeddings for *document_id* after training data update."""
    try:
        import os
        from services.rag_service import RAGService  # type: ignore[import]

        doc = Document.query.get(document_id)
        if doc is None or not doc.file_path:
            return

        import sys
        _root = current_app.root_path
        _backend = os.path.join(_root, "backend")
        if _backend not in sys.path:
            sys.path.append(_backend)

        from services.pdf_service import PDFService  # type: ignore[import]

        pdf_svc = PDFService()
        if not os.path.exists(doc.file_path):
            return

        text, _tables, _pages = pdf_svc.extract(doc.file_path)
        rag_dir = os.path.join(_root, os.environ.get("RAG_DIR", "rag_data"))
        rag_svc = RAGService(rag_dir=rag_dir)
        rag_svc.save_rag_text(str(document_id), text)
        current_app.logger.info(
            "TrainingService: rebuilt RAG embeddings for doc %s", document_id
        )
    except Exception as exc:  # pragma: no cover
        current_app.logger.warning(
            "TrainingService: could not rebuild RAG embeddings for doc %s: %s",
            document_id,
            exc,
        )


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
