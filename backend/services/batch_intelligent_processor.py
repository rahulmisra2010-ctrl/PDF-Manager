"""
backend/services/batch_intelligent_processor.py — Batch intelligent file processor.

Processes 1–10,000 files automatically in parallel using the AutoExtractionPipeline.
Features:
  - Parallel processing (ThreadPoolExecutor, CPU-optimised)
  - Smart tool selection per document
  - Real-time progress tracking with ETA
  - Auto-retry on failed extractions
  - Quality metrics aggregation
  - Job state management
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum parallel workers
_MAX_WORKERS = int(os.getenv("BATCH_MAX_WORKERS", "4"))
# Max retries per file
_MAX_RETRIES = int(os.getenv("BATCH_MAX_RETRIES", "2"))
# Maximum raw text characters stored per sample
_MAX_RAW_TEXT_LENGTH = 5000


class BatchJob:
    """In-memory state for a running or completed batch job."""

    def __init__(self, job_id: str, total: int) -> None:
        self.job_id = job_id
        self.total = total
        self.processed = 0
        self.failed = 0
        self.results: List[Dict[str, Any]] = []
        self.status = "queued"
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.events: List[Dict[str, Any]] = []  # SSE-style event log
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        self.status = "cancelled"

    @property
    def progress_pct(self) -> float:
        return round(self.processed / self.total * 100, 1) if self.total else 0.0

    @property
    def eta_seconds(self) -> Optional[float]:
        if not self.started_at or self.processed == 0:
            return None
        elapsed = time.monotonic() - self.started_at
        rate = self.processed / elapsed  # files per second
        remaining = self.total - self.processed
        return round(remaining / rate, 1) if rate > 0 else None

    def add_event(self, event_type: str, data: Dict) -> None:
        self.events.append({
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "total": self.total,
            "processed": self.processed,
            "failed": self.failed,
            "progress_pct": self.progress_pct,
            "eta_seconds": self.eta_seconds,
            "started_at": (
                datetime.utcfromtimestamp(self.started_at).isoformat()
                if self.started_at else None
            ),
            "completed_at": (
                datetime.utcfromtimestamp(self.completed_at).isoformat()
                if self.completed_at else None
            ),
            "event_count": len(self.events),
        }


# In-memory job registry (cleared on restart).
# TODO: In production, use Redis or DB-backed storage instead of in-memory registry.
_JOB_REGISTRY: Dict[str, BatchJob] = {}


class BatchIntelligentProcessor:
    """
    Processes a batch of files using the AutoExtractionPipeline in parallel.

    Usage::

        processor = BatchIntelligentProcessor()
        job_id = processor.start_batch(files, on_progress=my_callback)
        status = processor.get_job(job_id).to_dict()
    """

    def __init__(self, pipeline=None, max_workers: int = _MAX_WORKERS) -> None:
        self._pipeline = pipeline
        self._max_workers = max(1, max_workers)

    def _get_pipeline(self):
        if self._pipeline is None:
            try:
                from backend.services.auto_extraction_pipeline import AutoExtractionPipeline
            except ImportError:
                from services.auto_extraction_pipeline import AutoExtractionPipeline  # type: ignore
            self._pipeline = AutoExtractionPipeline()
        return self._pipeline

    def create_job(self, total_files: int) -> BatchJob:
        """Create and register a new batch job."""
        job_id = str(uuid.uuid4())
        job = BatchJob(job_id, total_files)
        _JOB_REGISTRY[job_id] = job
        return job

    @staticmethod
    def get_job(job_id: str) -> Optional[BatchJob]:
        """Retrieve a job by its ID."""
        return _JOB_REGISTRY.get(job_id)

    def start_batch(
        self,
        files: List[Dict[str, Any]],
        on_progress: Optional[Callable[[BatchJob], None]] = None,
        save_samples: bool = True,
        db_job_id: Optional[int] = None,
    ) -> str:
        """
        Start processing a batch of files asynchronously.

        Args:
            files:       List of {"filename": str, "data": bytes} dicts.
            on_progress: Optional callback called after each file completes.
            save_samples: If True, persist each sample to the database.
            db_job_id:   Optional ExtractionJob.id for DB association.

        Returns:
            job_id string — use get_job(job_id) to poll status.
        """
        job = self.create_job(len(files))
        job.status = "running"
        job.started_at = time.monotonic()

        # Persist job to DB if we have an app context
        self._persist_job_start(job, db_job_id)

        # Run in a background thread so we don't block the caller
        import threading
        thread = threading.Thread(
            target=self._run_batch,
            args=(job, files, on_progress, save_samples, db_job_id),
            daemon=True,
        )
        thread.start()
        return job.job_id

    def process_sync(
        self,
        files: List[Dict[str, Any]],
        save_samples: bool = True,
        db_job_id: Optional[int] = None,
    ) -> BatchJob:
        """
        Process files synchronously (blocking). Returns the completed BatchJob.
        """
        job = self.create_job(len(files))
        job.status = "running"
        job.started_at = time.monotonic()
        self._run_batch(job, files, None, save_samples, db_job_id)
        return job

    def _run_batch(
        self,
        job: BatchJob,
        files: List[Dict[str, Any]],
        on_progress: Optional[Callable],
        save_samples: bool,
        db_job_id: Optional[int],
    ) -> None:
        """Internal: process all files using a thread pool."""
        pipeline = self._get_pipeline()

        def _process_one(file_desc: Dict) -> Dict[str, Any]:
            fname = file_desc.get("filename", "unknown")
            data = file_desc.get("data", b"")
            retries = 0
            last_exc: Optional[Exception] = None

            while retries <= _MAX_RETRIES:
                if job._cancelled:
                    return {"filename": fname, "error": "job cancelled"}
                try:
                    result = pipeline.extract(data, filename=fname)
                    if save_samples:
                        self._save_sample(result, fname, db_job_id)
                    return result
                except Exception as exc:
                    last_exc = exc
                    retries += 1
                    logger.warning("Retry %d/%d for %s: %s", retries, _MAX_RETRIES, fname, exc)
                    time.sleep(0.5 * retries)

            return {"filename": fname, "error": str(last_exc), "fields": {}}

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_file = {
                executor.submit(_process_one, f): f
                for f in files
            }

            for future in as_completed(future_to_file):
                if job._cancelled:
                    break

                file_desc = future_to_file[future]
                fname = file_desc.get("filename", "unknown")

                try:
                    result = future.result()
                    if result.get("error"):
                        job.failed += 1
                        job.add_event("file_failed", {
                            "filename": fname, "error": result["error"]
                        })
                    else:
                        job.add_event("file_complete", {
                            "filename": fname,
                            "doc_type": result.get("doc_type"),
                            "confidence": result.get("confidence"),
                            "fields_count": len(result.get("fields", {})),
                        })
                    job.results.append(result)
                except Exception as exc:
                    job.failed += 1
                    job.add_event("file_error", {"filename": fname, "error": str(exc)})

                job.processed += 1
                if on_progress:
                    try:
                        on_progress(job)
                    except Exception:
                        pass

        job.completed_at = time.monotonic()
        job.status = "failed" if job.failed == job.total else "completed"
        self._persist_job_complete(job, db_job_id)

    def get_quality_summary(self, job: BatchJob) -> Dict[str, Any]:
        """Aggregate quality metrics across all results in a job."""
        results = [r for r in job.results if not r.get("error")]
        if not results:
            return {"processed": 0, "failed": job.failed}

        confs = [r.get("confidence", 0.0) for r in results]
        field_counts = [len(r.get("fields", {})) for r in results]
        doc_types = {}
        for r in results:
            dt = r.get("doc_type", "Unknown")
            doc_types[dt] = doc_types.get(dt, 0) + 1

        return {
            "processed": job.processed,
            "failed": job.failed,
            "avg_confidence": round(sum(confs) / len(confs), 4) if confs else 0,
            "avg_fields_per_doc": round(sum(field_counts) / len(field_counts), 1),
            "total_fields_extracted": sum(field_counts),
            "document_type_distribution": doc_types,
            "duration_seconds": (
                round(job.completed_at - job.started_at, 2)
                if job.completed_at and job.started_at else None
            ),
        }

    # ------------------------------------------------------------------
    # DB helpers (best-effort; skip on error)
    # ------------------------------------------------------------------

    @staticmethod
    def _save_sample(result: Dict, filename: str, db_job_id: Optional[int]) -> None:
        try:
            from models import ExtractedSample, db  # type: ignore
            sample = ExtractedSample(
                job_id=db_job_id,
                filename=filename,
                file_type=os.path.splitext(filename.lower())[1].lstrip("."),
                document_type=result.get("doc_type", "Unknown"),
                extracted_fields=json.dumps(result.get("fields", {})),
                source_tool=",".join(result.get("tools_used", [])),
                confidence_score=result.get("confidence", 0.0),
                llm_validated="llm" in result.get("tools_used", []),
                ml_scored=True,
                raw_text=(result.get("raw_text") or "")[:_MAX_RAW_TEXT_LENGTH],
            )
            db.session.add(sample)
            db.session.commit()
        except Exception as exc:
            logger.warning("Could not save sample to DB: %s", exc)

    @staticmethod
    def _persist_job_start(job: BatchJob, db_job_id: Optional[int]) -> None:
        if db_job_id is None:
            return
        try:
            from models import ExtractionJob, db  # type: ignore
            db_job = ExtractionJob.query.get(db_job_id)
            if db_job:
                db_job.status = "running"
                db_job.started_at = datetime.utcnow()
                db_job.total_files = job.total
                db.session.commit()
        except Exception:
            pass

    @staticmethod
    def _persist_job_complete(job: BatchJob, db_job_id: Optional[int]) -> None:
        if db_job_id is None:
            return
        try:
            from models import ExtractionJob, db  # type: ignore
            db_job = ExtractionJob.query.get(db_job_id)
            if db_job:
                db_job.status = job.status
                db_job.completed_at = datetime.utcnow()
                db_job.processed_files = job.processed
                db_job.failed_files = job.failed
                db.session.commit()
        except Exception:
            pass
