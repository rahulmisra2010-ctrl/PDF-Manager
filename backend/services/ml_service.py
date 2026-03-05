"""
ML service for intelligent data extraction using PyTorch and regex heuristics.
"""

import re
from dataclasses import dataclass, field

import torch
import torch.nn as nn

from config import settings
from models import ExtractedField


# ---------------------------------------------------------------------------
# Lightweight PyTorch classifier for field-type detection
# ---------------------------------------------------------------------------


class FieldClassifier(nn.Module):
    """
    Simple feed-forward network that classifies a text token as one of the
    known field types.  Input: bag-of-char-level n-gram features (256-d).
    Output: logit per field type.
    """

    FIELD_TYPES = [
        "name",
        "date",
        "amount",
        "address",
        "phone",
        "email",
        "invoice_number",
        "unknown",
    ]

    def __init__(self, input_dim: int = 256, hidden_dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, len(self.FIELD_TYPES)),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)

    @classmethod
    def featurize(cls, text: str) -> torch.Tensor:
        """Convert text to a 256-d bag-of-characters feature vector."""
        vec = torch.zeros(256)
        for ch in text[:512]:
            vec[ord(ch) % 256] += 1
        norm = vec.norm()
        if norm > 0:
            vec = vec / norm
        return vec


# ---------------------------------------------------------------------------
# Regex patterns for common field types
# ---------------------------------------------------------------------------

# Maximum lengths for key-value label and value extraction
_KV_MAX_LABEL_LEN = 40   # characters – keeps matches tight to field labels
_KV_MAX_VALUE_LEN = 200  # characters – prevents runaway matches on long lines

# Pre-compiled pattern for "Label: Value" and "Label\tValue" style lines
_KV_PATTERN = re.compile(
    rf"^([A-Za-z][A-Za-z0-9 _\-/]{{1,{_KV_MAX_LABEL_LEN}}})\s*[:\t]\s*(.{{1,{_KV_MAX_VALUE_LEN}}})$",
    re.MULTILINE,
)

_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("date", r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.compile(
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
    )),
    ("date", r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
     re.compile(
         r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
         re.IGNORECASE,
     )),
    ("amount", r"\$\s?\d[\d,]*(?:\.\d{1,2})?", re.compile(
        r"\$\s?\d[\d,]*(?:\.\d{1,2})?"
    )),
    ("email", r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.compile(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    )),
    ("phone", r"\+?1?\s*\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}", re.compile(
        r"\+?1?\s*\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}"
    )),
    ("invoice_number", r"\bINV[-\s]?\d{4,}\b", re.compile(
        r"\bINV[-\s]?\d{4,}\b", re.IGNORECASE
    )),
]


# ---------------------------------------------------------------------------
# Address Book field labels to detect in OCR text
# ---------------------------------------------------------------------------

ADDRESS_BOOK_FIELDS = [
    "Name",
    "Street Address",
    "City",
    "State",
    "Zip Code",
    "Home Phone",
    "Cell Phone",
    "Work Phone",
    "Email",
]

# Pre-compiled patterns for each Address Book field label.
# Matches the label followed by optional underscores/spaces and any trailing
# value on the same line.
_ADDRESS_BOOK_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        label,
        re.compile(
            rf"^{re.escape(label)}\s*[_\s]*(.*)$",
            re.MULTILINE | re.IGNORECASE,
        ),
    )
    for label in ADDRESS_BOOK_FIELDS
]


class MLService:
    """
    Service that combines regex heuristics with a lightweight PyTorch model
    to extract structured fields from PDF text.
    """

    def __init__(self):
        self.device = torch.device(
            "cuda" if settings.USE_GPU and torch.cuda.is_available() else "cpu"
        )
        self.classifier = FieldClassifier().to(self.device)
        self.classifier.eval()
        # In production, load pre-trained weights here:
        # self.classifier.load_state_dict(torch.load(settings.ML_MODEL_DIR + "/field_classifier.pt"))

    def extract_fields(
        self, text: str, tables: list[list[list[str]]]
    ) -> list[ExtractedField]:
        """
        Extract structured fields from raw PDF text and tables.

        Args:
            text: Full document text.
            tables: Detected table cells.

        Returns:
            List of ExtractedField instances.
        """
        fields: list[ExtractedField] = []
        seen: set[str] = set()

        # --- Regex-based extraction ---
        # Regex matches are deterministic, so assign high confidence directly
        # rather than consulting the untrained classifier.
        for field_type, _, pattern in _PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(0).strip()
                key = f"{field_type}:{value}"
                if key in seen:
                    continue
                seen.add(key)

                # Estimate page from character offset (rough heuristic)
                approx_page = max(1, text[:match.start()].count("\f") + 1)

                fields.append(
                    ExtractedField(
                        field_name=field_type,
                        value=value,
                        confidence=0.9,
                        page_number=approx_page,
                    )
                )

        # --- Key-value pair extraction (Label: Value patterns) ---
        for match in _KV_PATTERN.finditer(text):
            label = match.group(1).strip()
            value = match.group(2).strip()
            if not value:
                continue
            key = f"kv:{label}:{value}"
            if key in seen:
                continue
            seen.add(key)
            approx_page = max(1, text[:match.start()].count("\f") + 1)
            fields.append(
                ExtractedField(
                    field_name=label,
                    value=value,
                    confidence=0.8,
                    page_number=approx_page,
                )
            )

        # --- Table-based extraction ---
        for table_idx, table in enumerate(tables):
            for row in table:
                for cell in row:
                    cell_stripped = cell.strip()
                    if not cell_stripped:
                        continue
                    field_type = self._classify_text(cell_stripped)
                    confidence = self._classifier_confidence(
                        cell_stripped, field_type
                    )
                    if confidence >= settings.ML_CONFIDENCE_THRESHOLD:
                        key = f"{field_type}:{cell_stripped}"
                        if key not in seen:
                            seen.add(key)
                            fields.append(
                                ExtractedField(
                                    field_name=field_type,
                                    value=cell_stripped,
                                    confidence=round(confidence, 3),
                                    page_number=1,
                                )
                            )

        # --- Address Book field extraction ---
        # Detect labelled fields from OCR text (e.g. scanned address book forms).
        for label, pattern in _ADDRESS_BOOK_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(1).strip().lstrip("_")
                key = f"ab:{label}"
                if key in seen:
                    continue
                seen.add(key)
                approx_page = max(1, text[:match.start()].count("\f") + 1)
                fields.append(
                    ExtractedField(
                        field_name=label,
                        value=value,
                        confidence=0.85,
                        page_number=approx_page,
                    )
                )

        return fields

    def _classify_text(self, text: str) -> str:
        """Use the neural classifier to determine field type."""
        with torch.no_grad():
            features = FieldClassifier.featurize(text).unsqueeze(0).to(self.device)
            logits = self.classifier(features)
            class_idx = int(logits.argmax(dim=1).item())
        return FieldClassifier.FIELD_TYPES[class_idx]

    def _classifier_confidence(self, text: str, expected_type: str) -> float:
        """
        Return a confidence score in [0, 1] for the given text belonging to
        the expected_type field class.
        """
        with torch.no_grad():
            features = FieldClassifier.featurize(text).unsqueeze(0).to(self.device)
            logits = self.classifier(features)
            probs = torch.softmax(logits, dim=1).squeeze()

        if expected_type in FieldClassifier.FIELD_TYPES:
            idx = FieldClassifier.FIELD_TYPES.index(expected_type)
            return float(probs[idx].item())

        # Fall back to max probability
        return float(probs.max().item())
