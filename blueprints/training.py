"""
blueprints/training.py — Training Examples API blueprint.

Routes
------
POST   /api/v1/training/add        — save extracted fields as training examples
GET    /api/v1/training/list       — list all stored training examples
DELETE /api/v1/training/<id>       — remove a single training example
"""

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from models import AuditLog, Document, ExtractedField, TrainingExample, db

training_bp = Blueprint("training", __name__, url_prefix="/api/v1")


# ---------------------------------------------------------------------------
# POST /api/v1/training/add
# ---------------------------------------------------------------------------

@training_bp.route("/training/add", methods=["POST"])
@login_required
def add_training():
    """Mark extracted fields for a document as training examples.

    JSON body::

        {
          "document_id": 1,
          "fields": [
            {"field_name": "Name",  "field_value": "Rahul Misra"},
            {"field_name": "Email", "field_value": "rahul@example.com"},
            ...
          ]
        }

    Alternatively, omit ``fields`` to auto-load all
    :class:`~models.ExtractedField` rows for the document.

    Returns::

        {"ok": true, "added": 9, "document_id": 1}
    """
    data = request.get_json(silent=True) or {}
    document_id = data.get("document_id")
    fields = data.get("fields")  # may be None → auto-load from DB

    if not document_id:
        return jsonify({"ok": False, "error": "document_id is required"}), 400

    Document.query.get_or_404(document_id)  # 404 if document not found

    # If caller didn't supply fields, load them from the DB
    if fields is None:
        db_fields = ExtractedField.query.filter_by(document_id=document_id).all()
        fields = [
            {"field_name": f.field_name, "field_value": f.value or ""}
            for f in db_fields
        ]

    if not isinstance(fields, list):
        return jsonify({"ok": False, "error": "'fields' must be a list"}), 400

    added = 0
    for item in fields:
        field_name = (item.get("field_name") or "").strip()
        field_value = (item.get("field_value") or item.get("value") or "").strip()
        if not field_name:
            continue
        example = TrainingExample(
            document_id=document_id,
            field_name=field_name,
            field_value=field_value,
            created_by=current_user.id,
        )
        db.session.add(example)
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

    return jsonify({"ok": True, "added": added, "document_id": document_id})


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
# Helpers
# ---------------------------------------------------------------------------

def _log(
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: str,
    details: str = "",
) -> None:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or None,
    )
    db.session.add(entry)
