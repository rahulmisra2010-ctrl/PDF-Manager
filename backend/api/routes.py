"""
backend/api/routes.py — REST API v1 Blueprint.

Endpoints
---------
POST /api/v1/upload                                    Upload a PDF
POST /api/v1/extract/ocr/<document_id>                 Run OCR extraction
POST /api/v1/extract/ai/<document_id>                  Run AI + RAG extraction
POST /api/v1/extract/spatial/<document_id>             Run spatial OCR extraction
POST /api/v1/analyze/layout/<document_id>              Analyze form layout
POST /api/v1/suggestions/spatial/<document_id>         Get position-based suggestions
GET  /api/v1/position/<document_id>/<page>/<x>/<y>     Get field info for position
GET  /api/v1/fields/<document_id>                      Retrieve extracted fields
PUT  /api/v1/fields/<field_id>                        Edit a field value
GET  /api/v1/ocr/<document_id>/confidence              Get OCR confidence data
GET  /api/v1/documents/<document_id>/pdf               Serve the original PDF
GET  /api/v1/documents/<document_id>                   Get document metadata
GET  /api/v1/documents                                 List all documents
DELETE /api/v1/documents/<document_id>                 Delete a document
GET  /api/v1/documents/<document_id>/heatmap           Get heatmap for a page
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, request, send_file

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path setup so backend packages can be imported when the blueprint is loaded
# from the root Flask app.
# ---------------------------------------------------------------------------
_API_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_API_DIR)
_ROOT_DIR = os.path.dirname(_BACKEND_DIR)
for _p in (_BACKEND_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Lazily imported services
_extractor: Any = None
_ocr_engine: Any = None
_spatial_ocr_engine: Any = None
_layout_analyzer: Any = None
_context_enricher: Any = None
_template_matcher: Any = None


def _get_extractor():
    global _extractor
    if _extractor is None:
        from extraction.extractor import AIExtractor
        _extractor = AIExtractor()
    return _extractor


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from ocr.ocr_engine import OCREngine
        _ocr_engine = OCREngine()
    return _ocr_engine


def _get_spatial_ocr_engine():
    global _spatial_ocr_engine
    if _spatial_ocr_engine is None:
        from spatial.spatial_ocr_engine import SpatialOCREngine
        _spatial_ocr_engine = SpatialOCREngine()
    return _spatial_ocr_engine


def _get_layout_analyzer():
    global _layout_analyzer
    if _layout_analyzer is None:
        from spatial.layout_analyzer import LayoutAnalyzer
        _layout_analyzer = LayoutAnalyzer()
    return _layout_analyzer


def _get_context_enricher():
    global _context_enricher
    if _context_enricher is None:
        from spatial.context_enricher import ContextEnricher
        _context_enricher = ContextEnricher()
    return _context_enricher


def _get_template_matcher():
    global _template_matcher
    if _template_matcher is None:
        from spatial.template_matcher import TemplateMatcher
        _template_matcher = TemplateMatcher()
    return _template_matcher


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def _upload_folder() -> Path:
    return Path(current_app.config.get("UPLOAD_FOLDER", "uploads"))


def _ok(data: dict | list, status: int = 200):
    return jsonify(data), status


def _err(msg: str, status: int = 400):
    return jsonify({"error": msg}), status


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@api_v1_bp.route("/upload", methods=["POST"])
def upload():
    """Upload a PDF file and create a Document record."""
    if "file" not in request.files:
        return _err("No file part in request", 400)

    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith(".pdf"):
        return _err("Only PDF files are accepted", 400)

    content = f.read()
    max_bytes = current_app.config.get("MAX_CONTENT_LENGTH", 50 * 1024 * 1024)
    if len(content) > max_bytes:
        return _err("File too large", 413)

    upload_dir = _upload_folder()
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid.uuid4())
    file_path = upload_dir / f"{file_id}.pdf"
    file_path.write_bytes(content)

    # Persist to DB
    try:
        from models import Document, db
        doc = Document(
            filename=f.filename,
            file_path=str(file_path),
            status="uploaded",
            file_size=len(content),
        )
        # Associate with logged-in user if available
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated:
                doc.uploaded_by = current_user.id
        except Exception:
            pass
        db.session.add(doc)
        db.session.commit()
        document_id = doc.id
    except Exception as exc:
        logger.warning("DB save failed, using UUID: %s", exc)
        document_id = file_id

    return _ok(
        {
            "document_id": document_id,
            "filename": f.filename,
            "status": "uploaded",
            "message": "PDF uploaded successfully. Call /api/v1/extract/ocr or /api/v1/extract/ai to process.",
            "file_size_bytes": len(content),
        },
        201,
    )


# ---------------------------------------------------------------------------
# OCR Extraction
# ---------------------------------------------------------------------------

@api_v1_bp.route("/extract/ocr/<document_id>", methods=["POST"])
def extract_ocr(document_id: str):
    """
    Run multi-engine OCR extraction on the specified document.

    Returns per-page word lists with bounding boxes and confidence scores.
    Stores OCRCharacterData records in the database.
    """
    doc_path, db_doc = _resolve_document(document_id)
    if doc_path is None:
        return _err("Document not found", 404)

    try:
        engine = _get_ocr_engine()
        page_results = engine.ocr_document(doc_path)
    except Exception as exc:
        logger.exception("OCR extraction failed: %s", exc)
        return _err(f"OCR failed: {exc}", 500)

    # Persist character data to DB
    try:
        from models import OCRCharacterData, db
        doc_int_id = db_doc.id if db_doc else None
        if doc_int_id:
            for pr in page_results:
                for word in pr.words:
                    for char in word.text:
                        record = OCRCharacterData(
                            document_id=doc_int_id,
                            page_number=pr.page_number,
                            character=char,
                            confidence=word.confidence,
                            x=word.x,
                            y=word.y,
                            width=word.width / max(len(word.text), 1),
                            height=word.height,
                            ocr_engine=word.engine,
                        )
                        db.session.add(record)
            db.session.commit()
    except Exception as exc:
        logger.warning("Could not store OCR character data: %s", exc)

    result = {
        "document_id": document_id,
        "total_pages": len(page_results),
        "engines_used": list({e for pr in page_results for e in pr.engines_used}),
        "pages": [pr.to_dict() for pr in page_results],
        "full_text": "\n".join(pr.full_text for pr in page_results),
    }
    return _ok(result)


# ---------------------------------------------------------------------------
# AI / RAG Extraction
# ---------------------------------------------------------------------------

@api_v1_bp.route("/extract/ai/<document_id>", methods=["POST"])
def extract_ai(document_id: str):
    """
    Run full AI + RAG extraction pipeline on the document.

    Returns structured fields with confidence scores, heatmaps, and metrics.
    """
    doc_path, db_doc = _resolve_document(document_id)
    if doc_path is None:
        return _err("Document not found", 404)

    run_rag = request.json.get("run_rag", True) if request.is_json else True

    try:
        extractor = _get_extractor()
        result = extractor.extract(doc_path, str(document_id), run_rag=run_rag)
    except Exception as exc:
        logger.exception("AI extraction failed: %s", exc)
        return _err(f"Extraction failed: {exc}", 500)

    # Persist extracted fields to DB
    if db_doc:
        try:
            from models import ExtractedField, db
            # Remove old fields for this document
            ExtractedField.query.filter_by(document_id=db_doc.id).delete()
            for f in result["fields"]:
                bbox = f.get("bbox") or {}
                ef = ExtractedField(
                    document_id=db_doc.id,
                    field_name=f["field_name"],
                    value=f["value"],
                    confidence=f["confidence"],
                    bbox_x=bbox.get("x"),
                    bbox_y=bbox.get("y"),
                    bbox_width=bbox.get("width"),
                    bbox_height=bbox.get("height"),
                )
                db.session.add(ef)
            db_doc.status = "extracted"
            db.session.commit()
        except Exception as exc:
            logger.warning("Could not persist extracted fields: %s", exc)

    # Strip large heatmap images from response unless requested
    include_images = request.args.get("include_images", "false").lower() == "true"
    if not include_images:
        for hm in result.get("heatmaps", []):
            hm.pop("image", None)

    return _ok(result)


# ---------------------------------------------------------------------------
# Fields CRUD
# ---------------------------------------------------------------------------

@api_v1_bp.route("/fields/<document_id>", methods=["GET"])
def get_fields(document_id: str):
    """Return all extracted fields for a document."""
    _, db_doc = _resolve_document(document_id)
    if db_doc is None:
        return _err("Document not found", 404)

    try:
        from models import ExtractedField
        fields = ExtractedField.query.filter_by(document_id=db_doc.id).all()
        return _ok([f.to_dict() for f in fields])
    except Exception as exc:
        logger.exception("get_fields failed: %s", exc)
        return _err(str(exc), 500)


@api_v1_bp.route("/fields/<int:field_id>", methods=["PUT"])
def update_field(field_id: int):
    """
    Edit a single extracted field.

    Body (JSON): ``{ "value": "<new value>" }``
    Records the old value in FieldEditHistory.
    """
    data = request.get_json(force=True, silent=True) or {}
    new_value = data.get("value")
    if new_value is None:
        return _err("Missing 'value' in request body", 400)

    try:
        from models import ExtractedField, FieldEditHistory, db
        field = ExtractedField.query.get(field_id)
        if field is None:
            return _err("Field not found", 404)

        # Record history
        old_value = field.value
        history = FieldEditHistory(
            field_id=field.id,
            old_value=old_value,
            new_value=new_value,
        )
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated:
                history.edited_by = current_user.id
        except Exception:
            pass

        field.value = new_value
        field.is_edited = True
        if not field.original_value:
            field.original_value = old_value
        field.version = (field.version or 1) + 1

        db.session.add(history)
        db.session.commit()

        return _ok(field.to_dict())
    except Exception as exc:
        logger.exception("update_field failed: %s", exc)
        return _err(str(exc), 500)


# ---------------------------------------------------------------------------
# OCR Confidence
# ---------------------------------------------------------------------------

@api_v1_bp.route("/ocr/<document_id>/confidence", methods=["GET"])
def ocr_confidence(document_id: str):
    """Return stored OCR character confidence data for a document."""
    _, db_doc = _resolve_document(document_id)
    if db_doc is None:
        return _err("Document not found", 404)

    try:
        from models import OCRCharacterData
        records = OCRCharacterData.query.filter_by(
            document_id=db_doc.id
        ).order_by(OCRCharacterData.page_number, OCRCharacterData.y, OCRCharacterData.x).all()

        return _ok(
            {
                "document_id": document_id,
                "total_characters": len(records),
                "avg_confidence": (
                    sum(r.confidence for r in records) / len(records)
                    if records else 0.0
                ),
                "characters": [r.to_dict() for r in records[:5000]],  # cap at 5k
            }
        )
    except Exception as exc:
        logger.exception("ocr_confidence failed: %s", exc)
        return _err(str(exc), 500)


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

@api_v1_bp.route("/documents/<document_id>/heatmap", methods=["GET"])
def document_heatmap(document_id: str):
    """Generate and return a confidence heatmap for a document page."""
    page_number = int(request.args.get("page", 1))
    doc_path, db_doc = _resolve_document(document_id)
    if doc_path is None:
        return _err("Document not found", 404)

    try:
        engine = _get_ocr_engine()
        pr = engine.ocr_page(doc_path, page_number)
        from ocr.heatmap_generator import HeatmapGenerator
        gen = HeatmapGenerator()
        heatmap_data = gen.generate_json(pr)
        include_image = request.args.get("image", "false").lower() == "true"
        if include_image:
            heatmap_data["image"] = gen.generate_image(pr)
        return _ok(heatmap_data)
    except Exception as exc:
        logger.exception("heatmap generation failed: %s", exc)
        return _err(str(exc), 500)


# ---------------------------------------------------------------------------
# PDF Serving
# ---------------------------------------------------------------------------

@api_v1_bp.route("/documents/<document_id>/pdf", methods=["GET"])
def serve_pdf(document_id: str):
    """Serve the original PDF file for viewing in the browser."""
    doc_path, _ = _resolve_document(document_id)
    if doc_path is None:
        return _err("Document not found", 404)
    if not Path(doc_path).exists():
        return _err("PDF file not found on disk", 404)
    return send_file(doc_path, mimetype="application/pdf")


# ---------------------------------------------------------------------------
# Document management
# ---------------------------------------------------------------------------

@api_v1_bp.route("/documents", methods=["GET"])
def list_documents():
    """List all documents with pagination."""
    page = int(request.args.get("page", 1))
    per_page = min(int(request.args.get("per_page", 20)), 100)

    try:
        from models import Document
        paginated = Document.query.order_by(
            Document.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        docs = [_doc_to_dict(d) for d in paginated.items]
        return _ok(
            {
                "documents": docs,
                "total": paginated.total,
                "page": page,
                "per_page": per_page,
                "pages": paginated.pages,
            }
        )
    except Exception as exc:
        logger.exception("list_documents failed: %s", exc)
        return _err(str(exc), 500)


@api_v1_bp.route("/documents/<document_id>", methods=["GET"])
def get_document(document_id: str):
    """Return metadata for a specific document."""
    _, db_doc = _resolve_document(document_id)
    if db_doc is None:
        return _err("Document not found", 404)
    return _ok(_doc_to_dict(db_doc))


@api_v1_bp.route("/documents/<document_id>", methods=["DELETE"])
def delete_document(document_id: str):
    """Delete a document and its associated file."""
    doc_path, db_doc = _resolve_document(document_id)
    if db_doc is None:
        return _err("Document not found", 404)

    try:
        from models import db
        db.session.delete(db_doc)
        db.session.commit()
    except Exception as exc:
        logger.warning("DB delete failed: %s", exc)

    if doc_path and Path(doc_path).exists():
        try:
            Path(doc_path).unlink()
        except Exception as exc:
            logger.warning("File delete failed: %s", exc)

    return _ok({"status": "deleted", "document_id": document_id})


# ---------------------------------------------------------------------------
# Field edit history
# ---------------------------------------------------------------------------

@api_v1_bp.route("/fields/<int:field_id>/history", methods=["GET"])
def field_history(field_id: int):
    """Return the edit history for a specific field."""
    try:
        from models import FieldEditHistory
        records = FieldEditHistory.query.filter_by(
            field_id=field_id
        ).order_by(FieldEditHistory.edited_at.desc()).all()
        return _ok([r.to_dict() for r in records])
    except Exception as exc:
        return _err(str(exc), 500)


# ---------------------------------------------------------------------------
# Spatial OCR Endpoints
# ---------------------------------------------------------------------------

@api_v1_bp.route("/extract/spatial/<document_id>", methods=["POST"])
def extract_spatial(document_id: str):
    """
    Run spatial OCR extraction on the document.

    Query params:
      page (int, default 1): page number to extract. Pass 0 for all pages.

    Returns enriched word dicts with position, spatial, visual,
    and contextual features.
    """
    doc_path, _ = _resolve_document(document_id)
    if doc_path is None:
        return _err("Document not found", 404)

    body = request.get_json(force=True, silent=True) or {}
    page_num = body.get("page", int(request.args.get("page", 1)))

    try:
        engine = _get_spatial_ocr_engine()
        enricher = _get_context_enricher()

        if page_num == 0:
            # All pages
            raw = engine.extract_document(doc_path)
            total_pages = raw["total_pages"]
            pages_out = {}
            for p_str, words in raw["pages"].items():
                pages_out[p_str] = enricher.enrich(words)
            return _ok({
                "document_id": document_id,
                "total_pages": total_pages,
                "pages": pages_out,
            })
        else:
            words = engine.extract_page(doc_path, page_num)
            words = enricher.enrich(words)
            return _ok({
                "document_id": document_id,
                "page": page_num,
                "word_count": len(words),
                "words": words,
            })
    except Exception as exc:
        logger.exception("Spatial OCR extraction failed: %s", exc)
        return _err(f"Spatial extraction failed: {exc}", 500)


@api_v1_bp.route("/analyze/layout/<document_id>", methods=["POST"])
def analyze_layout(document_id: str):
    """
    Analyze the form layout of a document page.

    Query params:
      page (int, default 1): page to analyze.

    Returns zones, columns, rows, label-value pairs, and word layout.
    """
    doc_path, _ = _resolve_document(document_id)
    if doc_path is None:
        return _err("Document not found", 404)

    body = request.get_json(force=True, silent=True) or {}
    page_num = body.get("page", int(request.args.get("page", 1)))

    try:
        import fitz
        doc = fitz.open(doc_path)
        page = doc[page_num - 1]
        page_width = page.rect.width
        page_height = page.rect.height
        doc.close()
    except Exception as exc:
        logger.exception("Could not open PDF: %s", exc)
        return _err(f"PDF open failed: {exc}", 500)

    try:
        spatial_engine = _get_spatial_ocr_engine()
        words = spatial_engine.extract_page(doc_path, page_num)

        analyzer = _get_layout_analyzer()
        layout = analyzer.analyze(words, page_width, page_height)

        return _ok({
            "document_id": document_id,
            "page": page_num,
            "page_width": page_width,
            "page_height": page_height,
            "layout": layout,
        })
    except Exception as exc:
        logger.exception("Layout analysis failed: %s", exc)
        return _err(f"Layout analysis failed: {exc}", 500)


@api_v1_bp.route("/suggestions/spatial/<document_id>", methods=["POST"])
def suggestions_spatial(document_id: str):
    """
    Get hover suggestions for a position in the document.

    Body (JSON):
      page    (int)   : page number (default 1)
      x       (float) : x coordinate in PDF points
      y       (float) : y coordinate in PDF points

    Returns nearby words and inferred field information.
    """
    doc_path, _ = _resolve_document(document_id)
    if doc_path is None:
        return _err("Document not found", 404)

    body = request.get_json(force=True, silent=True) or {}
    page_num = int(body.get("page", 1))
    hover_x = float(body.get("x", 0))
    hover_y = float(body.get("y", 0))
    radius = float(body.get("radius", 30))  # search radius in points

    try:
        import fitz
        doc = fitz.open(doc_path)
        page = doc[page_num - 1]
        page_width = page.rect.width
        page_height = page.rect.height
        doc.close()
    except Exception as exc:
        return _err(f"PDF open failed: {exc}", 500)

    try:
        spatial_engine = _get_spatial_ocr_engine()
        enricher = _get_context_enricher()
        words = enricher.enrich(spatial_engine.extract_page(doc_path, page_num))

        # Find words near the hover position
        nearby = []
        for w in words:
            pos = w.get("position", {})
            wx = pos.get("x", 0) + pos.get("width", 0) / 2
            wy = pos.get("y", 0) + pos.get("height", 0) / 2
            dist = ((wx - hover_x) ** 2 + (wy - hover_y) ** 2) ** 0.5
            if dist <= radius:
                nearby.append({**w, "_distance": round(dist, 2)})

        nearby.sort(key=lambda n: n["_distance"])

        # If nothing found, use context enricher to infer empty-field type
        empty_inference = None
        nearby_labels = []
        if not nearby:
            # Look for any labels in the wider vicinity (3× radius)
            wide_radius = radius * 3
            for w in words:
                pos = w.get("position", {})
                wx = pos.get("x", 0) + pos.get("width", 0) / 2
                wy = pos.get("y", 0) + pos.get("height", 0) / 2
                dist = ((wx - hover_x) ** 2 + (wy - hover_y) ** 2) ** 0.5
                if dist <= wide_radius:
                    sp = w.get("spatial_features", {})
                    if sp.get("nearby_labels"):
                        nearby_labels.extend(sp["nearby_labels"])
            empty_inference = enricher.infer_empty_field(
                hover_x, hover_y, page_width, page_height, nearby_labels
            )

        return _ok({
            "document_id": document_id,
            "page": page_num,
            "hover_position": {"x": hover_x, "y": hover_y},
            "radius": radius,
            "nearby_words": nearby[:10],
            "empty_field_inference": empty_inference,
        })
    except Exception as exc:
        logger.exception("Spatial suggestions failed: %s", exc)
        return _err(f"Suggestions failed: {exc}", 500)


@api_v1_bp.route("/position/<document_id>/<int:page>/<float:x>/<float:y>", methods=["GET"])
def get_position_info(document_id: str, page: int, x: float, y: float):
    """
    GET /position/<document_id>/<page>/<x>/<y>

    Return spatial features and field inference for a specific PDF coordinate.
    """
    doc_path, _ = _resolve_document(document_id)
    if doc_path is None:
        return _err("Document not found", 404)

    radius = float(request.args.get("radius", 20))

    try:
        spatial_engine = _get_spatial_ocr_engine()
        enricher = _get_context_enricher()
        words = enricher.enrich(spatial_engine.extract_page(doc_path, page))

        nearby = []
        for w in words:
            pos = w.get("position", {})
            wx = pos.get("x", 0) + pos.get("width", 0) / 2
            wy = pos.get("y", 0) + pos.get("height", 0) / 2
            dist = ((wx - x) ** 2 + (wy - y) ** 2) ** 0.5
            if dist <= radius:
                nearby.append({**w, "_distance": round(dist, 2)})

        nearby.sort(key=lambda n: n["_distance"])
        top = nearby[0] if nearby else None

        return _ok({
            "document_id": document_id,
            "page": page,
            "query_position": {"x": x, "y": y},
            "nearest_word": top,
            "nearby_words": nearby[:5],
        })
    except Exception as exc:
        logger.exception("Position lookup failed: %s", exc)
        return _err(f"Position lookup failed: {exc}", 500)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_document(document_id: str) -> tuple[str | None, Any]:
    """
    Resolve a document_id (int DB id or UUID file id) to
    (file_path_str, db_doc_or_None).
    """
    try:
        from models import Document
        # Try integer DB ID first
        if str(document_id).isdigit():
            db_doc = Document.query.get(int(document_id))
            if db_doc:
                return db_doc.file_path, db_doc

        # Try matching UUID filename in uploads folder
        upload_dir = _upload_folder()
        candidate = upload_dir / f"{document_id}.pdf"
        if candidate.exists():
            return str(candidate), None
    except Exception as exc:
        logger.debug("Document resolution error: %s", exc)

    return None, None


def _doc_to_dict(doc) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_path": doc.file_path,
        "status": doc.status,
        "page_count": doc.page_count,
        "file_size": doc.file_size,
        "uploaded_by": doc.uploaded_by,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }
