"""
blueprints/extraction_api.py — Unified extraction API blueprint.

Routes
------
POST /api/v1/extract/all/<doc_id>        — Run all extraction strategies in parallel
POST /api/v1/validate-fields/<doc_id>    — Validate extracted fields (confidence gates)
POST /api/v1/auto-detect/<doc_id>        — Auto-detect fields with confidence scoring
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import re
import sys

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from models import AuditLog, Document, ExtractedField, TrainingExample, db

logger = logging.getLogger(__name__)

extraction_api_bp = Blueprint("extraction_api", __name__, url_prefix="/api/v1")

# Confidence thresholds (aligned with frontend hooks/useConfidenceColors.js)
CONFIDENCE_HIGH = 0.85
CONFIDENCE_MED = 0.65
CONFIDENCE_AUTO_ACCEPT = 0.90  # auto-detect minimum to auto-accept


# ---------------------------------------------------------------------------
# Service helpers
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
        _backend = os.path.join(current_app.root_path, "backend")
        if _backend not in sys.path:
            sys.path.append(_backend)
        from services.training_service import TrainingService  # type: ignore[import]
        return TrainingService()
    except Exception:
        return None


def _resolve_doc(doc_id: int):
    """Return (Document, error_response) pair."""
    doc = Document.query.get(doc_id)
    if doc is None:
        return None, (jsonify({"error": "Document not found"}), 404)
    if not os.path.exists(doc.file_path):
        return None, (jsonify({"error": "PDF file not found on disk"}), 404)
    return doc, None


def _log(user_id: int, action: str, resource_type: str, resource_id: str,
         details: str = "") -> None:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or None,
    )
    db.session.add(entry)


# ---------------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------------

def _run_acroform_strategy(file_path: str) -> list[dict]:
    """Strategy 1: Extract form fields from AcroForm (PDF widget annotations)."""
    fields: list[dict] = []
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        for page in doc:
            for widget in page.widgets():
                name = widget.field_name or ""
                value = widget.field_value or ""
                if name:
                    fields.append({
                        "field_name": name,
                        "value": str(value).strip(),
                        "confidence": 0.95,
                        "strategy": "AcroForm",
                        "bbox": {
                            "x": widget.rect.x0,
                            "y": widget.rect.y0,
                            "width": widget.rect.width,
                            "height": widget.rect.height,
                        },
                    })
        doc.close()
    except Exception as exc:
        logger.debug("AcroForm strategy failed: %s", exc)
    return fields


def _run_layout_strategy(file_path: str) -> list[dict]:
    """Strategy 2: Layout-based field detection using pdfplumber."""
    fields: list[dict] = []
    try:
        import pdfplumber
        _KNOWN_FIELDS = [
            "Name", "Street Address", "City", "State", "Zip Code",
            "Home Phone", "Cell Phone", "Work Phone", "Email",
            "Address", "Phone", "Zip", "Email Address",
        ]
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    line = line.strip()
                    for fname in _KNOWN_FIELDS:
                        pattern = re.compile(
                            rf"(?i){re.escape(fname)}\s*[:\-=]\s*(.+)"
                        )
                        m = pattern.search(line)
                        if m:
                            value = m.group(1).strip()
                            if value and not _is_garbage(value):
                                fields.append({
                                    "field_name": fname,
                                    "value": value,
                                    "confidence": 0.80,
                                    "strategy": "Layout",
                                })
    except Exception as exc:
        logger.debug("Layout strategy failed: %s", exc)
    return fields


def _run_regex_strategy(file_path: str, full_text: str) -> list[dict]:
    """Strategy 4: Regex pattern matching for known field types."""
    fields: list[dict] = []
    try:
        # Phone numbers (10-digit)
        phones = re.findall(r"\b(\d{10})\b", full_text)
        for phone in phones:
            fields.append({
                "field_name": "Phone",
                "value": phone,
                "confidence": 0.88,
                "strategy": "Regex",
            })

        # ZIP codes (5 or 6 digits)
        zips = re.findall(r"\b(\d{5,6})\b", full_text)
        for z in zips:
            fields.append({
                "field_name": "Zip Code",
                "value": z,
                "confidence": 0.92,
                "strategy": "Regex",
            })

        # Email addresses
        emails = re.findall(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
                            full_text)
        for email in emails:
            fields.append({
                "field_name": "Email",
                "value": email,
                "confidence": 0.97,
                "strategy": "Regex",
            })
    except Exception as exc:
        logger.debug("Regex strategy failed: %s", exc)
    return fields


def _run_pdf_service_strategy(file_path: str) -> tuple[list[dict], int]:
    """Strategy 3: PDFService OCR + address-book field mapping."""
    pdf_svc = _get_pdf_service()
    if pdf_svc is None:
        return [], 0
    try:
        text, _tables, page_count = pdf_svc.extract(file_path)
        mapped = pdf_svc.map_address_book_fields(text)
        fields = [
            {
                "field_name": f["field_name"],
                "value": f.get("value", ""),
                "confidence": 0.75,
                "strategy": "OCR",
            }
            for f in (mapped if isinstance(mapped, list) else [])
            if not _is_garbage(f.get("value", ""))
        ]
        return fields, page_count
    except Exception as exc:
        logger.debug("PDFService strategy failed: %s", exc)
        return [], 0


def _is_garbage(value: str, min_len: int = 1) -> bool:
    """Return True if the extracted value is likely garbage/noise."""
    if not value or not value.strip():
        return True
    v = value.strip()
    if len(v) < min_len:
        return True
    # Repetitive characters (e.g. "dddddddddd", "xxxxxxxxx")
    if len(set(v.lower())) <= 2 and len(v) > 4:
        return True
    # Mostly non-printable or special characters
    printable_ratio = sum(1 for c in v if c.isalnum() or c in " .,/-@") / len(v)
    if printable_ratio < 0.5:
        return True
    return False


def _merge_strategies(strategy_results: list[list[dict]]) -> list[dict]:
    """
    Merge results from multiple strategies.

    For each field name, keep the result with the highest confidence.
    AcroForm results take priority over layout/OCR results.
    """
    merged: dict[str, dict] = {}
    # Priority order: AcroForm > OCR > Layout > Regex
    priority = {"AcroForm": 4, "OCR": 3, "Layout": 2, "Regex": 1}

    for results in strategy_results:
        for field in results:
            name = (field.get("field_name") or "").strip()
            if not name:
                continue
            if _is_garbage(field.get("value", "")):
                continue
            existing = merged.get(name)
            if existing is None:
                merged[name] = field
            else:
                # Higher confidence wins; break ties by strategy priority
                new_conf = field.get("confidence", 0)
                old_conf = existing.get("confidence", 0)
                new_prio = priority.get(field.get("strategy", ""), 0)
                old_prio = priority.get(existing.get("strategy", ""), 0)
                if (new_conf, new_prio) > (old_conf, old_prio):
                    merged[name] = field

    return list(merged.values())


# ---------------------------------------------------------------------------
# POST /api/v1/extract/all/<doc_id>
# ---------------------------------------------------------------------------

@extraction_api_bp.route("/extract/all/<int:doc_id>", methods=["POST"])
@login_required
def extract_all(doc_id: int):
    """
    Run all extraction strategies in parallel and merge the best results.

    Strategies executed:
      1. AcroForm (PDF widget annotations)
      2. Layout-based (pdfplumber label detection)
      3. OCR + address-book mapping (PDFService)
      4. Regex pattern matching (phone, zip, email)
      5. RAG field refinement (training-data similarity)

    Results are merged (highest confidence per field name wins) and persisted
    to the extracted_fields table, replacing any previous extraction.
    """
    doc, err = _resolve_doc(doc_id)
    if err:
        return err

    file_path = doc.file_path

    # --- Gather full text for regex strategy (via PDFService / fallback) ---
    full_text = ""
    page_count = 0
    try:
        pdf_svc = _get_pdf_service()
        if pdf_svc:
            full_text, _tables, page_count = pdf_svc.extract(file_path)
    except Exception:
        pass

    # --- Run strategies in parallel ---
    acroform_fields: list[dict] = []
    layout_fields: list[dict] = []
    ocr_fields: list[dict] = []
    regex_fields: list[dict] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        fut_acroform = pool.submit(_run_acroform_strategy, file_path)
        fut_layout = pool.submit(_run_layout_strategy, file_path)
        fut_regex = pool.submit(_run_regex_strategy, file_path, full_text)

        try:
            acroform_fields = fut_acroform.result(timeout=30)
        except Exception as exc:
            logger.warning("AcroForm strategy error: %s", exc)
        try:
            layout_fields = fut_layout.result(timeout=30)
        except Exception as exc:
            logger.warning("Layout strategy error: %s", exc)
        try:
            regex_fields = fut_regex.result(timeout=30)
        except Exception as exc:
            logger.warning("Regex strategy error: %s", exc)

    # OCR strategy runs separately (may be slow and sequential)
    try:
        ocr_fields, ocr_page_count = _run_pdf_service_strategy(file_path)
        if ocr_page_count > page_count:
            page_count = ocr_page_count
    except Exception as exc:
        logger.warning("OCR strategy error: %s", exc)

    # Merge all strategies
    merged = _merge_strategies([acroform_fields, ocr_fields, layout_fields, regex_fields])

    # --- RAG refinement ---
    rag_svc = _get_rag_service()
    if rag_svc and full_text.strip():
        try:
            rag_fields = rag_svc.extract_fields(str(doc_id), full_text)
            for rf in rag_fields:
                name = rf.get("field_name", "")
                value = rf.get("field_value") or rf.get("value", "")
                conf = rf.get("confidence", 0.7)
                if name and value and not _is_garbage(value):
                    # Boost existing field confidence if RAG agrees
                    for mf in merged:
                        if mf["field_name"] == name:
                            if mf.get("value", "").strip().lower() == value.strip().lower():
                                mf["confidence"] = min(1.0, mf["confidence"] + 0.05)
                            break
                    else:
                        merged.append({
                            "field_name": name,
                            "value": value,
                            "confidence": conf,
                            "strategy": "RAG",
                        })
        except Exception as exc:
            logger.warning("RAG refinement failed: %s", exc)

    # --- Apply training examples ---
    training_svc = _get_training_service()
    if training_svc and merged:
        try:
            training_examples = [ex.to_dict() for ex in TrainingExample.query.all()]
            if training_examples:
                refined = training_svc.apply_training_to_results(merged, training_examples)
                if refined:
                    merged = refined
        except Exception as exc:
            logger.warning("Training service failed: %s", exc)

    # --- Persist results ---
    ExtractedField.query.filter_by(document_id=doc_id).delete()
    saved: list[dict] = []
    for item in merged:
        bbox = item.get("bbox") or {}
        field = ExtractedField(
            document_id=doc_id,
            field_name=item["field_name"],
            value=item.get("value", ""),
            confidence=item.get("confidence", 0.5),
            bbox_x=bbox.get("x"),
            bbox_y=bbox.get("y"),
            bbox_width=bbox.get("width"),
            bbox_height=bbox.get("height"),
        )
        db.session.add(field)
        db.session.flush()
        saved.append({
            "id": field.id,
            "field_name": field.field_name,
            "value": field.value,
            "confidence": field.confidence,
            "strategy": item.get("strategy", "unknown"),
            "bbox": bbox if bbox else None,
        })

    doc.status = "extracted"
    if page_count:
        doc.page_count = page_count
    _log(current_user.id, "extract_all", "document", str(doc_id),
         f"strategies: AcroForm+Layout+OCR+Regex+RAG, fields: {len(saved)}")
    db.session.commit()

    avg_confidence = (
        sum(f["confidence"] for f in saved) / len(saved) if saved else 0.0
    )

    return jsonify({
        "document_id": doc_id,
        "fields": saved,
        "page_count": page_count,
        "strategies_used": ["AcroForm", "Layout", "OCR", "Regex", "RAG"],
        "total_extracted": len(saved),
        "average_confidence": round(avg_confidence, 3),
    })


# ---------------------------------------------------------------------------
# POST /api/v1/validate-fields/<doc_id>
# ---------------------------------------------------------------------------

@extraction_api_bp.route("/validate-fields/<int:doc_id>", methods=["POST"])
@login_required
def validate_fields(doc_id: int):
    """
    Validate extracted fields for a document.

    Checks each field against:
    - Format rules (zip = 5-6 digits, phone = 10 digits, email format)
    - Confidence threshold (flag fields below CONFIDENCE_MED)
    - Garbage text detection

    Returns a per-field validation result with status and suggestions.
    """
    doc = Document.query.get(doc_id)
    if doc is None:
        return jsonify({"error": "Document not found"}), 404

    data = request.get_json(silent=True) or {}
    min_confidence = float(data.get("min_confidence", CONFIDENCE_MED))

    fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    if not fields:
        return jsonify({
            "document_id": doc_id,
            "message": "No extracted fields found. Run extraction first.",
            "validations": [],
        })

    validations = []
    for f in fields:
        issues = []
        status = "ok"
        value = f.value or ""

        # Confidence check
        if (f.confidence or 0) < min_confidence:
            issues.append(f"Low confidence ({(f.confidence or 0):.0%})")
            status = "warning"

        # Garbage text check
        if value and _is_garbage(value):
            issues.append("Value appears to be garbage/noise text")
            status = "error"

        # Format-specific checks
        field_lower = f.field_name.lower()
        if "zip" in field_lower or "postal" in field_lower:
            if value and not re.match(r"^\d{5,6}$", value.strip()):
                issues.append("Zip code should be 5-6 digits")
                status = "warning" if status == "ok" else status

        if "phone" in field_lower or "mobile" in field_lower:
            digits_only = re.sub(r"\D", "", value)
            if value and len(digits_only) != 10:
                issues.append("Phone should be 10 digits")
                status = "warning" if status == "ok" else status

        if "email" in field_lower:
            if value and not re.match(
                r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$",
                value.strip(),
            ):
                issues.append("Invalid email format")
                status = "warning" if status == "ok" else status

        if not value:
            issues.append("Field is blank")
            status = "blank"

        validations.append({
            "id": f.id,
            "field_name": f.field_name,
            "value": value,
            "confidence": f.confidence,
            "confidence_pct": round((f.confidence or 0) * 100, 1),
            "status": status,
            "issues": issues,
            "is_valid": status == "ok",
        })

    total = len(validations)
    valid_count = sum(1 for v in validations if v["is_valid"])
    return jsonify({
        "document_id": doc_id,
        "total_fields": total,
        "valid_fields": valid_count,
        "invalid_fields": total - valid_count,
        "overall_status": "ok" if valid_count == total else "needs_review",
        "validations": validations,
    })


# ---------------------------------------------------------------------------
# POST /api/v1/auto-detect/<doc_id>
# ---------------------------------------------------------------------------

@extraction_api_bp.route("/auto-detect/<int:doc_id>", methods=["POST"])
@login_required
def auto_detect(doc_id: int):
    """
    Automatic field detection with confidence gates.

    Runs all extraction strategies (same as /extract/all), then applies
    quality gates:
    - Fields with confidence >= threshold (default 90%) are auto-accepted
    - Fields below threshold are flagged for manual review
    - Garbage text is filtered out

    Returns accepted and flagged fields separately.
    """
    doc, err = _resolve_doc(doc_id)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    threshold = float(data.get("threshold", CONFIDENCE_AUTO_ACCEPT))

    file_path = doc.file_path

    # Gather text
    full_text = ""
    page_count = 0
    try:
        pdf_svc = _get_pdf_service()
        if pdf_svc:
            full_text, _tables, page_count = pdf_svc.extract(file_path)
    except Exception:
        pass

    # Run all strategies
    acroform_fields = _run_acroform_strategy(file_path)
    layout_fields = _run_layout_strategy(file_path)
    regex_fields = _run_regex_strategy(file_path, full_text)
    ocr_fields, ocr_page_count = _run_pdf_service_strategy(file_path)
    if ocr_page_count > page_count:
        page_count = ocr_page_count

    merged = _merge_strategies([acroform_fields, ocr_fields, layout_fields, regex_fields])

    # RAG refinement
    rag_svc = _get_rag_service()
    if rag_svc and full_text.strip():
        try:
            rag_fields = rag_svc.extract_fields(str(doc_id), full_text)
            for rf in rag_fields:
                name = rf.get("field_name", "")
                value = rf.get("field_value") or rf.get("value", "")
                conf = rf.get("confidence", 0.7)
                if name and value and not _is_garbage(value):
                    for mf in merged:
                        if mf["field_name"] == name:
                            if mf.get("value", "").strip().lower() == value.strip().lower():
                                mf["confidence"] = min(1.0, mf["confidence"] + 0.05)
                            break
                    else:
                        merged.append({
                            "field_name": name,
                            "value": value,
                            "confidence": conf,
                            "strategy": "RAG",
                        })
        except Exception as exc:
            logger.warning("RAG failed in auto-detect: %s", exc)

    # Apply confidence gates
    accepted = []
    flagged = []
    for field in merged:
        conf = field.get("confidence", 0)
        if conf >= threshold and not _is_garbage(field.get("value", "")):
            accepted.append(field)
        else:
            reasons = []
            if conf < threshold:
                reasons.append(f"confidence {conf:.0%} < threshold {threshold:.0%}")
            if _is_garbage(field.get("value", "")):
                reasons.append("garbage text detected")
            field["rejection_reasons"] = reasons
            flagged.append(field)

    # Persist only accepted fields
    ExtractedField.query.filter_by(document_id=doc_id).delete()
    saved: list[dict] = []
    for item in accepted:
        bbox = item.get("bbox") or {}
        field = ExtractedField(
            document_id=doc_id,
            field_name=item["field_name"],
            value=item.get("value", ""),
            confidence=item.get("confidence", 0.5),
            bbox_x=bbox.get("x"),
            bbox_y=bbox.get("y"),
            bbox_width=bbox.get("width"),
            bbox_height=bbox.get("height"),
        )
        db.session.add(field)
        db.session.flush()
        saved.append({
            "id": field.id,
            "field_name": field.field_name,
            "value": field.value,
            "confidence": field.confidence,
            "strategy": item.get("strategy", "unknown"),
        })

    doc.status = "extracted"
    if page_count:
        doc.page_count = page_count
    _log(current_user.id, "auto_detect", "document", str(doc_id),
         f"threshold={threshold}, accepted={len(saved)}, flagged={len(flagged)}")
    db.session.commit()

    avg_confidence = (
        sum(f["confidence"] for f in saved) / len(saved) if saved else 0.0
    )

    return jsonify({
        "document_id": doc_id,
        "threshold": threshold,
        "page_count": page_count,
        "accepted": saved,
        "flagged": flagged,
        "total_accepted": len(saved),
        "total_flagged": len(flagged),
        "average_confidence": round(avg_confidence, 3),
    })
