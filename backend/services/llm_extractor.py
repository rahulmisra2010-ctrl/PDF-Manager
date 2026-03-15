"""
backend/services/llm_extractor.py — LLM-powered structured field extraction.

Uses OpenAI GPT (or any compatible API) to understand document semantics
and extract structured key-value fields with context awareness.

Environment variables:
  OPENAI_API_KEY  — Required for GPT extraction
  OPENAI_MODEL    — Model to use (default: gpt-3.5-turbo)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Optional OpenAI dependency
try:
    from openai import OpenAI  # type: ignore
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False
    logger.info("openai package not installed – LLMExtractor will return empty results")

_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

_EXTRACTION_PROMPT = """You are an intelligent document information extractor.
Analyze the following document text and extract ALL key-value information.

Rules:
1. Extract every field you can identify (names, dates, amounts, addresses, IDs, etc.)
2. Use clear, human-readable field names as keys
3. Return ONLY valid JSON (no markdown, no explanation)
4. Values must be strings
5. If a field appears multiple times, keep the most specific value
6. Infer document type from content and add a "document_type" field

Document Text:
{text}

JSON Response:"""

_VALIDATION_PROMPT = """You are a data quality validator for document extraction.
Review the extracted fields below for a {doc_type} document.

Extracted Fields:
{fields_json}

For each field:
1. Verify the value is reasonable for the field name
2. Flag any obvious errors (wrong format, missing required fields)
3. Suggest corrections if needed

Return JSON with structure:
{{
  "valid_fields": {{"field_name": "value", ...}},
  "corrections": {{"field_name": "corrected_value", ...}},
  "anomalies": ["description of anomaly", ...],
  "overall_confidence": 0.0-1.0
}}"""


class LLMExtractor:
    """
    Extracts structured fields from document text using LLM (GPT).

    Usage::

        extractor = LLMExtractor()
        fields = extractor.extract(text)
        result = extractor.validate_and_correct(fields, doc_type="Invoice")
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model or _OPENAI_MODEL
        self._client: Optional[OpenAI] = None
        if _OPENAI_AVAILABLE and self._api_key:
            self._client = OpenAI(api_key=self._api_key)

    @property
    def available(self) -> bool:
        return _OPENAI_AVAILABLE and bool(self._api_key)

    def _call_llm(self, prompt: str, max_tokens: int = 1500) -> str:
        """Call the LLM API and return raw text response."""
        if not self._client:
            return ""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.error("LLM API call failed: %s", exc)
            return ""

    @staticmethod
    def _parse_json_response(text: str) -> Dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        if not text:
            return {}
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
        # Find first { ... } block
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON response: %.200s", cleaned)
            return {}

    def extract(
        self,
        text: str,
        doc_type: Optional[str] = None,
        max_text_chars: int = 3000,
    ) -> Dict[str, str]:
        """
        Extract structured fields from document text using GPT.

        Args:
            text:           Full document text to analyze.
            doc_type:       Optional hint for document type.
            max_text_chars: Truncate text to this length to stay within token limits.

        Returns:
            Dict of field_name → field_value strings.
        """
        if not self.available:
            logger.debug("LLMExtractor not available (no API key or openai not installed)")
            return {}

        # Truncate text to avoid exceeding context window
        truncated = text[:max_text_chars] if len(text) > max_text_chars else text

        prompt = _EXTRACTION_PROMPT.format(text=truncated)
        raw = self._call_llm(prompt, max_tokens=1200)
        parsed = self._parse_json_response(raw)

        # Ensure all values are strings
        fields: Dict[str, str] = {
            str(k): str(v) for k, v in parsed.items() if k and v is not None
        }
        logger.info("LLMExtractor extracted %d fields", len(fields))
        return fields

    def validate_and_correct(
        self,
        fields: Dict[str, str],
        doc_type: str = "Unknown",
    ) -> Dict:
        """
        Use LLM to validate extracted fields and suggest corrections.

        Returns a dict with keys:
          - ``valid_fields`` (Dict[str, str])
          - ``corrections`` (Dict[str, str])
          - ``anomalies`` (List[str])
          - ``overall_confidence`` (float)
        """
        if not self.available or not fields:
            return {
                "valid_fields": fields,
                "corrections": {},
                "anomalies": [],
                "overall_confidence": 0.5,
            }

        prompt = _VALIDATION_PROMPT.format(
            doc_type=doc_type,
            fields_json=json.dumps(fields, indent=2),
        )
        raw = self._call_llm(prompt, max_tokens=1000)
        result = self._parse_json_response(raw)

        return {
            "valid_fields": result.get("valid_fields", fields),
            "corrections": result.get("corrections", {}),
            "anomalies": result.get("anomalies", []),
            "overall_confidence": float(result.get("overall_confidence", 0.5)),
        }

    def learn_from_correction(
        self,
        original: Dict[str, str],
        corrected: Dict[str, str],
        doc_type: str,
    ) -> None:
        """
        Record a user correction for future improvement.

        In production this would store the correction in the sample DB and
        retrain the model.  Currently logs the delta for audit.
        """
        delta = {
            k: {"from": original.get(k), "to": corrected[k]}
            for k in corrected
            if corrected[k] != original.get(k)
        }
        if delta:
            logger.info(
                "LLM correction recorded for %s: %s", doc_type, json.dumps(delta)
            )
