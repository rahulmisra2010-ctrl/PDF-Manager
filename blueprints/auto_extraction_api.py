"""
blueprints/auto_extraction_api.py — Smart API endpoints for the automatic extraction system.

Routes
------
POST   /api/v1/auto-extraction/upload           → Upload + auto-extract single file
POST   /api/v1/auto-extraction/batch            → Batch extract multiple files
GET    /api/v1/auto-extraction/live/<job_id>    → Stream real-time progress (SSE)
GET    /api/v1/auto-extraction/samples          → View auto-generated sample database
GET    /api/v1/auto-extraction/samples/<id>     → Get single sample details
DELETE /api/v1/auto-extraction/samples/<id>     → Delete a sample
POST   /api/v1/auto-extraction/train-ml         → Train / retrain ML model from samples
POST   /api/v1/auto-extraction/feedback         → Submit correction to improve extraction
GET    /api/v1/auto-extraction/jobs             → List all batch jobs
GET    /api/v1/auto-extraction/jobs/<job_id>    → Get batch job status
POST   /api/v1/auto-extraction/classify         → Classify document type only
GET    /api/v1/auto-extraction/stats            → Sample DB and ML stats
GET    /extraction/live                         → Real-time extraction UI (HTML)
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    render_template,
    request,
    stream_with_context,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

# Maximum seconds to hold an SSE connection open while waiting for a batch job
_SSE_MAX_WAIT_SECONDS = int(os.getenv("SSE_MAX_WAIT_SECONDS", "300"))

auto_extraction_bp = Blueprint("auto_extraction", __name__)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff",
                      ".tif", ".docx", ".xlsx", ".xls", ".txt"}


def _allowed_file(filename: str) -> bool:
    return os.path.splitext(filename.lower())[1] in ALLOWED_EXTENSIONS


def _get_pipeline():
    """Lazy-load the AutoExtractionPipeline."""
    try:
        from backend.services.auto_extraction_pipeline import AutoExtractionPipeline
    except ImportError:
        from services.auto_extraction_pipeline import AutoExtractionPipeline  # type: ignore
    return AutoExtractionPipeline()


def _get_batch_processor():
    try:
        from backend.services.batch_intelligent_processor import BatchIntelligentProcessor
    except ImportError:
        from services.batch_intelligent_processor import BatchIntelligentProcessor  # type: ignore
    return BatchIntelligentProcessor()


def _get_sample_builder():
    try:
        from backend.services.auto_sample_builder import AutoSampleBuilder
    except ImportError:
        from services.auto_sample_builder import AutoSampleBuilder  # type: ignore
    return AutoSampleBuilder()


def _get_feedback_learner():
    try:
        from backend.services.feedback_learner import FeedbackLearner
    except ImportError:
        from services.feedback_learner import FeedbackLearner  # type: ignore
    return FeedbackLearner()


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/extraction/live")
@login_required
def live_extraction_ui():
    """Render the real-time extraction web UI."""
    return render_template("extraction/live_extraction.html")


# ---------------------------------------------------------------------------
# POST /api/v1/auto-extraction/upload
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/upload", methods=["POST"])
@login_required
def upload_and_extract():
    """Upload a single file and run the full automatic extraction pipeline."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    filename = secure_filename(f.filename)
    if not _allowed_file(filename):
        return jsonify({
            "error": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        }), 415

    file_data = f.read()
    if not file_data:
        return jsonify({"error": "Empty file"}), 422

    try:
        pipeline = _get_pipeline()
        result = pipeline.extract(file_data, filename=filename)

        # Save sample if requested
        save_sample = request.form.get("save_sample", "true").lower() == "true"
        sample_id: Optional[int] = None
        if save_sample:
            builder = _get_sample_builder()
            sample = builder.build_sample(
                file_data, filename, save_to_db=True
            )
            sample_id = sample.get("id")

        return jsonify({
            "ok": True,
            "filename": filename,
            "fields": result.get("fields", {}),
            "doc_type": result.get("doc_type"),
            "confidence": result.get("confidence"),
            "tools_used": result.get("tools_used", []),
            "quality": result.get("quality", {}),
            "duration_ms": result.get("duration_ms"),
            "sample_id": sample_id,
        }), 200

    except Exception as exc:
        logger.exception("upload_and_extract failed for %s", filename)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /api/v1/auto-extraction/batch
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/batch", methods=["POST"])
@login_required
def batch_extract():
    """
    Upload multiple files for batch extraction.

    Accepts multipart/form-data with one or more ``files`` file fields.
    Returns a job_id to poll for progress.
    """
    uploaded = request.files.getlist("files")
    if not uploaded:
        return jsonify({"error": "No files provided"}), 400

    files = []
    rejected = []
    for f in uploaded:
        fname = secure_filename(f.filename or "file")
        if not _allowed_file(fname):
            rejected.append(fname)
            continue
        data = f.read()
        if data:
            files.append({"filename": fname, "data": data})

    if not files:
        return jsonify({
            "error": "No valid files to process",
            "rejected": rejected,
        }), 422

    # Create DB job record
    db_job_id: Optional[int] = None
    try:
        from models import ExtractionJob, db  # type: ignore
        db_job = ExtractionJob(
            job_id=str(uuid.uuid4()),
            status="queued",
            total_files=len(files),
            created_by=current_user.id if current_user.is_authenticated else None,
        )
        db.session.add(db_job)
        db.session.commit()
        db_job_id = db_job.id
    except Exception as exc:
        logger.warning("Could not create DB job record: %s", exc)

    processor = _get_batch_processor()
    job_id = processor.start_batch(files, save_samples=True, db_job_id=db_job_id)

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "total_files": len(files),
        "rejected": rejected,
        "live_url": f"/api/v1/auto-extraction/live/{job_id}",
    }), 202


# ---------------------------------------------------------------------------
# GET /api/v1/auto-extraction/live/<job_id>  — SSE streaming progress
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/live/<job_id>")
@login_required
def live_progress(job_id: str):
    """
    Stream real-time extraction progress as Server-Sent Events (SSE).

    The client connects and receives JSON events as each file is processed.
    The stream ends when the job completes or is cancelled.
    """
    try:
        from backend.services.batch_intelligent_processor import (  # noqa
            BatchIntelligentProcessor, _JOB_REGISTRY,
        )
    except ImportError:
        from services.batch_intelligent_processor import (  # type: ignore
            BatchIntelligentProcessor, _JOB_REGISTRY,
        )

    def generate():
        max_wait = _SSE_MAX_WAIT_SECONDS
        start = time.monotonic()
        last_event_idx = 0

        while time.monotonic() - start < max_wait:
            job = _JOB_REGISTRY.get(job_id)
            if job is None:
                yield _sse_event("error", {"message": "Job not found"})
                return

            # Send any new events
            new_events = job.events[last_event_idx:]
            for event in new_events:
                yield _sse_event(event["type"], {
                    "data": event["data"],
                    "timestamp": event["timestamp"],
                })
            last_event_idx += len(new_events)

            # Send current status
            yield _sse_event("progress", job.to_dict())

            if job.status in ("completed", "failed", "cancelled"):
                yield _sse_event("done", job.to_dict())
                return

            time.sleep(0.5)

        yield _sse_event("timeout", {"message": "Max wait time exceeded"})

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event_type: str, data: Dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# GET /api/v1/auto-extraction/samples
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/samples")
@login_required
def list_samples():
    """Return paginated list of auto-generated extraction samples."""
    try:
        from models import ExtractedSample  # type: ignore

        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 25)), 100)
        doc_type = request.args.get("doc_type")
        min_conf = float(request.args.get("min_confidence", 0))

        q = ExtractedSample.query
        if doc_type:
            q = q.filter_by(document_type=doc_type)
        if min_conf > 0:
            q = q.filter(ExtractedSample.confidence_score >= min_conf)

        q = q.order_by(ExtractedSample.created_at.desc())
        total = q.count()
        samples = q.offset((page - 1) * per_page).limit(per_page).all()

        return jsonify({
            "ok": True,
            "total": total,
            "page": page,
            "per_page": per_page,
            "samples": [s.to_dict() for s in samples],
        }), 200

    except Exception as exc:
        logger.exception("list_samples failed")
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /api/v1/auto-extraction/samples/<id>
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/samples/<int:sample_id>")
@login_required
def get_sample(sample_id: int):
    """Get a single extracted sample by ID."""
    try:
        from models import ExtractedSample  # type: ignore
        sample = ExtractedSample.query.get_or_404(sample_id)
        return jsonify({"ok": True, "sample": sample.to_dict()}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# DELETE /api/v1/auto-extraction/samples/<id>
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/samples/<int:sample_id>",
                           methods=["DELETE"])
@login_required
def delete_sample(sample_id: int):
    """Delete a sample from the database."""
    try:
        from models import ExtractedSample, db  # type: ignore
        sample = ExtractedSample.query.get_or_404(sample_id)
        db.session.delete(sample)
        db.session.commit()
        return jsonify({"ok": True, "deleted": sample_id}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /api/v1/auto-extraction/train-ml
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/train-ml", methods=["POST"])
@login_required
def train_ml():
    """Train / retrain the ML field classifier from accumulated samples."""
    try:
        learner = _get_feedback_learner()
        result = learner.retrain_field_classifier(
            limit=int(request.json.get("limit", 2000)) if request.is_json else 2000
        )
        return jsonify({"ok": True, "result": result}), 200
    except Exception as exc:
        logger.exception("train_ml failed")
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /api/v1/auto-extraction/feedback
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/feedback", methods=["POST"])
@login_required
def submit_feedback():
    """
    Submit field corrections to improve extraction accuracy.

    JSON body:
      {
        "sample_id": 42,
        "original_fields": {"Name": "Jhn Doe"},
        "corrected_fields": {"Name": "John Doe"},
        "doc_type": "Invoice"
      }
    """
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    data = request.get_json()
    sample_id = data.get("sample_id")
    original = data.get("original_fields", {})
    corrected = data.get("corrected_fields", {})
    doc_type = data.get("doc_type", "Unknown")

    if not corrected:
        return jsonify({"error": "corrected_fields required"}), 400

    try:
        learner = _get_feedback_learner()
        result = learner.record_correction(
            sample_id=sample_id,
            original_fields=original,
            corrected_fields=corrected,
            doc_type=doc_type,
            user_id=current_user.id if current_user.is_authenticated else None,
        )
        return jsonify({"ok": True, "result": result}), 200
    except Exception as exc:
        logger.exception("submit_feedback failed")
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /api/v1/auto-extraction/jobs
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/jobs")
@login_required
def list_jobs():
    """List recent batch extraction jobs."""
    try:
        from models import ExtractionJob  # type: ignore
        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 20)), 100)
        jobs = (
            ExtractionJob.query
            .order_by(ExtractionJob.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return jsonify({
            "ok": True,
            "jobs": [j.to_dict() for j in jobs],
        }), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /api/v1/auto-extraction/jobs/<job_id>
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/jobs/<job_id>")
@login_required
def get_job_status(job_id: str):
    """Get status of a batch job by its UUID job_id."""
    try:
        from backend.services.batch_intelligent_processor import _JOB_REGISTRY  # noqa
    except ImportError:
        from services.batch_intelligent_processor import _JOB_REGISTRY  # type: ignore

    job = _JOB_REGISTRY.get(job_id)
    if job:
        return jsonify({"ok": True, "job": job.to_dict()}), 200

    # Try DB
    try:
        from models import ExtractionJob  # type: ignore
        db_job = ExtractionJob.query.filter_by(job_id=job_id).first()
        if db_job:
            return jsonify({"ok": True, "job": db_job.to_dict()}), 200
    except Exception:
        pass

    return jsonify({"error": "Job not found"}), 404


# ---------------------------------------------------------------------------
# POST /api/v1/auto-extraction/classify
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/classify", methods=["POST"])
@login_required
def classify_document():
    """Classify a document type from uploaded file or text payload."""
    text = ""

    if request.is_json:
        text = request.get_json().get("text", "")
        filename = request.get_json().get("filename", "")
    elif "file" in request.files:
        f = request.files["file"]
        filename = secure_filename(f.filename or "doc")
        data = f.read()
        ext = os.path.splitext(filename.lower())[1]
        if ext == ".txt":
            text = data.decode("utf-8", errors="replace")
        else:
            try:
                import fitz
                doc = fitz.open(stream=data, filetype="pdf")
                text = "".join(page.get_text() for page in doc)
                doc.close()
            except Exception:
                text = data.decode("utf-8", errors="replace")
    else:
        return jsonify({"error": "Provide JSON {text} or a file upload"}), 400

    try:
        from backend.ml.doc_classifier import DocClassifier
    except ImportError:
        from ml.doc_classifier import DocClassifier  # type: ignore

    clf = DocClassifier()
    doc_type, confidence, tools = clf.classify(text, filename=filename)
    all_types = clf.classify_all(text, filename=filename)

    return jsonify({
        "ok": True,
        "doc_type": doc_type,
        "confidence": confidence,
        "preferred_tools": tools,
        "all_matches": all_types[:5],
    }), 200


# ---------------------------------------------------------------------------
# GET /api/v1/auto-extraction/stats
# ---------------------------------------------------------------------------

@auto_extraction_bp.route("/api/v1/auto-extraction/stats")
@login_required
def get_stats():
    """Return sample database and ML model statistics."""
    try:
        builder = _get_sample_builder()
        sample_stats = builder.generate_stats()

        learner = _get_feedback_learner()
        improvement_stats = learner.get_improvement_stats()

        try:
            from models import ExtractionJob  # type: ignore
            total_jobs = ExtractionJob.query.count()
            active_jobs = ExtractionJob.query.filter(
                ExtractionJob.status.in_(["queued", "running"])
            ).count()
        except Exception:
            total_jobs = 0
            active_jobs = 0

        return jsonify({
            "ok": True,
            "sample_db": sample_stats,
            "improvement": improvement_stats,
            "jobs": {
                "total": total_jobs,
                "active": active_jobs,
            },
        }), 200

    except Exception as exc:
        logger.exception("get_stats failed")
        return jsonify({"error": str(exc)}), 500
