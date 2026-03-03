import re
from pathlib import Path
import fitz  # PyMuPDF


class PDFService:
    """Extract text and structured fields from PDFs using PyMuPDF + regex."""

    CONFIDENCE_DEGRADATION_RATE = 0.02  # confidence reduction per additional match of same type

    PATTERNS = {
        'date': (r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b', 0.85),
        'email': (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 0.95),
        'phone': (r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', 0.80),
        'amount': (r'\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*(?:USD|EUR|GBP)\b', 0.80),
        'invoice_number': (r'\b(?:INV|Invoice|Inv)[-#\s]?\d+\b', 0.90),
        'po_number': (r'\b(?:PO|P\.O\.|Purchase Order)[-#\s]?\d+\b', 0.85),
        'address': (r'\d+\s+[A-Za-z0-9\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct)\.?(?:\s+(?:Suite|Ste|Apt|Unit)\s+\w+)?', 0.70),
    }

    def extract(self, file_path: str) -> tuple:
        """
        Extract text and fields from a PDF.
        Returns (full_text, fields_list, page_count)
        fields_list: list of dicts with field_name, field_value, confidence, page_number
        """
        doc = fitz.open(file_path)
        page_count = len(doc)
        all_text_parts = []
        all_fields = []
        seen_values = {}  # deduplicate

        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            all_text_parts.append(text)
            fields = self._extract_fields_from_text(text, page_num)
            for f in fields:
                key = (f['field_name'], f['field_value'])
                if key not in seen_values:
                    seen_values[key] = True
                    all_fields.append(f)

        doc.close()
        full_text = '\n'.join(all_text_parts)
        return full_text, all_fields, page_count

    def _extract_fields_from_text(self, text: str, page_num: int) -> list:
        fields = []
        for field_name, (pattern, base_confidence) in self.PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            for i, match in enumerate(matches):
                value = match.strip() if isinstance(match, str) else ' '.join(m.strip() for m in match if m.strip())
                if not value:
                    continue
                # Confidence slightly lower for subsequent matches of same type
                confidence = round(base_confidence - (i * self.CONFIDENCE_DEGRADATION_RATE), 2)
                confidence = max(0.3, min(1.0, confidence))
                label = field_name if i == 0 else f'{field_name}_{i+1}'
                fields.append({
                    'field_name': label,
                    'field_value': value,
                    'confidence': confidence,
                    'page_number': page_num,
                    'bbox': {}
                })
        return fields
