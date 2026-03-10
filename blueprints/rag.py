"""
blueprints/rag.py — RAG (Retrieval-Augmented Generation) API blueprint.

Routes
------
POST /api/v1/extract/rag/<doc_id>        — RAG-based field extraction
GET  /api/v1/fields/<doc_id>             — list all extracted fields for a document
PUT  /api/v1/fields/<field_id>           — update a single field value (with history)
GET  /api/v1/fields/<field_id>/history   — get edit history for a field
POST /api/v1/documents/<doc_id>/pdf      — retrieve raw PDF bytes for the viewer
GET  /api/v1/rag/files                   — list RAG text files
"""

import os

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required

from models import AuditLog, Document, ExtractedField, FieldEditHistory, db

rag_bp = Blueprint("rag", __name__, url_prefix="/api/v1")


# ---------------------------------------------------------------------------
# Service loader
# ---------------------------------------------------------------------------

def _get_pdf_service():
    try:
        from services.pdf_service import PDFService  # type: ignore[import]
        return PDFService()
    except Exception:
        return None


def _get_rag_service():
    try:
        from services.rag_service import RAGService  # type: ignore[import]
        rag_dir = os.path.join(
            current_app.root_path, os.environ.get("RAG_DIR", "rag_data")
        )
        return RAGService(rag_dir=rag_dir)
    except Exception:
        current_app.logger.exception("Failed to initialise RAGService")
        return None


def _get_training_service():
    try:
        from services.training_service import TrainingService  # type: ignore[import]
        return TrainingService()
    except Exception:
        current_app.logger.warning("TrainingService unavailable; skipping training intelligence.")
        return None


# ---------------------------------------------------------------------------
# POST /api/v1/extract/rag/<doc_id>
# ---------------------------------------------------------------------------

@rag_bp.route("/extract/rag/<int:doc_id>", methods=["POST"])
@login_required
def rag_extract(doc_id: int):
    """
    Run RAG-based field extraction on the document.

    Extracts text via PDFService, then passes it through RAGService to produce
    address-book fields with confidence scores.  Results are persisted to the
    ``extracted_fields`` table (previous fields are replaced).
    """
    doc = Document.query.get_or_404(doc_id)

    if not os.path.exists(doc.file_path):
        return jsonify({"error": "PDF file not found on disk"}), 404

    pdf_svc = _get_pdf_service()
    if pdf_svc is None:
        return jsonify({"error": "PDFService unavailable — check backend dependencies"}), 503

    try:
        text, _tables, page_count = pdf_svc.extract(doc.file_path)
    except Exception as exc:
        current_app.logger.exception("Text extraction failed for doc %s", doc_id)
        return jsonify({"error": f"Text extraction failed: {exc}"}), 500

    rag_svc = _get_rag_service()
    if rag_svc is None:
        return jsonify({"error": "RAGService unavailable"}), 503

    try:
        rag_fields = rag_svc.extract_fields(str(doc_id), text)
    except Exception as exc:
        current_app.logger.exception("RAG extraction failed for doc %s", doc_id)
        return jsonify({"error": f"RAG extraction failed: {exc}"}), 500

    # Apply training intelligence: fill blank fields and correct incorrect
    # values using patterns learned from stored training examples.
    training_svc = _get_training_service()
    if training_svc is not None:
        try:
            rag_fields = training_svc.apply_training(rag_fields)
        except Exception as exc:
            current_app.logger.warning(
                "TrainingService.apply_training failed for doc %s (%s); "
                "using raw RAG results.",
                doc_id, exc,
            )

    # Persist results — remove old fields, insert fresh ones
    ExtractedField.query.filter_by(document_id=doc_id).delete()
    saved: list[dict] = []
    for item in rag_fields:
        field = ExtractedField(
            document_id=doc_id,
            field_name=item["field_name"],
            value=item["field_value"],
            confidence=item["confidence"],
        )
        db.session.add(field)
        db.session.flush()
        saved.append(
            {
                "id": field.id,
                "field_name": field.field_name,
                "value": field.value,
                "confidence": field.confidence,
                "confidence_source": item.get("confidence_source", "rag"),
            }
        )

    doc.status = "extracted"
    doc.page_count = page_count
    _log(current_user.id, "rag_extract", "document", str(doc_id))
    db.session.commit()

    return jsonify({"document_id": doc_id, "fields": saved, "page_count": page_count})


# ---------------------------------------------------------------------------
# GET /api/v1/fields/<doc_id>
# ---------------------------------------------------------------------------

@rag_bp.route("/fields/<int:doc_id>", methods=["GET"])
@login_required
def get_fields(doc_id: int):
    """Return all extracted fields for a document as JSON."""
    Document.query.get_or_404(doc_id)  # 404 if document does not exist
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    return jsonify({"document_id": doc_id, "fields": [f.to_dict() for f in fields]})


# ---------------------------------------------------------------------------
# PUT /api/v1/fields/<field_id>
# ---------------------------------------------------------------------------

@rag_bp.route("/fields/<int:field_id>", methods=["PUT"])
@login_required
def update_field(field_id: int):
    """
    Update a single extracted field value.

    Records the old/new value in ``field_edit_history`` for change tracking.

    JSON body: ``{"value": "<new value>"}``
    """
    field = ExtractedField.query.get_or_404(field_id)
    data = request.get_json(silent=True) or {}

    new_value = data.get("value")
    if new_value is None:
        return jsonify({"error": "Missing 'value' in request body"}), 400

    new_value = str(new_value).strip()
    old_value = field.value or ""

    if new_value == old_value:
        return jsonify({"message": "No change detected", "field": field.to_dict()})

    # Record history
    history = FieldEditHistory(
        field_id=field.id,
        old_value=old_value,
        new_value=new_value,
        edited_by=current_user.id,
    )
    db.session.add(history)

    # Update field
    if not field.is_edited:
        field.original_value = old_value
    field.value = new_value
    field.is_edited = True

    _log(current_user.id, "field_edit", "field", str(field_id), f"{field.field_name}: {old_value!r} -> {new_value!r}")
    db.session.commit()

    return jsonify({"message": "Field updated", "field": field.to_dict()})


# ---------------------------------------------------------------------------
# GET /api/v1/fields/<field_id>/history
# ---------------------------------------------------------------------------

@rag_bp.route("/fields/<int:field_id>/history", methods=["GET"])
@login_required
def field_history(field_id: int):
    """Return the full edit history for a single field."""
    ExtractedField.query.get_or_404(field_id)  # 404 if field not found
    history = (
        FieldEditHistory.query
        .filter_by(field_id=field_id)
        .order_by(FieldEditHistory.edited_at.desc())
        .all()
    )
    return jsonify(
        {"field_id": field_id, "history": [h.to_dict() for h in history]}
    )


# ---------------------------------------------------------------------------
# POST /api/v1/documents/<doc_id>/pdf
# ---------------------------------------------------------------------------

@rag_bp.route("/documents/<int:doc_id>/pdf", methods=["POST", "GET"])
@login_required
def serve_pdf(doc_id: int):
    """Serve the raw PDF file for embedding in the browser viewer."""
    doc = Document.query.get_or_404(doc_id)
    if not os.path.exists(doc.file_path):
        return jsonify({"error": "PDF file not found on disk"}), 404
    return send_file(doc.file_path, mimetype="application/pdf")


# ---------------------------------------------------------------------------
# GET /api/v1/rag/files
# ---------------------------------------------------------------------------

@rag_bp.route("/rag/files", methods=["GET"])
@login_required
def rag_files():
    """List all RAG text files stored on disk."""
    rag_svc = _get_rag_service()
    if rag_svc is None:
        return jsonify({"error": "RAGService unavailable"}), 503
    return jsonify({"files": rag_svc.list_rag_files()})


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
