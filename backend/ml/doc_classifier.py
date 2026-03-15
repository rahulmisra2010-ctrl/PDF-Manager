"""
backend/ml/doc_classifier.py — Intelligent document type classifier.

Auto-detects document type (Invoice, Receipt, ID, Contract, etc.) from text
content and selects the optimal extraction tool chain for each document.

Supports multi-language documents via keyword detection.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Document type definitions with keyword signatures and tool preferences
# ---------------------------------------------------------------------------

DOCUMENT_TYPES: Dict[str, Dict] = {
    "Invoice": {
        "keywords": [
            "invoice", "inv#", "invoice no", "invoice number", "bill to",
            "amount due", "total due", "payment due", "subtotal", "tax amount",
            "purchase order", "po number", "vendor", "supplier",
        ],
        "preferred_tools": ["mindee", "pdfplumber", "pymupdf", "llm"],
        "weight": 1.2,
    },
    "Receipt": {
        "keywords": [
            "receipt", "thank you for your purchase", "order confirmation",
            "total paid", "change due", "cashier", "transaction", "store",
            "pos receipt", "payment received",
        ],
        "preferred_tools": ["mindee", "tesseract", "llm"],
        "weight": 1.1,
    },
    "ID Document": {
        "keywords": [
            "date of birth", "dob", "nationality", "passport", "license",
            "identification", "id number", "expiry", "expiration", "issued by",
            "national id", "driver license", "driving licence",
        ],
        "preferred_tools": ["mindee", "tesseract", "llm"],
        "weight": 1.2,
    },
    "Contract": {
        "keywords": [
            "agreement", "contract", "terms and conditions", "whereas",
            "hereinafter", "signed by", "party of the first part",
            "obligations", "indemnify", "jurisdiction", "governing law",
            "confidentiality", "non-disclosure",
        ],
        "preferred_tools": ["pymupdf", "pdfplumber", "llm"],
        "weight": 1.0,
    },
    "Resume": {
        "keywords": [
            "resume", "curriculum vitae", "cv", "work experience", "education",
            "skills", "objective", "references", "employment history",
            "certifications", "linkedin", "github",
        ],
        "preferred_tools": ["pdfplumber", "pymupdf", "llm"],
        "weight": 1.0,
    },
    "Medical Record": {
        "keywords": [
            "patient", "diagnosis", "prescription", "medication", "dosage",
            "physician", "doctor", "hospital", "clinic", "treatment",
            "icd", "cpt code", "health record", "medical history",
        ],
        "preferred_tools": ["tesseract", "pdfplumber", "llm"],
        "weight": 1.1,
    },
    "Tax Form": {
        "keywords": [
            "tax", "w-2", "1099", "irs", "taxable income", "deduction",
            "gross income", "adjusted gross", "filing status", "ein",
            "ssn", "social security", "federal tax", "withholding",
        ],
        "preferred_tools": ["pdfplumber", "pymupdf", "llm"],
        "weight": 1.1,
    },
    "Bank Statement": {
        "keywords": [
            "account statement", "bank statement", "account number", "iban",
            "routing number", "balance", "deposit", "withdrawal", "transaction",
            "opening balance", "closing balance", "interest earned",
        ],
        "preferred_tools": ["pdfplumber", "pymupdf", "llm"],
        "weight": 1.0,
    },
    "Address Book": {
        "keywords": [
            "first name", "last name", "full name", "street address",
            "cell phone", "home phone", "work phone", "email address",
            "zip code", "postal code", "city", "state",
        ],
        "preferred_tools": ["pdfplumber", "pymupdf", "llm"],
        "weight": 1.0,
    },
    "Purchase Order": {
        "keywords": [
            "purchase order", "po#", "ship to", "bill to", "qty", "unit price",
            "item number", "description", "ordered by", "delivery date",
        ],
        "preferred_tools": ["mindee", "pdfplumber", "llm"],
        "weight": 1.1,
    },
}

# Fallback type
_DEFAULT_TYPE = "General Document"
_DEFAULT_TOOLS = ["pymupdf", "pdfplumber", "tesseract", "llm"]


class DocClassifier:
    """
    Classifies a document as one of the known DocumentType categories
    and recommends the best extraction tool chain.

    Usage::

        clf = DocClassifier()
        doc_type, confidence, tools = clf.classify(text)
    """

    def __init__(self, custom_types: Optional[Dict[str, Dict]] = None) -> None:
        self._types = dict(DOCUMENT_TYPES)
        if custom_types:
            self._types.update(custom_types)

    def classify(
        self, text: str, filename: str = ""
    ) -> Tuple[str, float, List[str]]:
        """
        Classify document text and return (doc_type, confidence, tools).

        Args:
            text:     Full extracted text of the document.
            filename: Optional filename hint (extension may help classification).

        Returns:
            Tuple of (document_type_name, confidence_score, preferred_tools).
        """
        if not text or not text.strip():
            return _DEFAULT_TYPE, 0.0, _DEFAULT_TOOLS

        text_lower = text.lower()
        scores: Dict[str, float] = {}

        for doc_type, meta in self._types.items():
            keywords = meta.get("keywords", [])
            weight = meta.get("weight", 1.0)
            hits = sum(1 for kw in keywords if kw.lower() in text_lower)
            if hits:
                score = (hits / len(keywords)) * weight
                scores[doc_type] = score

        if not scores:
            # Try filename extension hints
            fn_lower = filename.lower()
            if fn_lower.endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff")):
                return _DEFAULT_TYPE, 0.1, ["tesseract", "llm"]
            return _DEFAULT_TYPE, 0.0, _DEFAULT_TOOLS

        best_type = max(scores, key=lambda k: scores[k])
        raw_score = scores[best_type]

        # Normalise to [0, 1] — cap at 1.0
        confidence = min(raw_score * 5, 1.0)

        preferred_tools = self._types[best_type].get("preferred_tools", _DEFAULT_TOOLS)
        return best_type, round(confidence, 4), list(preferred_tools)

    def classify_all(self, text: str, filename: str = "") -> List[Dict]:
        """Return ranked list of all matching document types with scores."""
        if not text:
            return []

        text_lower = text.lower()
        results = []

        for doc_type, meta in self._types.items():
            keywords = meta.get("keywords", [])
            weight = meta.get("weight", 1.0)
            hits = sum(1 for kw in keywords if kw.lower() in text_lower)
            if hits:
                score = min((hits / len(keywords)) * weight * 5, 1.0)
                results.append({
                    "doc_type": doc_type,
                    "confidence": round(score, 4),
                    "keyword_hits": hits,
                    "preferred_tools": meta.get("preferred_tools", _DEFAULT_TOOLS),
                })

        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results

    def get_tools_for_type(self, doc_type: str) -> List[str]:
        """Return the preferred tool list for a given document type."""
        meta = self._types.get(doc_type, {})
        return list(meta.get("preferred_tools", _DEFAULT_TOOLS))

    @property
    def known_types(self) -> List[str]:
        return list(self._types.keys())
