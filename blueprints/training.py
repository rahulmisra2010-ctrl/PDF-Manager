"""
blueprints/training.py — Training Examples API and UI blueprint.

Routes
------
POST   /api/v1/training/add        — save extracted fields as training examples
GET    /api/v1/training/examples   — list all training examples as JSON
GET    /api/v1/training/list       — alias list endpoint (returns ok/count/examples)
DELETE /api/v1/training/<id>       — remove a single training example
GET    /training/examples          — HTML view of all training examples
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from models import AuditLog, Document, ExtractedField, TrainingExample, db

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
          "fields": {"Name": "Alice", "City": "NY"}   ← dict form
        }

    Or with a list of field objects::

        {
          "document_id": 1,
          "fields": [{"field_name": "Name", "field_value": "Alice"}, ...]
        }

    Omit ``fields`` entirely to auto-load from :class:`~models.ExtractedField`.

    Replaces any existing training examples for the document.

    Returns::

        {"ok": true, "added": N, "document_id": 1, "saved": [...]}
    """
    data = request.get_json(silent=True) or {}
    document_id = data.get("document_id")
    fields = data.get("fields")

    if not document_id:
        return jsonify({"ok": False, "error": "document_id is required"}), 400

    # Validate document exists
    Document.query.get_or_404(document_id)

    # ------------------------------------------------------------------
    # Normalise fields to list of (field_name, value) pairs
    # ------------------------------------------------------------------
    pairs: list[tuple[str, str]] = []

    if fields is None:
        # Auto-load from DB
        db_fields = ExtractedField.query.filter_by(document_id=document_id).all()
        pairs = [(f.field_name, f.value or "") for f in db_fields]
    elif isinstance(fields, dict):
        # Dict form: {"Name": "Alice", ...}
        pairs = [(str(k).strip(), str(v).strip()) for k, v in fields.items()]
    elif isinstance(fields, list):
        # List form: [{"field_name": "Name", "field_value": "Alice"}, ...]
        for item in fields:
            fn = (item.get("field_name") or item.get("name") or "").strip()
            val = (item.get("field_value") or item.get("value") or "").strip()
            if fn:
                pairs.append((fn, val))
    else:
        return jsonify({"ok": False, "error": "'fields' must be a dict or list"}), 400

    # Replace existing examples for this document
    TrainingExample.query.filter_by(document_id=document_id).delete()

    saved: list[dict] = []
    for field_name, correct_value in pairs:
        if not correct_value:
            continue  # skip blank values
        ex = TrainingExample(
            document_id=document_id,
            field_name=field_name,
            correct_value=correct_value,
            field_value=correct_value,
            created_by=current_user.id,
        )
        db.session.add(ex)
        saved.append({"field_name": ex.field_name, "correct_value": ex.correct_value})

    _log(
        current_user.id,
        "training_add",
        "document",
        str(document_id),
        details=f"saved={len(saved)}",
    )
    db.session.commit()

    return jsonify({
        "ok": True,
        "added": len(saved),
        "document_id": document_id,
        "saved": saved,
    })


# ---------------------------------------------------------------------------
# GET /api/v1/training/examples
# ---------------------------------------------------------------------------

@training_bp.route("/api/v1/training/examples", methods=["GET"])
@login_required
def list_examples_json():
    """Return all training examples as JSON (no 'ok' wrapper for legacy compat)."""
    doc_id_filter = request.args.get("document_id", type=int)
    q = TrainingExample.query
    if doc_id_filter is not None:
        q = q.filter_by(document_id=doc_id_filter)
    examples = q.order_by(TrainingExample.created_at.desc()).all()
    return jsonify({
        "count": len(examples),
        "examples": [ex.to_dict() for ex in examples],
    })


# ---------------------------------------------------------------------------
# GET /api/v1/training/list
# ---------------------------------------------------------------------------

@training_bp.route("/api/v1/training/list", methods=["GET"])
@login_required
def list_training():
    """Return all stored training examples with ok/count/examples structure."""
    doc_id_filter = request.args.get("document_id", type=int)
    field_name_filter = (request.args.get("field_name") or "").strip() or None

    q = TrainingExample.query
    if doc_id_filter is not None:
        q = q.filter_by(document_id=doc_id_filter)
    if field_name_filter:
        q = q.filter_by(field_name=field_name_filter)

    examples = q.order_by(TrainingExample.created_at.desc()).all()
    return jsonify({
        "ok": True,
        "count": len(examples),
        "examples": [ex.to_dict() for ex in examples],
    })


# ---------------------------------------------------------------------------
# DELETE /api/v1/training/<id>
# ---------------------------------------------------------------------------

@training_bp.route("/api/v1/training/<int:example_id>", methods=["DELETE"])
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
# GET /training/examples — HTML view
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
# Helper
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
