"""
blueprints/ai_pdf.py — AI-powered PDF extraction blueprint.

Routes
------
GET  /ai-pdf/<doc_id>/view                  — interactive AI extraction interface
GET  /ai-pdf/<doc_id>/page/<page_num>       — serve PDF page as PNG image
POST /ai-pdf/<doc_id>/extract-region        — extract text from a screen region
POST /ai-pdf/<doc_id>/detect-fields         — auto-detect all fields on a page
POST /ai-pdf/<doc_id>/save-fields           — persist extracted fields to DB
GET  /ai-pdf/<doc_id>/engines               — list available OCR/AI engines
"""

import os
import sys

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from models import AuditLog, Document, ExtractedField, db


def _ensure_backend_on_path() -> None:
    """Add backend/ directory to sys.path if not already present."""
    _here = os.path.dirname(os.path.abspath(__file__))
    _backend = os.path.abspath(os.path.join(_here, "..", "backend"))
    if _backend not in sys.path:
        sys.path.insert(0, _backend)

ai_pdf_bp = Blueprint("ai_pdf", __name__, template_folder="../templates/pdf")


# ---------------------------------------------------------------------------
# Service loader
# ---------------------------------------------------------------------------

def _get_ai_service():
    """Lazily import AIExtractionService (backend/ must be on sys.path)."""
    try:
        from services.ai_extraction_service import AIExtractionService  # type: ignore[import]
        return AIExtractionService()
    except ImportError:
        return None
    except Exception:
        current_app.logger.exception("Failed to initialise AIExtractionService")
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@ai_pdf_bp.route("/<int:doc_id>/view")
@login_required
def view(doc_id: int):
    """Render the interactive AI extraction interface."""
    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    svc = _get_ai_service()
    engines = svc.get_available_engines() if svc else ["PyMuPDF"]
    return render_template(
        "pdf/extract_ai.html",
        doc=doc,
        fields=fields,
        engines=engines,
    )


@ai_pdf_bp.route("/<int:doc_id>/page/<int:page_num>")
@login_required
def page_image(doc_id: int, page_num: int):
    """Serve a single PDF page rendered as a PNG image."""
    doc = Document.query.get_or_404(doc_id)

    if not os.path.exists(doc.file_path):
        abort(404)

    zoom = float(request.args.get("zoom", 1.5))
    # Clamp zoom to a safe range to avoid denial-of-service via large images
    zoom = max(0.5, min(zoom, 3.0))

    svc = _get_ai_service()
    if svc is None:
        abort(503)

    try:
        png_bytes = svc.render_page(doc.file_path, page_num, zoom=zoom)
    except ValueError as exc:
        abort(404, str(exc))
    except Exception:
        current_app.logger.exception(
            "Failed to render page %s of doc %s", page_num, doc_id
        )
        abort(500)

    return Response(png_bytes, mimetype="image/png")


@ai_pdf_bp.route("/<int:doc_id>/detect-fields", methods=["POST"])
@login_required
def detect_fields(doc_id: int):
    """Auto-detect label/value field pairs on a single PDF page and return JSON.

    Preferred strategy: use ``extract_dynamic_fields`` to infer label/value pairs
    from OCR tokens (same heuristic used by the /pdf/<id>/extract route).
    Fallback: raw word-level extraction via the AI service (returns individual
    tokens with generic ``field_type`` tags).
    """
    doc = Document.query.get_or_404(doc_id)

    if not os.path.exists(doc.file_path):
        return jsonify({"error": "File not found on disk"}), 404

    data = request.get_json(silent=True) or {}
    page_num = int(data.get("page", 1))
    zoom = float(data.get("zoom", 1.5))
    zoom = max(0.5, min(zoom, 3.0))

    # ── Strategy 1: dynamic label/value extraction ──────────────────────────
    _ensure_backend_on_path()
    try:
        from services.dynamic_extraction import extract_dynamic_fields  # type: ignore[import]

        pairs = extract_dynamic_fields(doc.file_path, page_index=page_num - 1)
        if pairs:
            fields_out = []
            for pair in pairs:
                bbox = pair.get("bbox") or {}
                # Convert PDF-point bbox → pixel coords at the current zoom level
                pixel_bbox = {
                    "x0": bbox.get("x", 0) * zoom,
                    "y0": bbox.get("y", 0) * zoom,
                    "x1": (bbox.get("x", 0) + bbox.get("width", 0)) * zoom,
                    "y1": (bbox.get("y", 0) + bbox.get("height", 0)) * zoom,
                } if bbox else None
                fields_out.append({
                    "field_name": pair["label"],
                    "label":      pair["label"],
                    "value":      pair.get("value", ""),
                    "confidence": pair.get("confidence", 1.0),
                    "bbox":       pixel_bbox,
                    "page":       page_num,
                })
            return jsonify({"fields": fields_out, "page": page_num})
    except Exception as exc:
        current_app.logger.warning(
            "Dynamic extraction in detect_fields failed for doc %s page %s: %s",
            doc_id, page_num, exc,
        )

    # ── Strategy 2: fallback — raw word-level AI service ────────────────────
    svc = _get_ai_service()
    if svc is None:
        return jsonify({"error": "AI service unavailable"}), 503

    try:
        raw_fields = svc.extract_page_fields(doc.file_path, page_num, zoom=zoom)
        # Normalise to a consistent shape so the JS panel can render label/value
        for f in raw_fields:
            f.setdefault("field_name", f.get("text", ""))
            f.setdefault("label", f.get("text", ""))
            f.setdefault("value", f.get("text", ""))
        return jsonify({"fields": raw_fields, "page": page_num})
    except Exception as exc:
        current_app.logger.exception(
            "Field detection failed for doc %s page %s", doc_id, page_num
        )
        return jsonify({"error": str(exc)}), 500


@ai_pdf_bp.route("/<int:doc_id>/extract-region", methods=["POST"])
@login_required
def extract_region(doc_id: int):
    """Extract text from a rectangular screen region (pixel coordinates)."""
    doc = Document.query.get_or_404(doc_id)

    if not os.path.exists(doc.file_path):
        return jsonify({"error": "File not found on disk"}), 404

    data = request.get_json(silent=True) or {}
    try:
        page_num = int(data["page"])
        x0 = float(data["x0"])
        y0 = float(data["y0"])
        x1 = float(data["x1"])
        y1 = float(data["y1"])
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({"error": f"Invalid parameters: {exc}"}), 400

    zoom = float(data.get("zoom", 1.5))
    zoom = max(0.5, min(zoom, 3.0))

    svc = _get_ai_service()
    if svc is None:
        return jsonify({"error": "AI service unavailable"}), 503

    try:
        result = svc.extract_region(doc.file_path, page_num, x0, y0, x1, y1, zoom=zoom)
        return jsonify(result)
    except Exception as exc:
        current_app.logger.exception(
            "Region extraction failed for doc %s", doc_id
        )
        return jsonify({"error": str(exc)}), 500


@ai_pdf_bp.route("/<int:doc_id>/save-fields", methods=["POST"])
@login_required
def save_fields(doc_id: int):
    """
    Persist a list of AI-extracted fields to the database.

    Expects JSON body: ``{"fields": [{"field_name": ..., "value": ..., "confidence": ...}, …]}``
    """
    doc = Document.query.get_or_404(doc_id)
    data = request.get_json(silent=True) or {}
    incoming = data.get("fields", [])

    if not isinstance(incoming, list):
        return jsonify({"error": "fields must be a list"}), 400

    # Merge with existing fields: update matching names, append new ones
    existing = {f.field_name: f for f in ExtractedField.query.filter_by(document_id=doc_id).all()}

    for item in incoming:
        name = str(item.get("field_name", "")).strip()
        value = str(item.get("value", "")).strip()
        confidence = float(item.get("confidence", 0.8))
        if not name:
            continue
        if name in existing:
            field = existing[name]
            if value != (field.value or ""):
                if not field.is_edited:
                    field.original_value = field.value
                field.value = value
                field.is_edited = True
            field.confidence = round(confidence, 4)
        else:
            field = ExtractedField(
                document_id=doc_id,
                field_name=name,
                value=value,
                confidence=round(confidence, 4),
            )
            db.session.add(field)

    doc.status = "extracted"
    _log(current_user.id, "ai_extract", "document", str(doc_id))
    db.session.commit()
    return jsonify({"saved": len(incoming), "status": doc.status})


@ai_pdf_bp.route("/<int:doc_id>/engines")
@login_required
def engines(doc_id: int):
    """Return the list of available OCR/AI engines."""
    svc = _get_ai_service()
    engine_list = svc.get_available_engines() if svc else []
    return jsonify({"engines": engine_list})


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
