"""
blueprints/training.py — Training examples API and UI blueprint.

Routes
------
POST   /api/v1/training/add        — save labeled training examples for a document
GET    /api/v1/training/examples   — list all training examples as JSON
GET    /api/v1/training/list       — list all stored training examples (with filters)
DELETE /api/v1/training/<id>       — remove a single training example
GET    /training/examples          — HTML view of all training examples
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from models import AuditLog, Document, ExtractedField, TrainingExample, db

# UI blueprint — serves rendered HTML pages (no API prefix)
training_ui_bp = Blueprint("training_ui", __name__)

# API blueprint — all routes are prefixed with /api/v1
training_bp = Blueprint("training", __name__, url_prefix="/api/v1")


# ---------------------------------------------------------------------------
# POST /api/v1/training/add
# ---------------------------------------------------------------------------

@training_bp.route("/training/add", methods=["POST"])
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

@training_bp.route("/training/examples", methods=["GET"])
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
# GET /api/v1/training/list
# ---------------------------------------------------------------------------

@training_bp.route("/training/list", methods=["GET"])
@login_required
def list_training():
    """Return all stored training examples.

    Optional query params:
    * ``document_id`` — filter by document
    * ``field_name`` — filter by field name

    Returns::

        {"ok": true, "count": 9, "examples": [...]}
    """
    doc_id_filter = request.args.get("document_id", type=int)
    field_name_filter = request.args.get("field_name", "").strip() or None

    q = TrainingExample.query
    if doc_id_filter is not None:
        q = q.filter_by(document_id=doc_id_filter)
    if field_name_filter:
        q = q.filter_by(field_name=field_name_filter)

    examples = q.order_by(TrainingExample.created_at.desc()).all()
    return jsonify({
        "ok": True,
        "count": len(examples),
        "examples": [e.to_dict() for e in examples],
    })


# ---------------------------------------------------------------------------
# DELETE /api/v1/training/<id>
# ---------------------------------------------------------------------------

@training_bp.route("/training/<int:example_id>", methods=["DELETE"])
@login_required
def delete_training(example_id: int):
    """Remove a single training example by ID.

    Returns::

        {"ok": true, "deleted_id": 42}
    """
    example = TrainingExample.query.get_or_404(example_id)
    doc_id = example.document_id
    db.session.delete(example)
    _log(current_user.id, "training_delete", "training_example", str(example_id))
    db.session.commit()
    return jsonify({"ok": True, "deleted_id": example_id, "document_id": doc_id})


# ---------------------------------------------------------------------------
# GET /training/examples  (UI — HTML view)
# ---------------------------------------------------------------------------

@training_ui_bp.route("/training/examples")
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
# Helpers
# ---------------------------------------------------------------------------

def _rebuild_rag_embeddings(document_id: int) -> None:
    """Attempt to rebuild RAG embeddings for *document_id* after training data update."""
    try:
        import os
        import sys
        from services.rag_service import RAGService  # type: ignore[import]

        doc = Document.query.get(document_id)
        if doc is None or not doc.file_path:
            return

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
