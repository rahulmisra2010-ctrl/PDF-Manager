"""
blueprints/extraction_api.py — Extraction API Blueprint.

Routes
------
POST /api/v1/extraction/extract-file    — Extract from a single uploaded file
POST /api/v1/extraction/batch-process   — Process multiple uploaded files
GET  /api/v1/extraction/status/<job_id> — Track batch job status
POST /api/v1/extraction/auto-sample     — Auto-generate training samples
GET  /api/v1/extraction/samples         — List extracted samples
GET  /api/v1/extraction/samples/export  — Export samples (JSON or CSV)
GET  /extraction/batch-processor        — Batch processor UI page
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
)
from flask_login import current_user, login_required

extraction_api_bp = Blueprint("extraction_api", __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp",
    ".docx", ".xlsx", ".xls", ".txt",
}


def _get_api_keys() -> dict[str, str | None]:
    return {
        "mindee_key": os.environ.get("MINDEE_API_KEY"),
        "koncile_key": os.environ.get("KONCILE_API_KEY"),
        "openai_key": os.environ.get("OPENAI_API_KEY"),
    }


def _allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in _ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# UI route
# ---------------------------------------------------------------------------

@extraction_api_bp.route("/extraction/batch-processor")
@login_required
def batch_processor_ui():
    """Render the batch processor UI page."""
    return render_template("extraction/batch_processor.html")


# ---------------------------------------------------------------------------
# API: Extract single file
# ---------------------------------------------------------------------------

@extraction_api_bp.route("/api/v1/extraction/extract-file", methods=["POST"])
@login_required
def extract_file():
    """
    Extract fields from a single uploaded file.

    Request (multipart/form-data)
    ---
    file: uploaded file (PDF, image, DOCX, XLSX)

    Response JSON
    ---
    {
        "ok": true,
        "filename": "...",
        "document_type": "invoice",
        "fields": {"Invoice Number": "INV-001", ...},
        "confidence": {"Invoice Number": 0.92, ...},
        "tool": "mindee",
        "quality_score": 0.87
    }
    """
    if "file" not in request.files:
        return jsonify(ok=False, error="No file provided"), 400

    upload = request.files["file"]
    filename = upload.filename or "document"

    if not _allowed_file(filename):
        return jsonify(ok=False, error=f"Unsupported file type: {filename}"), 415

    file_data = upload.read()
    if not file_data:
        return jsonify(ok=False, error="Empty file"), 400

    try:
        from backend.services.extraction_pipeline import run_extraction_pipeline

        keys = _get_api_keys()
        result = run_extraction_pipeline(
            file_data,
            filename,
            **keys,
        )

        return jsonify(
            ok=True,
            filename=filename,
            document_type=result.get("document_type", "unknown"),
            fields=result.get("fields", {}),
            confidence=result.get("confidence", {}),
            tool=result.get("tool", "none"),
            quality_score=result.get("quality_score", 0.0),
        )

    except Exception as exc:
        current_app.logger.error("extract_file error: %s", exc)
        return jsonify(ok=False, error=str(exc)), 500


# ---------------------------------------------------------------------------
# API: Batch process
# ---------------------------------------------------------------------------

@extraction_api_bp.route("/api/v1/extraction/batch-process", methods=["POST"])
@login_required
def batch_process():
    """
    Process multiple uploaded files in parallel.

    Request (multipart/form-data)
    ---
    files[]: one or more files

    Response JSON
    ---
    {"ok": true, "job_id": "<uuid>", "total_files": N}
    """
    uploaded = request.files.getlist("files[]") or request.files.getlist("files")
    if not uploaded:
        return jsonify(ok=False, error="No files provided"), 400

    files: list[tuple[str, bytes]] = []
    for upload in uploaded:
        fname = upload.filename or "document"
        if _allowed_file(fname):
            files.append((fname, upload.read()))
        else:
            current_app.logger.warning("Skipping unsupported file: %s", fname)

    if not files:
        return jsonify(ok=False, error="No supported files found"), 400

    try:
        from backend.services.batch_processor import BatchProcessor

        keys = _get_api_keys()
        processor = BatchProcessor(
            mindee_key=keys["mindee_key"],
            koncile_key=keys["koncile_key"],
            openai_key=keys["openai_key"],
        )

        job_id = processor.start_job(
            files,
            save_to_db=True,
            flask_app=current_app._get_current_object(),  # type: ignore[attr-defined]
        )

        return jsonify(ok=True, job_id=job_id, total_files=len(files))

    except Exception as exc:
        current_app.logger.error("batch_process error: %s", exc)
        return jsonify(ok=False, error=str(exc)), 500


# ---------------------------------------------------------------------------
# API: Job status
# ---------------------------------------------------------------------------

@extraction_api_bp.route("/api/v1/extraction/status/<job_id>", methods=["GET"])
@login_required
def job_status(job_id: str):
    """
    Get the status of a batch extraction job.

    Response JSON
    ---
    {
        "ok": true,
        "job_id": "...",
        "status": "running|completed|partial|failed",
        "total_files": N,
        "processed_files": N,
        "failed_files": N,
        "results": [...]
    }
    """
    from backend.services.batch_processor import BatchProcessor

    state = BatchProcessor.get_job_status(BatchProcessor, job_id)  # type: ignore[arg-type]

    if state is None:
        # Fall back to database
        try:
            from models import ExtractionJob

            record = ExtractionJob.query.filter_by(job_id=job_id).first()
            if record is None:
                return jsonify(ok=False, error="Job not found"), 404
            return jsonify(ok=True, **record.to_dict())
        except Exception as exc:
            current_app.logger.error("job_status DB lookup error: %s", exc)
            return jsonify(ok=False, error="Job not found"), 404

    return jsonify(ok=True, **state)


# ---------------------------------------------------------------------------
# API: Auto-sample generation
# ---------------------------------------------------------------------------

@extraction_api_bp.route("/api/v1/extraction/auto-sample", methods=["POST"])
@login_required
def auto_sample():
    """
    Auto-generate training samples from uploaded files.

    Accepts the same multipart request as ``batch-process`` but saves all
    extracted data to the ``ExtractedSample`` table immediately (synchronous).

    Response JSON
    ---
    {"ok": true, "stats": {"processed": N, "saved": N, "duplicates": N, ...}}
    """
    uploaded = request.files.getlist("files[]") or request.files.getlist("files")
    if not uploaded:
        return jsonify(ok=False, error="No files provided"), 400

    files: list[tuple[str, bytes]] = []
    for upload in uploaded:
        fname = upload.filename or "document"
        if _allowed_file(fname):
            files.append((fname, upload.read()))

    if not files:
        return jsonify(ok=False, error="No supported files found"), 400

    try:
        from backend.services.sample_db_generator import SampleDbGenerator

        keys = _get_api_keys()
        gen = SampleDbGenerator(
            flask_app=current_app._get_current_object(),  # type: ignore[attr-defined]
            mindee_key=keys["mindee_key"],
            koncile_key=keys["koncile_key"],
            openai_key=keys["openai_key"],
        )

        stats = gen.generate_from_files(files)
        return jsonify(ok=True, stats=stats)

    except Exception as exc:
        current_app.logger.error("auto_sample error: %s", exc)
        return jsonify(ok=False, error=str(exc)), 500


# ---------------------------------------------------------------------------
# API: List samples
# ---------------------------------------------------------------------------

@extraction_api_bp.route("/api/v1/extraction/samples", methods=["GET"])
@login_required
def list_samples():
    """
    List extracted samples from the database.

    Query params
    ---
    document_type  — filter by document type
    min_quality    — minimum quality score (float)
    limit          — max results (default 50)
    offset         — pagination offset (default 0)

    Response JSON
    ---
    {"ok": true, "total": N, "samples": [...]}
    """
    try:
        from models import ExtractedSample

        doc_type = request.args.get("document_type")
        min_q = request.args.get("min_quality", type=float)
        limit = min(int(request.args.get("limit", 50)), 500)
        offset = int(request.args.get("offset", 0))

        query = ExtractedSample.query
        if doc_type:
            query = query.filter_by(document_type=doc_type)
        if min_q is not None:
            query = query.filter(ExtractedSample.quality_score >= min_q)

        total = query.count()
        rows = (
            query.order_by(ExtractedSample.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return jsonify(ok=True, total=total, samples=[r.to_dict() for r in rows])

    except Exception as exc:
        current_app.logger.error("list_samples error: %s", exc)
        return jsonify(ok=False, error=str(exc)), 500


# ---------------------------------------------------------------------------
# API: Export samples
# ---------------------------------------------------------------------------

@extraction_api_bp.route("/api/v1/extraction/samples/export", methods=["GET"])
@login_required
def export_samples():
    """
    Export extracted samples as JSON or CSV.

    Query params
    ---
    format         — "json" (default) or "csv"
    document_type  — optional filter
    min_quality    — optional minimum quality score
    """
    import io

    fmt = request.args.get("format", "json").lower()
    doc_type = request.args.get("document_type")
    min_q = request.args.get("min_quality", type=float)

    try:
        from backend.services.sample_db_generator import SampleDbGenerator

        gen = SampleDbGenerator(
            flask_app=current_app._get_current_object(),  # type: ignore[attr-defined]
        )

        if fmt == "csv":
            data = gen.export_samples_csv(document_type=doc_type, min_quality=min_q)
            return send_file(
                io.BytesIO(data.encode("utf-8")),
                mimetype="text/csv",
                as_attachment=True,
                download_name=f"samples_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
            )
        else:
            data = gen.export_samples_json(document_type=doc_type, min_quality=min_q)
            return send_file(
                io.BytesIO(data.encode("utf-8")),
                mimetype="application/json",
                as_attachment=True,
                download_name=f"samples_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
            )

    except Exception as exc:
        current_app.logger.error("export_samples error: %s", exc)
        return jsonify(ok=False, error=str(exc)), 500
