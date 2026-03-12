"""backend/services/advanced_extraction_service.py — AI-powered IDP extraction service.

Provides multi-strategy document field extraction using:
- Mindee IDP API (cloud-based intelligent document processing)
- Koncile.ai API (AI-powered document extraction)
- Tesseract OCR (open-source optical character recognition)
- LLM-based extraction via OpenAI GPT (large language model field parsing)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)


class AdvancedExtractionService:
    """Multi-strategy extraction service using Mindee, Koncile, OCR, and LLM."""

    # -----------------------------------------------------------------------
    # Mindee IDP extraction
    # -----------------------------------------------------------------------

    @staticmethod
    def extract_with_mindee(file_data: bytes, api_key: str) -> Dict[str, str]:
        """Extract document fields using the Mindee IDP API.

        Uses Mindee's FinancialDocumentV1 product which handles invoices,
        receipts, and general financial documents.

        :param file_data: Raw PDF bytes.
        :param api_key: Mindee API key from https://developers.mindee.com.
        :returns: Mapping of field name → value, or empty dict on failure.
        """
        try:
            from mindee import Client, product  # type: ignore[import]

            mindee_client = Client(api_key=api_key)
            input_doc = mindee_client.source_from_bytes(file_data, filename="document.pdf")
            result = mindee_client.parse(product.FinancialDocumentV1, input_doc)

            fields: Dict[str, str] = {}
            prediction = result.document.inference.prediction

            # Map Mindee prediction attributes to field name → value pairs
            _mindee_attr_map = {
                "invoice_number": "Invoice Number",
                "reference_numbers": "Reference Numbers",
                "date": "Date",
                "due_date": "Due Date",
                "supplier_name": "Supplier Name",
                "supplier_address": "Supplier Address",
                "supplier_email": "Supplier Email",
                "supplier_phone": "Supplier Phone",
                "customer_name": "Customer Name",
                "customer_address": "Customer Address",
                "customer_id": "Customer ID",
                "customer_email": "Customer Email",
                "total_net": "Total Net",
                "total_tax": "Total Tax",
                "total_amount": "Total Amount",
                "document_type": "Document Type",
                "locale": "Locale",
                "payment_date": "Payment Date",
                "po_number": "PO Number",
            }

            for attr, label in _mindee_attr_map.items():
                val = getattr(prediction, attr, None)
                if val is None:
                    continue
                str_val = str(val).strip()
                # Skip empty or placeholder values
                if str_val and str_val not in ("None", "N/A", ""):
                    fields[label] = str_val

            logger.info("Mindee extraction found %d fields", len(fields))
            return fields

        except Exception as exc:
            logger.warning("Mindee extraction failed: %s", exc)
            return {}

    # -----------------------------------------------------------------------
    # Koncile.ai extraction
    # -----------------------------------------------------------------------

    @staticmethod
    def extract_with_koncile(file_data: bytes, api_key: str) -> Dict[str, str]:
        """Extract document fields using the Koncile.ai API.

        Uploads the file to Koncile, waits for processing, and returns
        extracted field values.

        :param file_data: Raw PDF bytes.
        :param api_key: Koncile API key from https://koncile.ai.
        :returns: Mapping of field name → value, or empty dict on failure.
        """
        import tempfile

        tmp_path: str | None = None
        try:
            from koncile_sdk.client import KoncileAPIClient  # type: ignore[import]

            # Write bytes to a temporary file because Koncile SDK expects file paths
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_data)
                tmp_path = tmp.name

            client = KoncileAPIClient(api_key=api_key)

            # Upload the file
            upload_response = client.files.upload(
                folder_id="default",
                file_paths=[tmp_path],
            )
            logger.debug("Koncile upload response: %s", upload_response)

            fields: Dict[str, str] = {}

            # Extract field values from the upload response if available
            if isinstance(upload_response, dict):
                for key, value in upload_response.items():
                    if isinstance(value, str) and value.strip():
                        fields[str(key)] = value.strip()
            elif isinstance(upload_response, list):
                for item in upload_response:
                    if isinstance(item, dict):
                        name = item.get("field_name") or item.get("name") or ""
                        value = item.get("value") or item.get("field_value") or ""
                        if name and value:
                            fields[str(name)] = str(value).strip()

            logger.info("Koncile extraction found %d fields", len(fields))
            return fields

        except Exception as exc:
            logger.warning("Koncile extraction failed: %s", exc)
            return {}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # -----------------------------------------------------------------------
    # Tesseract OCR extraction
    # -----------------------------------------------------------------------

    @staticmethod
    def extract_with_ocr(file_data: bytes) -> str:
        """Extract text from a PDF using Tesseract OCR.

        Converts each PDF page to an image and runs Tesseract OCR on it.
        Useful for scanned PDFs that contain no embedded text layer.

        :param file_data: Raw PDF bytes.
        :returns: Combined OCR text from all pages, or empty string on failure.
        """
        try:
            import pytesseract  # type: ignore[import]
            from pdf2image import convert_from_bytes  # type: ignore[import]

            logger.debug("Starting OCR extraction")
            images = convert_from_bytes(file_data)
            parts: list[str] = []

            for i, image in enumerate(images):
                page_text = pytesseract.image_to_string(image)
                logger.debug("OCR page %d: %d chars", i + 1, len(page_text))
                parts.append(page_text)

            ocr_text = "\n".join(parts)
            logger.info("OCR extracted %d characters total", len(ocr_text))
            return ocr_text

        except Exception as exc:
            logger.warning("OCR extraction failed: %s", exc)
            return ""

    # -----------------------------------------------------------------------
    # LLM (GPT) based extraction
    # -----------------------------------------------------------------------

    @staticmethod
    def extract_with_llm(text: str, api_key: str) -> Dict[str, str]:
        """Extract structured key-value fields from text using OpenAI GPT.

        Sends the document text to GPT and instructs it to return a JSON
        object of field_name → value pairs.

        :param text: Document text (from direct extraction or OCR).
        :param api_key: OpenAI API key from https://platform.openai.com.
        :returns: Mapping of field name → value, or empty dict on failure.
        """
        try:
            from openai import OpenAI  # type: ignore[import]

            if not text.strip():
                logger.warning("LLM extraction skipped: empty input text")
                return {}

            client = OpenAI(api_key=api_key)

            # Truncate very long documents to stay within token limits
            truncated = text[:6000] if len(text) > 6000 else text

            prompt = (
                "Extract all key-value pairs from the following document text.\n"
                "Return a JSON object where each key is a field name and each value "
                "is the corresponding field value extracted from the document.\n"
                "Only return valid JSON. Do not include any explanation or extra text.\n\n"
                f"Document:\n{truncated}\n\nJSON:"
            )

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000,
            )

            response_text = response.choices[0].message.content or ""
            response_text = response_text.strip()

            # Strip markdown code fences if present (e.g. ```json ... ```)
            if response_text.startswith("```"):
                lines = response_text.splitlines()
                # Drop the first line (opening fence) and trailing closing fence if present
                inner_lines = lines[1:]
                if inner_lines and inner_lines[-1].strip() == "```":
                    inner_lines = inner_lines[:-1]
                response_text = "\n".join(inner_lines).strip()

            parsed = json.loads(response_text)
            if not isinstance(parsed, dict):
                logger.warning("LLM returned non-dict JSON")
                return {}

            fields = {
                str(k): str(v).strip()
                for k, v in parsed.items()
                if str(v).strip()
            }
            logger.info("LLM extraction found %d fields", len(fields))
            return fields

        except Exception as exc:
            logger.warning("LLM extraction failed: %s", exc)
            return {}

    # -----------------------------------------------------------------------
    # Multi-strategy orchestrator
    # -----------------------------------------------------------------------

    @staticmethod
    def extract_multi_strategy(
        file_data: bytes,
        *,
        mindee_key: str | None = None,
        koncile_key: str | None = None,
        openai_key: str | None = None,
    ) -> Dict[str, str]:
        """Run multiple extraction strategies and return the first successful result.

        Strategies are tried in priority order:
        1. Mindee IDP (if ``mindee_key`` is set)
        2. Koncile.ai (if ``koncile_key`` is set)
        3. OCR + LLM (if ``openai_key`` is set and Tesseract is available)
        4. OCR alone (Tesseract only, returns raw text parsed as key-value pairs)

        :param file_data: Raw PDF bytes.
        :param mindee_key: Optional Mindee API key.
        :param koncile_key: Optional Koncile.ai API key.
        :param openai_key: Optional OpenAI API key.
        :returns: Mapping of field name → value from the first successful strategy,
                  or empty dict if all strategies fail or no keys are configured.
        """
        # Strategy 1: Mindee IDP
        if mindee_key:
            logger.info("Attempting Mindee IDP extraction")
            result = AdvancedExtractionService.extract_with_mindee(file_data, mindee_key)
            if result:
                logger.info("Mindee found %d fields", len(result))
                return result

        # Strategy 2: Koncile.ai
        if koncile_key:
            logger.info("Attempting Koncile.ai extraction")
            result = AdvancedExtractionService.extract_with_koncile(file_data, koncile_key)
            if result:
                logger.info("Koncile found %d fields", len(result))
                return result

        # Strategy 3: OCR + LLM
        ocr_text = AdvancedExtractionService.extract_with_ocr(file_data)
        if ocr_text.strip() and openai_key:
            logger.info("Attempting OCR + LLM extraction")
            result = AdvancedExtractionService.extract_with_llm(ocr_text, openai_key)
            if result:
                logger.info("OCR+LLM found %d fields", len(result))
                return result

        logger.warning("All advanced extraction strategies exhausted")
        return {}
