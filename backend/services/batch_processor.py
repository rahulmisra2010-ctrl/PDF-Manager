"""
backend/services/batch_processor.py — Batch file processing service.

Processes multiple files (PDF, images, DOCX, XLSX, etc.) using the full
extraction pipeline with parallel processing, progress tracking, and
retries.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Maximum number of worker threads for parallel processing
_MAX_WORKERS = int(os.environ.get("BATCH_MAX_WORKERS", "4"))
# Number of retry attempts for failed extractions
_MAX_RETRIES = int(os.environ.get("BATCH_MAX_RETRIES", "2"))

# Supported file extensions
SUPPORTED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp",
    ".docx", ".xlsx", ".xls", ".txt",
}


def _is_supported(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in SUPPORTED_EXTENSIONS


def _process_single_file(
    file_data: bytes,
    filename: str,
    *,
    mindee_key: str | None,
    koncile_key: str | None,
    openai_key: str | None,
    use_ocr: bool,
    retries: int = _MAX_RETRIES,
) -> dict[str, Any]:
    """
    Run the extraction pipeline on a single file with retry logic.

    Returns a result dict with keys:
        filename, success, fields, confidence, tool, quality_score,
        document_type, raw_text, error
    """
    from backend.services.extraction_pipeline import run_extraction_pipeline

    result: dict[str, Any] = {
        "filename": filename,
        "success": False,
        "fields": {},
        "confidence": {},
        "tool": "none",
        "quality_score": 0.0,
        "document_type": "unknown",
        "raw_text": "",
        "error": None,
    }

    last_exc: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            extraction = run_extraction_pipeline(
                file_data,
                filename,
                mindee_key=mindee_key,
                koncile_key=koncile_key,
                openai_key=openai_key,
                use_ocr=use_ocr,
            )
            result.update(extraction)
            result["success"] = True
            return result
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Extraction attempt %d/%d failed for %r: %s",
                attempt,
                retries + 1,
                filename,
                exc,
            )

    result["error"] = str(last_exc)
    return result


class BatchProcessor:
    """
    Orchestrates parallel extraction over a list of (filename, bytes) pairs.

    Usage::

        processor = BatchProcessor(mindee_key="...", openai_key="...")
        job_id = processor.start_job(files)
        status = processor.get_job_status(job_id)
    """

    # In-memory job registry  {job_id → job_state_dict}
    _jobs: dict[str, dict[str, Any]] = {}

    def __init__(
        self,
        *,
        mindee_key: str | None = None,
        koncile_key: str | None = None,
        openai_key: str | None = None,
        use_ocr: bool = True,
        max_workers: int = _MAX_WORKERS,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> None:
        self.mindee_key = mindee_key
        self.koncile_key = koncile_key
        self.openai_key = openai_key
        self.use_ocr = use_ocr
        self.max_workers = max_workers
        self.progress_callback = progress_callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_job(
        self,
        files: list[tuple[str, bytes]],
        *,
        save_to_db: bool = True,
        flask_app: Any | None = None,
    ) -> str:
        """
        Kick off a batch extraction job asynchronously.

        Parameters
        ----------
        files:
            List of ``(filename, file_bytes)`` tuples.
        save_to_db:
            If ``True``, persist results to the ``ExtractedSample`` table.
        flask_app:
            Flask application instance — required when ``save_to_db=True``
            because the worker threads need an app context.

        Returns
        -------
        str
            A unique ``job_id`` that can be used with :meth:`get_job_status`.
        """
        job_id = str(uuid.uuid4())
        total = len(files)

        job_state: dict[str, Any] = {
            "job_id": job_id,
            "status": "running",
            "total_files": total,
            "processed_files": 0,
            "failed_files": 0,
            "results": [],
            "file_list": [f[0] for f in files],
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
        }
        BatchProcessor._jobs[job_id] = job_state

        # Persist job record to DB
        if save_to_db and flask_app is not None:
            self._create_db_job(job_id, files, flask_app)

        import threading

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, files, save_to_db, flask_app),
            daemon=True,
        )
        thread.start()
        return job_id

    def process_sync(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[dict[str, Any]]:
        """
        Process files synchronously and return results list.

        Useful for testing or small batches where async is not needed.
        """
        return self._extract_all(files)

    @classmethod
    def get_job_status(cls, job_id: str) -> dict[str, Any] | None:
        """Return the current state of a batch job, or ``None`` if not found."""
        return cls._jobs.get(job_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_job(
        self,
        job_id: str,
        files: list[tuple[str, bytes]],
        save_to_db: bool,
        flask_app: Any | None,
    ) -> None:
        job = BatchProcessor._jobs[job_id]
        try:
            results = self._extract_all(files, job=job)
            job["results"] = results
            job["status"] = (
                "completed"
                if job["failed_files"] == 0
                else "partial"
            )
        except Exception as exc:
            logger.error("Batch job %s failed: %s", job_id, exc)
            job["status"] = "failed"
            job["error"] = str(exc)
        finally:
            job["completed_at"] = datetime.utcnow().isoformat()

        if save_to_db and flask_app is not None:
            self._save_results_to_db(job_id, job.get("results", []), flask_app)

    def _extract_all(
        self,
        files: list[tuple[str, bytes]],
        job: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run extraction in parallel and return list of result dicts."""
        results: list[dict[str, Any]] = []
        total = len(files)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(
                    _process_single_file,
                    file_data,
                    filename,
                    mindee_key=self.mindee_key,
                    koncile_key=self.koncile_key,
                    openai_key=self.openai_key,
                    use_ocr=self.use_ocr,
                ): filename
                for filename, file_data in files
                if _is_supported(filename)
            }

            for future in as_completed(future_to_file):
                filename = future_to_file[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "filename": filename,
                        "success": False,
                        "fields": {},
                        "error": str(exc),
                    }

                results.append(result)

                if job is not None:
                    job["processed_files"] += 1
                    if not result.get("success"):
                        job["failed_files"] += 1

                if self.progress_callback:
                    processed = len(results)
                    try:
                        self.progress_callback(
                            future_to_file.get(future, ""), processed, total
                        )
                    except Exception:
                        pass

                logger.info(
                    "Processed %d/%d — %r success=%s",
                    len(results),
                    total,
                    filename,
                    result.get("success"),
                )

        return results

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _create_db_job(
        self,
        job_id: str,
        files: list[tuple[str, bytes]],
        flask_app: Any,
    ) -> None:
        try:
            with flask_app.app_context():
                from models import ExtractionJob, db

                job_record = ExtractionJob(
                    job_id=job_id,
                    status="running",
                    total_files=len(files),
                    file_list=json.dumps([f[0] for f in files]),
                    started_at=datetime.utcnow(),
                )
                db.session.add(job_record)
                db.session.commit()
        except Exception as exc:
            logger.warning("Could not persist ExtractionJob to DB: %s", exc)

    def _save_results_to_db(
        self,
        job_id: str,
        results: list[dict[str, Any]],
        flask_app: Any,
    ) -> None:
        try:
            with flask_app.app_context():
                from models import ExtractedSample, ExtractionJob, db

                job_record = ExtractionJob.query.filter_by(job_id=job_id).first()
                job_pk = job_record.id if job_record else None

                for r in results:
                    sample = ExtractedSample(
                        job_id=job_pk,
                        source_filename=r.get("filename", ""),
                        document_type=r.get("document_type", "unknown"),
                        fields=json.dumps(r.get("fields") or {}),
                        confidence_scores=json.dumps(r.get("confidence") or {}),
                        extraction_tool=r.get("tool"),
                        quality_score=r.get("quality_score"),
                        raw_text=(r.get("raw_text") or "")[:5000],
                    )
                    db.session.add(sample)

                if job_record:
                    job_record.status = (
                        BatchProcessor._jobs.get(job_id, {}).get("status", "completed")
                    )
                    job_record.processed_files = len(results)
                    failed = sum(1 for r in results if not r.get("success"))
                    job_record.failed_files = failed
                    job_record.completed_at = datetime.utcnow()
                    job_record.result_summary = json.dumps({
                        "total": len(results),
                        "success": len(results) - failed,
                        "failed": failed,
                    })

                db.session.commit()
                logger.info("Saved %d samples to DB for job %s", len(results), job_id)
        except Exception as exc:
            logger.error("Could not save batch results to DB: %s", exc)
