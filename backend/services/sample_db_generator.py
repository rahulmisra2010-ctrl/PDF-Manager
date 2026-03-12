"""
backend/services/sample_db_generator.py — Automatic sample database generator.

Reads files from an upload directory (or from an in-memory list), runs the
full extraction pipeline on each file, detects document types, deduplicates,
and stores the results in the ``ExtractedSample`` table.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Minimum quality score to include a sample in the database
MIN_QUALITY_SCORE = float(os.environ.get("SAMPLE_MIN_QUALITY", "0.1"))


def _content_hash(fields: dict[str, str]) -> str:
    """Return a deterministic hash of the extracted fields for duplicate detection."""
    canonical = json.dumps(fields, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class SampleDbGenerator:
    """
    Automatically extract data from uploaded files and build a structured
    training / sample database.

    Usage::

        gen = SampleDbGenerator(flask_app=app)
        stats = gen.generate_from_files(files)  # list of (filename, bytes)
    """

    def __init__(
        self,
        flask_app: Any | None = None,
        *,
        mindee_key: str | None = None,
        koncile_key: str | None = None,
        openai_key: str | None = None,
        use_ocr: bool = True,
        min_quality: float = MIN_QUALITY_SCORE,
    ) -> None:
        self.flask_app = flask_app
        self.mindee_key = mindee_key or os.environ.get("MINDEE_API_KEY")
        self.koncile_key = koncile_key or os.environ.get("KONCILE_API_KEY")
        self.openai_key = openai_key or os.environ.get("OPENAI_API_KEY")
        self.use_ocr = use_ocr
        self.min_quality = min_quality

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_from_files(
        self,
        files: list[tuple[str, bytes]],
        job_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Extract data from *files* and persist to the sample database.

        Parameters
        ----------
        files:
            List of ``(filename, file_bytes)`` tuples.
        job_id:
            Optional FK to an :class:`~models.ExtractionJob` row.

        Returns
        -------
        dict
            ``{"processed": N, "saved": N, "skipped": N, "duplicates": N, "errors": N}``
        """
        from backend.services.extraction_pipeline import run_extraction_pipeline

        stats = {
            "processed": 0,
            "saved": 0,
            "skipped": 0,
            "duplicates": 0,
            "errors": 0,
        }

        seen_hashes: set[str] = self._load_existing_hashes()

        for filename, file_data in files:
            stats["processed"] += 1
            try:
                extraction = run_extraction_pipeline(
                    file_data,
                    filename,
                    mindee_key=self.mindee_key,
                    koncile_key=self.koncile_key,
                    openai_key=self.openai_key,
                    use_ocr=self.use_ocr,
                )
            except Exception as exc:
                logger.error("Extraction failed for %r: %s", filename, exc)
                stats["errors"] += 1
                continue

            fields = extraction.get("fields") or {}
            quality = extraction.get("quality_score") or 0.0

            if quality < self.min_quality and not fields:
                logger.debug("Skipping %r — quality %.2f below threshold", filename, quality)
                stats["skipped"] += 1
                continue

            # Duplicate detection
            content_hash = _content_hash(fields)
            if content_hash in seen_hashes:
                logger.debug("Skipping %r — duplicate content", filename)
                stats["duplicates"] += 1
                self._mark_duplicate(filename, job_id)
                continue
            seen_hashes.add(content_hash)

            saved = self._save_sample(extraction, filename, job_id, is_duplicate=False)
            if saved:
                stats["saved"] += 1
            else:
                stats["errors"] += 1

        return stats

    def generate_from_directory(
        self,
        directory: str,
        recursive: bool = False,
        job_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Scan *directory* for supported files and generate samples.

        Parameters
        ----------
        directory:
            Path to scan for PDF / image / DOCX / XLSX files.
        recursive:
            If ``True``, scan subdirectories as well.
        job_id:
            Optional FK to an :class:`~models.ExtractionJob` row.
        """
        from backend.services.batch_processor import SUPPORTED_EXTENSIONS

        files: list[tuple[str, bytes]] = []

        walk = os.walk(directory) if recursive else [(directory, [], os.listdir(directory))]

        for root, _dirs, filenames in walk:
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "rb") as fh:
                        files.append((fname, fh.read()))
                except OSError as exc:
                    logger.warning("Cannot read %r: %s", fpath, exc)

        return self.generate_from_files(files, job_id=job_id)

    def list_samples(
        self,
        *,
        document_type: str | None = None,
        min_quality: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Return samples from the database with optional filtering.

        Parameters
        ----------
        document_type:
            Filter by document type label (e.g. ``"invoice"``).
        min_quality:
            Minimum quality score filter.
        limit / offset:
            Pagination controls.
        """
        if self.flask_app is None:
            logger.warning("list_samples requires a Flask app context")
            return []

        with self.flask_app.app_context():
            from models import ExtractedSample

            query = ExtractedSample.query
            if document_type:
                query = query.filter_by(document_type=document_type)
            if min_quality is not None:
                query = query.filter(ExtractedSample.quality_score >= min_quality)

            rows = query.order_by(ExtractedSample.id.desc()).offset(offset).limit(limit).all()
            return [r.to_dict() for r in rows]

    def export_samples_json(
        self,
        *,
        document_type: str | None = None,
        min_quality: float | None = None,
    ) -> str:
        """Return all matching samples as a JSON string."""
        samples = self.list_samples(
            document_type=document_type,
            min_quality=min_quality,
            limit=10000,
        )
        return json.dumps(samples, ensure_ascii=False, indent=2)

    def export_samples_csv(
        self,
        *,
        document_type: str | None = None,
        min_quality: float | None = None,
    ) -> str:
        """Return all matching samples as a CSV string."""
        import csv
        import io

        samples = self.list_samples(
            document_type=document_type,
            min_quality=min_quality,
            limit=10000,
        )
        if not samples:
            return ""

        # Collect all field names across all samples
        all_field_names: set[str] = set()
        for s in samples:
            all_field_names.update((s.get("fields") or {}).keys())

        fieldnames = (
            ["id", "source_filename", "document_type", "extraction_tool", "quality_score"]
            + sorted(all_field_names)
        )

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for s in samples:
            row: dict[str, Any] = {
                "id": s["id"],
                "source_filename": s["source_filename"],
                "document_type": s["document_type"],
                "extraction_tool": s["extraction_tool"],
                "quality_score": s["quality_score"],
            }
            row.update(s.get("fields") or {})
            writer.writerow(row)

        return buf.getvalue()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_existing_hashes(self) -> set[str]:
        """Load content hashes from existing non-duplicate samples."""
        if self.flask_app is None:
            return set()
        try:
            with self.flask_app.app_context():
                from models import ExtractedSample

                rows = ExtractedSample.query.filter_by(is_duplicate=False).all()
                hashes: set[str] = set()
                for row in rows:
                    fields = json.loads(row.fields) if row.fields else {}
                    hashes.add(_content_hash(fields))
                return hashes
        except Exception as exc:
            logger.warning("Could not load existing hashes: %s", exc)
            return set()

    def _save_sample(
        self,
        extraction: dict[str, Any],
        filename: str,
        job_id: int | None,
        is_duplicate: bool,
    ) -> bool:
        """Persist a single extracted sample to the database."""
        if self.flask_app is None:
            return False
        try:
            with self.flask_app.app_context():
                from models import ExtractedSample, db

                sample = ExtractedSample(
                    job_id=job_id,
                    source_filename=filename,
                    document_type=extraction.get("document_type", "unknown"),
                    fields=json.dumps(extraction.get("fields") or {}),
                    confidence_scores=json.dumps(extraction.get("confidence") or {}),
                    extraction_tool=extraction.get("tool"),
                    quality_score=extraction.get("quality_score"),
                    raw_text=(extraction.get("raw_text") or "")[:5000],
                    is_duplicate=is_duplicate,
                )
                db.session.add(sample)
                db.session.commit()
                return True
        except Exception as exc:
            logger.error("Could not save sample for %r: %s", filename, exc)
            return False

    def _mark_duplicate(self, filename: str, job_id: int | None) -> None:
        """Save a record flagged as a duplicate (no fields stored)."""
        if self.flask_app is None:
            return
        try:
            with self.flask_app.app_context():
                from models import ExtractedSample, db

                sample = ExtractedSample(
                    job_id=job_id,
                    source_filename=filename,
                    document_type="unknown",
                    fields="{}",
                    is_duplicate=True,
                )
                db.session.add(sample)
                db.session.commit()
        except Exception as exc:
            logger.warning("Could not save duplicate marker for %r: %s", filename, exc)
