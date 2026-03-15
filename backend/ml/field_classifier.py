"""
backend/ml/field_classifier.py — ML-based field type classifier.

Trains a simple scikit-learn (or fallback regex) model on extracted samples
to classify field names and predict confidence scores.  The model learns
field patterns and formats from the auto-generated sample database and
improves with each extraction.

Dependencies (optional):
  pip install scikit-learn numpy
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional scikit-learn / numpy
# ---------------------------------------------------------------------------
try:
    import numpy as np  # type: ignore
    from sklearn.ensemble import RandomForestClassifier  # type: ignore
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
    from sklearn.pipeline import Pipeline  # type: ignore
    from sklearn.preprocessing import LabelEncoder  # type: ignore
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False
    logger.info("scikit-learn not installed – FieldClassifier uses regex fallback mode")

# ---------------------------------------------------------------------------
# Field type definitions
# ---------------------------------------------------------------------------

FIELD_TYPES = [
    "name",
    "email",
    "phone",
    "date",
    "address",
    "currency",
    "invoice_number",
    "company",
    "percentage",
    "quantity",
    "description",
    "id_number",
    "other",
]

# Regex heuristics used as fallback and feature generation
_FIELD_PATTERNS: Dict[str, str] = {
    "email": r"[\w.+-]+@[\w-]+\.[a-z]{2,}",
    "phone": r"(\+?\d[\d\s\-().]{6,}\d)",
    "date": r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{2}[/-]\d{2})\b",
    "currency": r"[$€£¥]\s?[\d,]+\.?\d*",
    "invoice_number": r"\b(INV|INVOICE|#)[\s\-]?\w+\b",
    "percentage": r"\b\d+(\.\d+)?%",
    "id_number": r"\b[A-Z]{0,3}\d{4,}\b",
}

_NAME_KEYWORDS = {"name", "first", "last", "full", "middle", "surname"}
_ADDRESS_KEYWORDS = {"address", "street", "city", "state", "zip", "postal", "country"}
_COMPANY_KEYWORDS = {"company", "business", "organization", "vendor", "supplier", "employer"}
_DESC_KEYWORDS = {"description", "detail", "note", "comment", "remark", "item"}


class FieldClassifier:
    """
    Classifies a (field_name, field_value) pair into a ``FIELD_TYPES`` category
    and returns a confidence score in [0.0, 1.0].

    Usage::

        clf = FieldClassifier()
        clf.train(samples)          # list of {"field_name": str, "field_value": str, "label": str}
        ftype, conf = clf.predict("Invoice Number", "INV-2024-001")
    """

    _MODEL_DIR = os.path.join(os.path.dirname(__file__), "saved_models")

    def __init__(self) -> None:
        self._pipeline: Optional[Pipeline] = None
        self._label_encoder: Optional[LabelEncoder] = None
        self._trained = False
        self._sample_count = 0

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    @staticmethod
    def _featurize(field_name: str, field_value: str) -> str:
        """Convert (name, value) pair into a feature string for TF-IDF."""
        name_lower = field_name.lower()
        value_lower = str(field_value).lower()

        flags: List[str] = []
        for ftype, pattern in _FIELD_PATTERNS.items():
            if re.search(pattern, field_value, re.IGNORECASE):
                flags.append(f"FLAG_{ftype.upper()}")

        if any(k in name_lower for k in _NAME_KEYWORDS):
            flags.append("FLAG_NAME")
        if any(k in name_lower for k in _ADDRESS_KEYWORDS):
            flags.append("FLAG_ADDRESS")
        if any(k in name_lower for k in _COMPANY_KEYWORDS):
            flags.append("FLAG_COMPANY")
        if any(k in name_lower for k in _DESC_KEYWORDS):
            flags.append("FLAG_DESC")

        return f"{name_lower} {value_lower} {' '.join(flags)}"

    # ------------------------------------------------------------------
    # Regex-only fallback prediction
    # ------------------------------------------------------------------

    @staticmethod
    def _regex_predict(field_name: str, field_value: str) -> Tuple[str, float]:
        """Heuristic prediction without ML model."""
        name_lower = field_name.lower()
        value_str = str(field_value)

        for ftype, pattern in _FIELD_PATTERNS.items():
            if re.search(pattern, value_str, re.IGNORECASE):
                return ftype, 0.75

        if any(k in name_lower for k in _NAME_KEYWORDS):
            return "name", 0.70
        if any(k in name_lower for k in _ADDRESS_KEYWORDS):
            return "address", 0.70
        if any(k in name_lower for k in _COMPANY_KEYWORDS):
            return "company", 0.65
        if any(k in name_lower for k in _DESC_KEYWORDS):
            return "description", 0.60

        return "other", 0.40

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, samples: List[Dict]) -> Dict:
        """
        Train the classifier on labeled samples.

        Each sample must have:
          - ``field_name`` (str)
          - ``field_value`` (str)
          - ``label`` (str) — one of FIELD_TYPES

        Returns a dict with training metrics.
        """
        if not samples:
            logger.warning("FieldClassifier.train called with empty samples")
            return {"trained": False, "reason": "no samples"}

        valid = [
            s for s in samples
            if s.get("field_name") and s.get("label") in FIELD_TYPES
        ]
        if len(valid) < 2:
            return {"trained": False, "reason": "insufficient labeled samples"}

        X = [self._featurize(s["field_name"], s.get("field_value", "")) for s in valid]
        y_raw = [s["label"] for s in valid]

        if not _SKLEARN_AVAILABLE:
            self._sample_count = len(valid)
            logger.info("sklearn unavailable – regex-only mode; %d samples noted", len(valid))
            return {"trained": False, "reason": "sklearn not available", "samples": len(valid)}

        le = LabelEncoder()
        y = le.fit_transform(y_raw)

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=500)),
            ("clf", RandomForestClassifier(n_estimators=50, random_state=42)),
        ])
        pipeline.fit(X, y)

        self._pipeline = pipeline
        self._label_encoder = le
        self._trained = True
        self._sample_count = len(valid)

        logger.info("FieldClassifier trained on %d samples", len(valid))
        return {
            "trained": True,
            "samples": len(valid),
            "classes": list(le.classes_),
        }

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, field_name: str, field_value: str) -> Tuple[str, float]:
        """
        Predict the field type and return (label, confidence).

        Falls back to regex heuristics if the ML model is not trained.
        """
        if self._trained and _SKLEARN_AVAILABLE and self._pipeline is not None:
            feature = self._featurize(field_name, field_value)
            proba = self._pipeline.predict_proba([feature])[0]
            idx = int(proba.argmax())
            confidence = float(proba[idx])
            label = self._label_encoder.inverse_transform([idx])[0]
            return str(label), confidence

        return self._regex_predict(field_name, field_value)

    def predict_batch(self, pairs: List[Tuple[str, str]]) -> List[Dict]:
        """
        Predict field types for a list of (field_name, field_value) tuples.

        Returns a list of dicts: {"field_name", "field_value", "label", "confidence"}.
        """
        results = []
        for field_name, field_value in pairs:
            label, confidence = self.predict(field_name, field_value)
            results.append({
                "field_name": field_name,
                "field_value": field_value,
                "label": label,
                "confidence": round(confidence, 4),
            })
        return results

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Optional[str] = None) -> str:
        """Serialize model to disk using pickle. Returns the saved path."""
        import pickle

        save_dir = path or self._MODEL_DIR
        os.makedirs(save_dir, exist_ok=True)
        model_path = os.path.join(save_dir, "field_classifier.pkl")
        with open(model_path, "wb") as fh:
            pickle.dump(
                {
                    "pipeline": self._pipeline,
                    "label_encoder": self._label_encoder,
                    "trained": self._trained,
                    "sample_count": self._sample_count,
                },
                fh,
            )
        logger.info("FieldClassifier saved to %s", model_path)
        return model_path

    @classmethod
    def load(cls, path: Optional[str] = None) -> "FieldClassifier":
        """Load a previously saved model from disk."""
        import pickle

        model_path = path or os.path.join(cls._MODEL_DIR, "field_classifier.pkl")
        instance = cls()
        if not os.path.exists(model_path):
            logger.warning("No saved FieldClassifier found at %s", model_path)
            return instance
        with open(model_path, "rb") as fh:
            state = pickle.load(fh)  # noqa: S301
        instance._pipeline = state.get("pipeline")
        instance._label_encoder = state.get("label_encoder")
        instance._trained = state.get("trained", False)
        instance._sample_count = state.get("sample_count", 0)
        logger.info("FieldClassifier loaded from %s", model_path)
        return instance

    @property
    def is_trained(self) -> bool:
        return self._trained

    @property
    def sample_count(self) -> int:
        return self._sample_count
