"""blueprints/training.py — Training examples API and UI blueprint.

Routes
------
POST   /api/v1/training/add        — save labeled training examples for a document
GET    /api/v1/training/list       — list all stored training examples
DELETE /api/v1/training/<id>       — remove a single training example
GET    /api/v1/training/examples   — list all training examples as JSON
GET    /training/examples          — HTML view of all training examples
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request, url_for
from flask_login import current_user, login_required

from models import AuditLog, Document, ExtractedField, TrainingExample, db

training_bp = Blueprint("training", __name__)


# ---------------------------------------------------------------------------
# POST /api/v1/training/add
# ---------------------------------------------------------------------------

@training_bp.route("/api/v1/training/add", methods=["POST"])
@login_required
def add_training():
    """Mark extracted fields for a document as training examples.

    JSON body::

        {
          "document_id": 1,
          "fields": {
            "Name": "Rahul Misra",
            "City": "Asansol"
          }
        }

    Alternatively, pass ``fields`` as a list::

        {"fields": [{"field_name": "Name", "field_value": "Rahul Misra"}, ...]}

    Or omit ``fields`` entirely to auto-load all ExtractedField rows for the
    document.

    Returns::

        {"ok": true, "added": 2, "document_id": 1, "saved": [...]}
    """
    data = request.get_json(silent=True) or {}
    document_id = data.get("document_id")
    fields = data.get("fields")  # may be None, dict, or list

    if not document_id:
        return jsonify({"ok": False, "error": "document_id is required"}), 400

    # Validate document exists (404 if not)
    Document.query.get_or_404(document_id)

    # Replace any existing examples for this document so repeated calls
    # always reflect the latest training data (idempotent behaviour).
    TrainingExample.query.filter_by(document_id=document_id).delete()

    # Normalise fields to list of (field_name, value) pairs
    if fields is None:
        # Auto-load from ExtractedField table
        db_fields = ExtractedField.query.filter_by(document_id=document_id).all()
        pairs: list[tuple[str, str]] = [
            (f.field_name, f.value or "") for f in db_fields
        ]
    elif isinstance(fields, dict):
        pairs = [
            (str(k).strip(), str(v).strip() if v is not None else "")
            for k, v in fields.items()
        ]
    elif isinstance(fields, list):
        pairs = [
            (
                (item.get("field_name") or "").strip(),
                (item.get("field_value") or item.get("value") or "").strip(),
            )
            for item in fields
            if isinstance(item, dict)
        ]
    else:
        return jsonify({"ok": False, "error": "'fields' must be a dict or list"}), 400

    saved: list[dict] = []
    added = 0
    for field_name, value in pairs:
        if not field_name or not value:
            continue  # skip blank field names and blank values
        example = TrainingExample(
            document_id=document_id,
            field_name=field_name,
            correct_value=value,
            field_value=value,
            created_by=current_user.id,
        )
        db.session.add(example)
        added += 1
        saved.append({"field_name": field_name, "correct_value": value})

    if added:
        _log(
            current_user.id,
            "training_add",
            "document",
            str(document_id),
            f"added {added} training example(s)",
        )
        db.session.commit()

    return jsonify({"ok": True, "added": added, "document_id": document_id, "saved": saved})


# ---------------------------------------------------------------------------
# GET /api/v1/training/list
# ---------------------------------------------------------------------------

@training_bp.route("/api/v1/training/list", methods=["GET"])
@login_required
def list_training():
    """Return all stored training examples.

    Optional query params:

    * ``document_id`` — filter by document
    * ``field_name``  — filter by field name

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
# GET /api/v1/training/examples
# ---------------------------------------------------------------------------

@training_bp.route("/api/v1/training/examples", methods=["GET"])
@login_required
def list_examples_json():
    """Return all training examples as JSON."""
    examples = TrainingExample.query.order_by(TrainingExample.created_at.desc()).all()
    return jsonify({
        "count": len(examples),
        "examples": [ex.to_dict() for ex in examples],
    })


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
