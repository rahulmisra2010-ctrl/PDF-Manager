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
GET  /ai-pdf/<doc_id>/ocr-tokens            — raw OCR word bboxes for overlay rendering
"""

import os
import re
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


def _ensure_tools_on_path() -> None:
    """Add tools/ directory to sys.path if not already present."""
    _here = os.path.dirname(os.path.abspath(__file__))
    _tools = os.path.abspath(os.path.join(_here, "..", "tools"))
    if _tools not in sys.path:
        sys.path.insert(0, _tools)


def _count_unpaired(fields_out: list) -> int:
    """Count fields that have no extracted value and are not headings."""
    return sum(1 for f in fields_out if not f.get("value") and not f.get("is_heading"))

ai_pdf_bp = Blueprint("ai_pdf", __name__, template_folder="../templates/pdf")


def _xywh_to_pixel_bbox(raw_bbox: dict | None) -> dict | None:
    """Convert a ``{x, y, width, height}`` bbox (pixel coords) to ``{x0, y0, x1, y1}``."""
    if not raw_bbox:
        return None
    return {
        "x0": raw_bbox.get("x", 0),
        "y0": raw_bbox.get("y", 0),
        "x1": raw_bbox.get("x", 0) + raw_bbox.get("width", 0),
        "y1": raw_bbox.get("y", 0) + raw_bbox.get("height", 0),
    }


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
# Heading extraction helper
# ---------------------------------------------------------------------------

def _extract_headings_as_fields(
    file_path: str,
    page_num: int,
    zoom: float,
    doc_id: int,
) -> list[dict]:
    """Return heading lines from the top of *page_num* as field dicts.

    Bounding boxes are scaled from PDF points to pixel coordinates using
    *zoom* so they align with the rendered page image.  Each heading is
    returned with ``is_heading=True`` so the frontend can render it with a
    distinct colour.

    Returns an empty list on any error so callers never have to handle
    exceptions from this helper.
    """
    _ensure_tools_on_path()
    try:
        from pathlib import Path
        from extract_pdf_headers import extract_headings_with_bbox  # type: ignore[import]

        results = extract_headings_with_bbox(Path(file_path), max_pages=page_num)
        # results is [(page_num, [heading_dict, …]), …]; pick the target page
        if not results or len(results) < page_num:
            return []
        _, headings = results[page_num - 1]

        heading_fields = []
        for h in headings:
            bb = h["bbox"]
            heading_fields.append({
                "field_name":    h["text"],
                "label":         h["text"],
                "value":         "",
                "confidence":    1.0,
                "bbox":          None,
                "label_bbox": {
                    "x0": bb["x0"] * zoom,
                    "y0": bb["y0"] * zoom,
                    "x1": bb["x1"] * zoom,
                    "y1": bb["y1"] * zoom,
                },
                "page":          page_num,
                "doc_id":        doc_id,
                "is_heading":    True,
                "font_size":     h.get("font_size", 0.0),
                "heading_level": h.get("heading_level", 3),
            })
        return heading_fields
    except Exception as exc:
        current_app.logger.warning(
            "Heading extraction failed for doc %s page %s: %s",
            doc_id, page_num, exc,
        )
        return []


# ---------------------------------------------------------------------------
# Input-type inference helper
# ---------------------------------------------------------------------------

# Keywords in field labels that strongly suggest a specific input widget type.
_CHECKBOX_KEYWORDS = re.compile(
    r"\b(check|tick|yes|no|agree|select|choose|option|checkbox|consent)\b",
    re.IGNORECASE,
)
_DATE_KEYWORDS = re.compile(
    r"\b(date|dob|birth|expir|issued|effective|start|end|from|to)\b",
    re.IGNORECASE,
)
_PHONE_KEYWORDS = re.compile(r"\b(phone|tel|fax|mobile|cell|contact)\b", re.IGNORECASE)
_EMAIL_KEYWORDS = re.compile(r"\b(email|e-mail|electronic.?mail)\b", re.IGNORECASE)
_SIGNATURE_KEYWORDS = re.compile(r"\b(sign|signature|initial)\b", re.IGNORECASE)
_NUMBER_KEYWORDS = re.compile(r"\b(amount|total|qty|quantity|number|no\.?|#|ssn|zip|postal)\b", re.IGNORECASE)


def _infer_input_type(label: str, value: str = "") -> str:
    """Infer the likely HTML input widget type from a field label and value.

    Returns one of: ``"checkbox"``, ``"date"``, ``"tel"``, ``"email"``,
    ``"signature"``, ``"number"``, or ``"text"`` (default).
    """
    lbl = str(label or "").lower()
    val = str(value or "").strip()

    if _CHECKBOX_KEYWORDS.search(lbl):
        return "checkbox"
    if _SIGNATURE_KEYWORDS.search(lbl):
        return "signature"
    if _DATE_KEYWORDS.search(lbl):
        return "date"
    if _EMAIL_KEYWORDS.search(lbl):
        return "email"
    if _PHONE_KEYWORDS.search(lbl):
        return "tel"
    if _NUMBER_KEYWORDS.search(lbl):
        return "number"

    # Fall back to value-based classification when the label is generic
    if val:
        if re.fullmatch(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}", val):
            return "email"
        # Require at least 7 digits among the formatting characters to avoid
        # matching strings that are purely punctuation/whitespace.
        if re.fullmatch(r"[\d()+\-\s]{7,}", val) and len(re.sub(r"\D", "", val)) >= 7:
            return "tel"
        if re.fullmatch(
            r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}[/\-]\d{2}[/\-]\d{2}", val
        ):
            return "date"

    return "text"


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

    # Build a JSON-serialisable list of field dicts scoped to this document.
    # These are injected into window.AI_CONFIG.initialFields so the JavaScript
    # overlay and sidebar start in sync with the DB state without any
    # cross-document contamination.
    fields_json = [
        {
            "id": f.id,
            "field_name": f.field_name,
            "label": f.field_name,
            "value": f.value or "",
            "confidence": float(f.confidence) if f.confidence is not None else 1.0,
            "page": f.page_number or 1,
            "doc_id": doc_id,
            "bbox": {
                "x0": f.bbox_x,
                "y0": f.bbox_y,
                "x1": (f.bbox_x + f.bbox_width) if (f.bbox_x is not None and f.bbox_width is not None) else None,
                "y1": (f.bbox_y + f.bbox_height) if (f.bbox_y is not None and f.bbox_height is not None) else None,
            } if f.bbox_x is not None else None,
            "label_bbox": None,
        }
        for f in fields
    ]

    return render_template(
        "pdf/extract_ai.html",
        doc=doc,
        fields=fields,
        fields_json=fields_json,
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

            def _to_pixel_bbox(raw_bbox):
                """Convert a {x, y, width, height} PDF-point bbox to pixel coords."""
                if not raw_bbox:
                    return None
                return {
                    "x0": raw_bbox.get("x", 0) * zoom,
                    "y0": raw_bbox.get("y", 0) * zoom,
                    "x1": (raw_bbox.get("x", 0) + raw_bbox.get("width", 0)) * zoom,
                    "y1": (raw_bbox.get("y", 0) + raw_bbox.get("height", 0)) * zoom,
                }

            for pair in pairs:
                pixel_bbox       = _to_pixel_bbox(pair.get("bbox"))
                pixel_label_bbox = _to_pixel_bbox(pair.get("label_bbox"))
                value = pair.get("value", "")
                fields_out.append({
                    "field_name":  pair["label"],
                    "label":       pair["label"],
                    "value":       value,
                    "confidence":  pair.get("confidence", 1.0),
                    "bbox":        pixel_bbox,
                    "label_bbox":  pixel_label_bbox,
                    "page":        page_num,
                    "doc_id":      doc_id,
                    "input_type":  _infer_input_type(pair["label"], value),
                })
            # Prepend heading fields (from the top of the page) so they
            # appear at the top of the sidebar and are visually distinct.
            heading_fields = _extract_headings_as_fields(
                doc.file_path, page_num, zoom, doc_id
            )
            fields_out = heading_fields + fields_out
            unpaired = _count_unpaired(fields_out)
            return jsonify({
                "fields": fields_out,
                "page": page_num,
                "doc_id": doc_id,
                "pairing_mode": "dynamic",
                "unpaired_labels_count": unpaired,
            })
    except Exception as exc:
        current_app.logger.warning(
            "Dynamic extraction in detect_fields failed for doc %s page %s: %s",
            doc_id, page_num, exc,
        )

    # ── Strategy 2: geometry-based label/value pairing via field_extractor ──
    svc = _get_ai_service()
    if svc is None:
        return jsonify({"error": "AI service unavailable"}), 503

    try:
        raw_fields = svc.extract_page_fields(doc.file_path, page_num, zoom=zoom)

        # Build raw_boxes in the format expected by extract_labeled_fields
        raw_boxes = []
        for f in raw_fields:
            bb = f.get("bbox") or {}
            raw_boxes.append({
                "text":       f.get("text", ""),
                "x0":         float(bb.get("x0", 0)),
                "y0":         float(bb.get("y0", 0)),
                "x1":         float(bb.get("x1", bb.get("x0", 0))),
                "y1":         float(bb.get("y1", bb.get("y0", 0))),
                "confidence": float(f.get("confidence", 0.5)),
                "page":       int(f.get("page", page_num)),
            })

        # Try the geometry-based extractor first (handles parenthesised labels
        # like "(city)", "(state)", "(ZIP)" and merges same-line value tokens)
        pairs: list[dict] = []
        pairing_mode = "fallback"
        try:
            from services.field_extractor import extract_labeled_fields  # type: ignore[import]

            labeled = extract_labeled_fields(raw_boxes, page=page_num)
            if labeled:
                pairs = [
                    {
                        "label":      p["label"],
                        "value":      p.get("value", ""),
                        "confidence": p.get("confidence", 0.5),
                        "bbox": {
                            "x0": p["value_box"]["x0"],
                            "y0": p["value_box"]["y0"],
                            "x1": p["value_box"]["x1"],
                            "y1": p["value_box"]["y1"],
                        } if p.get("value_box") else None,
                        "label_bbox": {
                            "x0": p["label_box"]["x0"],
                            "y0": p["label_box"]["y0"],
                            "x1": p["label_box"]["x1"],
                            "y1": p["label_box"]["y1"],
                        } if p.get("label_box") else None,
                    }
                    for p in labeled
                ]
                pairing_mode = "geometry"
        except Exception as fe_exc:
            current_app.logger.warning(
                "field_extractor failed for doc %s page %s: %s",
                doc_id, page_num, fe_exc,
            )

        # Fall back to keyword-based pairing if geometry extractor found nothing
        if not pairs:
            from services.dynamic_extraction import _pair_labels_values  # type: ignore[import]

            kw_boxes = [
                {
                    "text":       b["text"],
                    "x":          b["x0"],
                    "y":          b["y0"],
                    "width":      b["x1"] - b["x0"],
                    "height":     b["y1"] - b["y0"],
                    "confidence": b["confidence"],
                }
                for b in raw_boxes
            ]
            pairs = [
                {
                    "label":      kp["label"],
                    "value":      kp.get("value", ""),
                    "confidence": kp.get("confidence", 0.5),
                    "bbox":       _xywh_to_pixel_bbox(kp.get("bbox")),
                    "label_bbox": _xywh_to_pixel_bbox(kp.get("label_bbox")),
                }
                for kp in _pair_labels_values(kw_boxes)
            ]

        fields_out = [
            {
                "field_name": p["label"],
                "label":      p["label"],
                "value":      p.get("value", ""),
                "confidence": p.get("confidence", 0.5),
                "bbox":       p.get("bbox"),
                "label_bbox": p.get("label_bbox"),
                "page":       page_num,
                "doc_id":     doc_id,
                "input_type": _infer_input_type(p["label"], p.get("value", "")),
            }
            for p in pairs
        ]

        # Prepend heading fields from the top of the page
        heading_fields = _extract_headings_as_fields(
            doc.file_path, page_num, zoom, doc_id
        )
        fields_out = heading_fields + fields_out

        unpaired = _count_unpaired(fields_out)
        current_app.logger.info(
            "detect_fields %s pairing: doc=%s page=%s pairs=%d unpaired=%d",
            pairing_mode, doc_id, page_num, len(fields_out), unpaired,
        )
        return jsonify({
            "fields": fields_out,
            "page": page_num,
            "doc_id": doc_id,
            "pairing_mode": pairing_mode,
            "unpaired_labels_count": unpaired,
        })
    except Exception:
        current_app.logger.exception(
            "Field detection failed for doc %s page %s", doc_id, page_num
        )
        return jsonify({"error": "Field detection failed — check server logs for details"}), 500


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


@ai_pdf_bp.route("/<int:doc_id>/ocr-tokens")
@login_required
def ocr_tokens(doc_id: int):
    """Return all raw OCR word bounding boxes for a single PDF page.

    These raw tokens are intended for the client-side OCR overlay — a
    toggleable layer that shows every word PyMuPDF (or Tesseract) detected,
    independent of the field-pairing logic.  Each token carries its text,
    pixel-coordinate bounding box, inferred ``input_type``, and a confidence
    score so the overlay can colour-code tokens by reliability.

    Query parameters
    ----------------
    page : int  (default 1)   1-based page number.
    zoom : float (default 1.5) Render zoom factor; bboxes are in pixel coords
                               at this zoom level.
    """
    doc = Document.query.get_or_404(doc_id)

    if not os.path.exists(doc.file_path):
        return jsonify({"error": "File not found on disk"}), 404

    page_num = int(request.args.get("page", 1))
    zoom = float(request.args.get("zoom", 1.5))
    zoom = max(0.5, min(zoom, 3.0))

    _ensure_backend_on_path()
    svc = _get_ai_service()
    if svc is None:
        return jsonify({"error": "AI service unavailable"}), 503

    try:
        raw_fields = svc.extract_page_fields(doc.file_path, page_num, zoom=zoom)
    except Exception:
        current_app.logger.exception(
            "OCR token extraction failed for doc %s page %s", doc_id, page_num
        )
        return jsonify({"error": "OCR token extraction failed"}), 500

    tokens = []
    for f in raw_fields:
        bb = f.get("bbox") or {}
        text = f.get("text", "")
        tokens.append({
            "text":       text,
            "bbox":       {
                "x0": float(bb.get("x0", 0)),
                "y0": float(bb.get("y0", 0)),
                "x1": float(bb.get("x1", 0)),
                "y1": float(bb.get("y1", 0)),
            },
            "confidence": float(f.get("confidence", 0.5)),
            "input_type": _infer_input_type("", text),
            "page":       page_num,
        })

    return jsonify({
        "tokens": tokens,
        "page":   page_num,
        "doc_id": doc_id,
        "count":  len(tokens),
    })


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
