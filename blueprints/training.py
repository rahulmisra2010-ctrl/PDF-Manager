"""
blueprints/training.py — Training examples API and UI blueprint.

Routes
------
POST   /api/v1/training/add        — save extracted fields as training examples
GET    /api/v1/training/list       — list all stored training examples
GET    /api/v1/training/examples   — list all training examples as JSON
DELETE /api/v1/training/<id>       — remove a single training example
GET    /training/examples          — HTML view of all training examples
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from models import AuditLog, Document, ExtractedField, TrainingExample, db

training_bp = Blueprint("training", __name__, url_prefix="/api/v1")
training_ui_bp = Blueprint("training_ui", __name__)


# ---------------------------------------------------------------------------
# POST /api/v1/training/add
# ---------------------------------------------------------------------------

@training_bp.route("/training/add", methods=["POST"])
@login_required
def add_training():
    """Save labeled training examples for a document.

    JSON body::

        {
          "document_id": 1,
          "fields": [
            {"field_name": "Name",  "field_value": "Rahul Misra"},
            {"field_name": "Email", "field_value": "rahul@example.com"},
            ...
          ]
        }

    ``fields`` may also be a dict ``{"Name": "Rahul Misra", ...}``.
    Omit ``fields`` to auto-load all :class:`~models.ExtractedField` rows
    for the document.

    Returns::

        {"ok": true, "added": 9, "document_id": 1, "saved": [...]}
    """
    data = request.get_json(silent=True) or {}
    document_id = data.get("document_id")
    fields = data.get("fields")  # may be None → auto-load from DB

    if not document_id:
        return jsonify({"ok": False, "error": "document_id is required"}), 400

    # Validate document exists
    Document.query.get_or_404(document_id)

    # Normalise fields to a list of {"field_name": ..., "field_value": ...}
    if fields is None:
        # Auto-load from DB
        db_fields = ExtractedField.query.filter_by(document_id=document_id).all()
        fields = [
            {"field_name": f.field_name, "field_value": f.value or ""}
            for f in db_fields
        ]
    elif isinstance(fields, dict):
        # Convert dict format {"Name": "Rahul"} → list format
        fields = [
            {"field_name": k, "field_value": v}
            for k, v in fields.items()
        ]
    elif not isinstance(fields, list):
        return jsonify({"ok": False, "error": "'fields' must be a list or object"}), 400

    # Replace existing training examples for this document
    TrainingExample.query.filter_by(document_id=document_id).delete()

    added = 0
    saved: list[dict] = []
    for item in fields:
        field_name = (item.get("field_name") or "").strip()
        field_value = str(
            item.get("field_value") or item.get("correct_value") or item.get("value") or ""
        ).strip()
        if not field_name or not field_value:
            continue  # skip blank values
        example = TrainingExample(
            document_id=document_id,
            field_name=field_name,
            field_value=field_value,
            correct_value=field_value,
            created_by=current_user.id,
        )
        db.session.add(example)
        saved.append({"field_name": field_name, "field_value": field_value})
        added += 1

    if added:
        _log(
            current_user.id,
            "training_add",
            "document",
            str(document_id),
            f"added {added} training example(s)",
        )
        db.session.commit()

    # Rebuild RAG embeddings if RAGService is available
    _rebuild_rag_embeddings(document_id)

    return jsonify({
        "ok": True,
        "added": added,
        "document_id": document_id,
        "saved": saved,
    })


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
# GET /training/examples  (HTML page — note: no /api/v1 prefix here because
# the blueprint prefix is /api/v1, so /training/examples → /api/v1/training/examples
# For the bare HTML URL /training/examples, register on the app directly via
# a second blueprint without prefix, or adjust the URL below)
# ---------------------------------------------------------------------------

@training_bp.route("/training/examples/html", methods=["GET"])
@login_required
def examples_list_html():
    """HTML view — display all training examples grouped by document (API-prefixed path)."""
    return _render_examples_list()


@training_ui_bp.route("/training/examples", methods=["GET"])
@login_required
def examples_list():
    """HTML view — display all training examples grouped by document."""
    return _render_examples_list()


def _render_examples_list():
    """Shared helper for both HTML views of training examples."""
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
