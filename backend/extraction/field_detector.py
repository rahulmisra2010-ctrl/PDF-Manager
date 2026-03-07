"""
backend/extraction/field_detector.py — NER and rule-based field detection.

Provides
--------
* Named Entity Recognition using spaCy (optional)
* Rule-based address-book field extraction
* Auto field-type detection
* Confidence scoring per field
* Multi-language stub (English default)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional spaCy NER
# ---------------------------------------------------------------------------

try:
    import spacy as _spacy
    _nlp = _spacy.load("en_core_web_sm")
    _SPACY_AVAILABLE = True
except Exception:
    _SPACY_AVAILABLE = False
    logger.info("spaCy en_core_web_sm not available — NER disabled, using rules only")


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}", re.I)
_PHONE_10_RE = re.compile(r"\b(\d{10})\b")
_PHONE_FULL_RE = re.compile(r"\+?[\d\s\-().]{10,15}")
_ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")
_STATE_ABBR_RE = re.compile(r"\b([A-Z]{2})\b")
_URL_RE = re.compile(r"https?://\S+", re.I)
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}"
    r"|\d{4}[/\-]\d{2}[/\-]\d{2})\b"
)


@dataclass
class DetectedField:
    """A single detected field with type, value, and confidence."""

    field_name: str
    value: str
    field_type: str          # name/phone/email/address/city/state/zip/date/text
    confidence: float        # 0.0 – 1.0
    source: str = "rule"     # rule/ner/rag
    bbox: dict | None = None

    @property
    def confidence_pct(self) -> float:
        return round(self.confidence * 100, 1)

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "value": self.value,
            "field_type": self.field_type,
            "confidence": round(self.confidence, 4),
            "confidence_pct": self.confidence_pct,
            "source": self.source,
            "bbox": self.bbox,
        }


# ---------------------------------------------------------------------------
# FieldDetector
# ---------------------------------------------------------------------------

class FieldDetector:
    """
    Detect and classify address-book fields from raw text.

    Supported fields
    ----------------
    Name, Cell Phone, Home Phone, Work Phone, Email,
    Street Address, City, State, Zip Code, and generic text.

    Usage::

        detector = FieldDetector()
        fields = detector.detect(text)
    """

    # Ordered address-book labels to look for
    _AB_FIELDS = [
        ("Name",           re.compile(r"^Name\s+\S", re.I),           "name"),
        ("Street Address", re.compile(r"^Street\s+Address", re.I),     "address"),
        ("City",           re.compile(r"^City\s*:", re.I),             "city"),
        ("State",          re.compile(r"^State\s*:", re.I),            "state"),
        ("Zip Code",       re.compile(r"^Zip\s*Code\s*:", re.I),       "zip"),
        ("Home Phone",     re.compile(r"^Home\s*Phone\s*:", re.I),     "phone"),
        ("Cell Phone",     re.compile(r"^Cell\s*Phone\s*:", re.I),     "phone"),
        ("Work Phone",     re.compile(r"^Work\s*Phone\s*:", re.I),     "phone"),
        ("Email",          re.compile(r"^Email\s*:", re.I),            "email"),
    ]

    _SPLIT_RE = re.compile(
        r"(?<!\A)\s*[\"']?\s*(?="
        r"(?:Street\s+Address|Zip\s*Code|Home\s*Phone|Cell\s*Phone|Work\s*Phone|City|State|Email)"
        r"\s*[:\s])",
        re.IGNORECASE,
    )

    def _expand(self, lines: list[str]) -> list[str]:
        expanded: list[str] = []
        for raw in lines:
            parts = self._SPLIT_RE.split(raw)
            expanded.extend(p.strip() for p in parts if p.strip())
        return expanded

    @staticmethod
    def _clean(val: str) -> str:
        return val.strip('_" :').strip()

    @staticmethod
    def _extract_phone(segment: str) -> str | None:
        digits = re.sub(r"\D", "", segment)
        m = re.search(r"\d{10}", digits)
        return m.group() if m else None

    @staticmethod
    def _is_label(line: str) -> bool:
        for _, pat, _ in FieldDetector._AB_FIELDS:
            if pat.match(line.strip().lstrip('"\'_ ')):
                return True
        return False

    def detect(self, text: str) -> list[DetectedField]:
        """
        Detect fields from raw text using rules (+ NER if spaCy available).

        Args:
            text: Raw extracted or OCR text.

        Returns:
            List of :class:`DetectedField` objects in reading order.
        """
        fields = self._rule_detect(text)

        # Supplement with spaCy NER for name detection if not found
        if _SPACY_AVAILABLE:
            ner_fields = self._ner_detect(text, existing=fields)
            fields.extend(ner_fields)

        # Auto-classify any leftover values
        fields = self._deduplicate(fields)
        return fields

    def _rule_detect(self, text: str) -> list[DetectedField]:
        lines = self._expand(text.splitlines())
        result: list[DetectedField] = []
        i = 0
        while i < len(lines):
            line = lines[i].strip().lstrip('"\'')
            if not line:
                i += 1
                continue

            matched = False
            for label, pattern, ftype in self._AB_FIELDS:
                if not pattern.match(line):
                    continue
                matched = True
                if ftype == "name":
                    val = re.sub(r"^Name\s+", "", line, flags=re.I).strip()
                    if val:
                        result.append(DetectedField(label, val, "name", 0.92, "rule"))

                elif ftype == "address":
                    label_m = re.match(r"^Street\s+Address\s*:?\s*", line, re.I)
                    inline = line[label_m.end():].strip() if label_m else ""
                    city_m = re.search(r"\s+City\s*:", inline, re.I)
                    if city_m:
                        inline = inline[:city_m.start()].strip()
                    parts = [inline] if inline else []
                    i += 1
                    while i < len(lines):
                        nxt = lines[i].strip()
                        if self._is_label(nxt):
                            break
                        if nxt:
                            parts.append(nxt)
                        i += 1
                    if parts:
                        result.append(DetectedField(label, ", ".join(parts), "address", 0.88, "rule"))
                    continue  # i already advanced

                elif ftype == "city":
                    raw = re.sub(r"^City\s*:\s*", "", line, flags=re.I)
                    val = re.split(r'\s+(?:State|Zip|Home|Cell|Work|Email)\s*:', raw, 1, re.I)[0]
                    val = self._clean(val)
                    if val:
                        result.append(DetectedField(label, val, "city", 0.90, "rule"))

                elif ftype == "state":
                    raw = re.sub(r"^State\s*:\s*", "", line, flags=re.I)
                    val = re.split(r'\s+(?:Zip|Home|Cell|Work|Email)\s*:', raw, 1, re.I)[0]
                    val = self._clean(val)
                    if val:
                        result.append(DetectedField(label, val, "state", 0.90, "rule"))

                elif ftype == "zip":
                    raw = re.sub(r"^Zip\s*Code\s*:\s*", "", line, flags=re.I)
                    val = re.split(r'\s+(?:Home|Cell|Work|Email)\s*:', raw, 1, re.I)[0]
                    val = self._clean(val)
                    if val:
                        result.append(DetectedField(label, val, "zip", 0.92, "rule"))

                elif ftype == "phone":
                    raw = re.sub(
                        r"^(?:Home|Cell|Work)\s*Phone\s*:\s*", "", line, flags=re.I
                    )
                    phone = self._extract_phone(raw)
                    if not phone:
                        j = i + 1
                        while j < len(lines):
                            nxt = lines[j].strip()
                            if nxt and self._is_label(nxt):
                                break
                            if nxt:
                                phone = self._extract_phone(nxt)
                                if phone:
                                    break
                            j += 1
                    if phone:
                        result.append(DetectedField(label, phone, "phone", 0.95, "rule"))

                elif ftype == "email":
                    raw = re.sub(r"^Email\s*:\s*", "", line, flags=re.I).strip()
                    m = _EMAIL_RE.search(raw)
                    val = m.group() if m else raw.strip()
                    if val:
                        result.append(DetectedField(label, val, "email", 0.95, "rule"))

                break  # only one label per line

            if not matched:
                # Scan for emails/phones not captured by label matching
                if _EMAIL_RE.search(line):
                    m = _EMAIL_RE.search(line)
                    result.append(DetectedField("Email", m.group(), "email", 0.80, "rule"))
                elif _PHONE_10_RE.search(line):
                    m = _PHONE_10_RE.search(line)
                    result.append(DetectedField("Phone", m.group(), "phone", 0.75, "rule"))

            i += 1
        return result

    def _ner_detect(
        self, text: str, existing: list[DetectedField]
    ) -> list[DetectedField]:
        """Use spaCy NER to find PERSON entities not yet captured."""
        existing_names = {f.value.lower() for f in existing if f.field_type == "name"}
        doc = _nlp(text[:5000])  # limit for performance
        new_fields: list[DetectedField] = []
        for ent in doc.ents:
            if ent.label_ == "PERSON" and ent.text.lower() not in existing_names:
                new_fields.append(
                    DetectedField("Name", ent.text.strip(), "name", 0.80, "ner")
                )
                existing_names.add(ent.text.lower())
        return new_fields

    @staticmethod
    def _deduplicate(fields: list[DetectedField]) -> list[DetectedField]:
        """Remove duplicate fields (same field_name), keeping highest confidence."""
        seen: dict[str, DetectedField] = {}
        for f in fields:
            key = f.field_name
            if key not in seen or f.confidence > seen[key].confidence:
                seen[key] = f
        return list(seen.values())

    def auto_detect_type(self, value: str) -> str:
        """Classify a raw value string into a field type."""
        v = value.strip()
        if _EMAIL_RE.match(v):
            return "email"
        if _URL_RE.match(v):
            return "url"
        if _PHONE_10_RE.match(v):
            return "phone"
        if _ZIP_RE.match(v):
            return "zip"
        if _DATE_RE.search(v):
            return "date"
        return "text"
