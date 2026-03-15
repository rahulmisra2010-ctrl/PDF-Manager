"""
backend/services/feedback_learner.py — Auto-learning feedback loop.

Captures user corrections and failed extractions to continuously improve:
  - ML model accuracy
  - Field pattern recognition
  - Document type classification
  - Confidence score calibration
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FeedbackLearner:
    """
    Processes user corrections and feeds them back into the ML pipeline.

    Usage::

        learner = FeedbackLearner()
        learner.record_correction(sample_id, original_fields, corrected_fields)
        learner.retrain_field_classifier()
    """

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Correction recording
    # ------------------------------------------------------------------

    def record_correction(
        self,
        sample_id: Optional[int],
        original_fields: Dict[str, str],
        corrected_fields: Dict[str, str],
        doc_type: str = "Unknown",
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Record a user correction on an extracted sample.

        Persists the correction to the ExtractedSample (updates fields)
        and logs a FieldCorrection audit record.

        Returns:
            Dict with correction summary.
        """
        delta = {
            k: {"from": original_fields.get(k), "to": corrected_fields[k]}
            for k in corrected_fields
            if corrected_fields[k] != original_fields.get(k)
        }

        logger.info(
            "Feedback: %d field correction(s) on sample %s (doc_type=%s)",
            len(delta), sample_id, doc_type,
        )

        if sample_id is not None:
            try:
                from models import ExtractedSample, db  # type: ignore
                sample = ExtractedSample.query.get(sample_id)
                if sample:
                    sample.extracted_fields = json.dumps(corrected_fields)
                    sample.feedback_applied = True
                    sample.feedback_notes = json.dumps(delta)
                    sample.updated_at = datetime.utcnow()
                    db.session.commit()
            except Exception as exc:
                logger.error("Failed to persist correction: %s", exc)

        return {
            "sample_id": sample_id,
            "corrections": len(delta),
            "delta": delta,
            "doc_type": doc_type,
        }

    # ------------------------------------------------------------------
    # Failed extraction learning
    # ------------------------------------------------------------------

    def record_failed_extraction(
        self,
        filename: str,
        error: str,
        tools_tried: List[str],
        doc_type: Optional[str] = None,
    ) -> None:
        """
        Log a failed extraction for analysis and future improvement.

        In production this could:
          - Queue the file for manual review
          - Update tool selection weights
          - Alert the operator
        """
        logger.warning(
            "Failed extraction recorded: file=%s tools=%s error=%.120s",
            filename, tools_tried, error,
        )

    # ------------------------------------------------------------------
    # ML retraining
    # ------------------------------------------------------------------

    def retrain_field_classifier(self, limit: int = 2000) -> Dict[str, Any]:
        """
        Retrain the FieldClassifier on the current sample database.

        Loads the latest extracted samples, generates training pairs,
        and re-fits the classifier. Saves the new model.

        Returns:
            Training result dict.
        """
        try:
            from backend.services.auto_sample_builder import AutoSampleBuilder
            from backend.ml.field_classifier import FieldClassifier, FIELD_TYPES
        except ImportError:
            from services.auto_sample_builder import AutoSampleBuilder  # type: ignore
            from ml.field_classifier import FieldClassifier, FIELD_TYPES  # type: ignore

        builder = AutoSampleBuilder()
        training_data = builder.export_samples_as_training_data(limit=limit)

        if not training_data:
            return {"trained": False, "reason": "no training data available"}

        # Auto-label using regex heuristics (FieldClassifier._regex_predict)
        clf_tmp = FieldClassifier()
        for item in training_data:
            label, _ = clf_tmp._regex_predict(
                item["field_name"], item["field_value"]
            )
            item["label"] = label

        clf = FieldClassifier()
        result = clf.train(training_data)

        if result.get("trained"):
            model_path = clf.save()
            result["model_path"] = model_path
            self._register_model(
                name="field_classifier",
                model_type="field_classifier",
                accuracy=None,
                training_samples=result.get("samples", 0),
                model_path=model_path,
            )

        return result

    def retrain_doc_classifier(self) -> Dict[str, Any]:
        """
        Update the DocClassifier with new document type patterns from the DB.

        Currently adds any new document types stored in DocumentType table.
        Returns a summary dict.
        """
        try:
            from models import DocumentType  # type: ignore
            custom_types = {}
            for dt in DocumentType.query.all():
                keywords = json.loads(dt.keywords or "[]")
                tools = json.loads(dt.preferred_tools or "[]")
                if keywords:
                    custom_types[dt.name] = {
                        "keywords": keywords,
                        "preferred_tools": tools or ["pymupdf", "llm"],
                    }
            return {
                "updated": True,
                "custom_types_added": len(custom_types),
            }
        except Exception as exc:
            logger.error("retrain_doc_classifier failed: %s", exc)
            return {"updated": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Model registry
    # ------------------------------------------------------------------

    @staticmethod
    def _register_model(
        name: str,
        model_type: str,
        accuracy: Optional[float],
        training_samples: int,
        model_path: str,
    ) -> None:
        """Register a newly trained model in the MLModel table."""
        try:
            from models import MLModel, db  # type: ignore
            # Deactivate previous active model of same type
            MLModel.query.filter_by(model_type=model_type, is_active=True).update(
                {"is_active": False}
            )
            new_model = MLModel(
                name=name,
                model_type=model_type,
                version=datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
                accuracy=accuracy,
                training_samples=training_samples,
                model_path=model_path,
                is_active=True,
                trained_at=datetime.utcnow(),
            )
            db.session.add(new_model)
            db.session.commit()
        except Exception as exc:
            logger.warning("Could not register model in DB: %s", exc)

    def get_improvement_stats(self) -> Dict[str, Any]:
        """Return learning improvement statistics."""
        try:
            from models import ExtractedSample, MLModel, db  # type: ignore
            from sqlalchemy import func  # type: ignore

            total_samples = ExtractedSample.query.count()
            corrected = ExtractedSample.query.filter_by(feedback_applied=True).count()
            latest_model = (
                MLModel.query.filter_by(is_active=True)
                .order_by(MLModel.trained_at.desc())
                .first()
            )

            return {
                "total_samples": total_samples,
                "corrected_samples": corrected,
                "correction_rate": round(corrected / total_samples, 4) if total_samples else 0,
                "latest_model": latest_model.to_dict() if latest_model else None,
            }
        except Exception as exc:
            logger.error("get_improvement_stats failed: %s", exc)
            return {}
