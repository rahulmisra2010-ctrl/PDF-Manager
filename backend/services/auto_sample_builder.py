"""
backend/services/auto_sample_builder.py — Automatic sample database builder.

Automatically extracts data from uploaded files, creates structured training
samples, stores metadata (confidence, source tool, document type), and
auto-generates labeled datasets for ML model training.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AutoSampleBuilder:
    """
    Builds the auto-extraction sample database from uploaded files.

    Integrates with the AutoExtractionPipeline to run extraction, then
    stores results in the ExtractedSample database table for later use
    as ML training data.

    Usage::

        from flask import current_app
        with current_app.app_context():
            builder = AutoSampleBuilder()
            sample = builder.build_sample(file_data, "invoice.pdf", job_id=1)
    """

    def __init__(self, pipeline=None) -> None:
        """
        Args:
            pipeline: Optional pre-configured AutoExtractionPipeline instance.
                      A new one is created if not provided.
        """
        self._pipeline = pipeline

    def _get_pipeline(self):
        if self._pipeline is None:
            try:
                from backend.services.auto_extraction_pipeline import AutoExtractionPipeline
            except ImportError:
                from services.auto_extraction_pipeline import AutoExtractionPipeline  # type: ignore
            self._pipeline = AutoExtractionPipeline()
        return self._pipeline

    def build_sample(
        self,
        file_data: bytes,
        filename: str,
        job_id: Optional[int] = None,
        save_to_db: bool = True,
        progress_cb=None,
    ) -> Dict[str, Any]:
        """
        Run extraction on a file and save the result as an ExtractedSample.

        Args:
            file_data:   Raw file bytes.
            filename:    Original filename.
            job_id:      Optional ExtractionJob.id to associate with.
            save_to_db:  If True, persist the sample to the database.
            progress_cb: Optional progress callback(step, pct).

        Returns:
            Dict representation of the created ExtractedSample.
        """
        pipeline = self._get_pipeline()
        result = pipeline.extract(file_data, filename=filename, progress_cb=progress_cb)

        sample_data = {
            "job_id": job_id,
            "filename": filename,
            "file_type": os.path.splitext(filename.lower())[1].lstrip("."),
            "document_type": result.get("doc_type", "Unknown"),
            "extracted_fields": json.dumps(result.get("fields", {})),
            "source_tool": ",".join(result.get("tools_used", [])),
            "confidence_score": result.get("confidence", 0.0),
            "llm_validated": "llm" in result.get("tools_used", []),
            "ml_scored": True,
            "raw_text": (result.get("raw_text") or "")[:5000],
        }

        if save_to_db:
            try:
                from models import ExtractedSample, db  # type: ignore
                sample = ExtractedSample(**sample_data)
                db.session.add(sample)
                db.session.commit()
                return sample.to_dict()
            except Exception as exc:
                logger.error("Failed to save sample to DB: %s", exc)
                # Fall through and return the dict anyway

        sample_data["id"] = None
        sample_data["created_at"] = datetime.utcnow().isoformat()
        sample_data["updated_at"] = sample_data["created_at"]
        sample_data["feedback_applied"] = False
        sample_data["feedback_notes"] = None
        return sample_data

    def build_samples_from_list(
        self,
        files: List[Dict[str, Any]],
        job_id: Optional[int] = None,
        progress_cb=None,
    ) -> List[Dict[str, Any]]:
        """
        Build samples from a list of {"filename": str, "data": bytes} dicts.

        Args:
            files:       List of file descriptor dicts.
            job_id:      Optional batch job ID.
            progress_cb: Optional overall progress callback(step, pct).

        Returns:
            List of ExtractedSample dicts.
        """
        samples = []
        total = len(files)
        for i, f in enumerate(files):
            fname = f.get("filename", f"file_{i+1}")
            data = f.get("data", b"")

            def _cb(step: str, pct: float, i=i, total=total) -> None:
                if progress_cb:
                    overall = (i + pct) / total
                    progress_cb(f"File {i+1}/{total}: {step}", overall)

            try:
                sample = self.build_sample(data, fname, job_id=job_id, progress_cb=_cb)
                samples.append(sample)
            except Exception as exc:
                logger.error("Sample build failed for %s: %s", fname, exc)
                samples.append({
                    "filename": fname,
                    "error": str(exc),
                    "confidence_score": 0.0,
                })

        return samples

    def export_samples_as_training_data(
        self,
        samples: Optional[List[Dict]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Export samples from DB as labeled training data for ML models.

        Returns a list of dicts with:
          - ``field_name``, ``field_value``, ``label``, ``doc_type``, ``confidence``
        """
        if samples is None:
            try:
                from models import ExtractedSample  # type: ignore
                rows = ExtractedSample.query.order_by(
                    ExtractedSample.created_at.desc()
                ).limit(limit).all()
                samples = [r.to_dict() for r in rows]
            except Exception as exc:
                logger.error("Failed to load samples from DB: %s", exc)
                return []

        training_data: List[Dict[str, Any]] = []
        for sample in samples:
            fields_json = sample.get("extracted_fields") or "{}"
            doc_type = sample.get("document_type", "Unknown")
            conf = sample.get("confidence_score", 0.5)
            try:
                fields = json.loads(fields_json) if isinstance(fields_json, str) else fields_json
            except json.JSONDecodeError:
                continue

            for field_name, field_value in fields.items():
                if field_name and field_value:
                    training_data.append({
                        "field_name": str(field_name),
                        "field_value": str(field_value),
                        "label": "other",  # will be relabeled by FieldClassifier
                        "doc_type": doc_type,
                        "confidence": conf,
                    })

        logger.info("Exported %d training pairs from %d samples", len(training_data), len(samples))
        return training_data

    def generate_stats(self) -> Dict[str, Any]:
        """Return summary statistics about the sample database."""
        try:
            from models import ExtractedSample  # type: ignore
            total = ExtractedSample.query.count()
            if total == 0:
                return {"total_samples": 0}

            # Doc type distribution
            from sqlalchemy import func  # type: ignore
            from models import db  # type: ignore

            type_counts = (
                db.session.query(
                    ExtractedSample.document_type,
                    func.count(ExtractedSample.id)
                )
                .group_by(ExtractedSample.document_type)
                .all()
            )

            avg_conf = (
                db.session.query(func.avg(ExtractedSample.confidence_score)).scalar()
                or 0.0
            )

            return {
                "total_samples": total,
                "avg_confidence": round(float(avg_conf), 4),
                "document_type_distribution": {
                    t: c for t, c in type_counts
                },
            }
        except Exception as exc:
            logger.error("generate_stats failed: %s", exc)
            return {"total_samples": 0, "error": str(exc)}
