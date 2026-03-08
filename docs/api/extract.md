# Extraction Endpoints

Run OCR or full AI/RAG extraction on an uploaded document.

---

## OCR Extraction – `POST /api/v1/extract/ocr/{document_id}`

<div class="endpoint-title">
  <span class="http-post">POST</span>
  <code>/api/v1/extract/ocr/{document_id}</code>
</div>

Runs the multi-engine OCR ensemble (PyMuPDF text layer + Tesseract + EasyOCR + PaddleOCR) and returns raw text with per-word confidence scores.

### Example

```bash
curl -b cookies.txt -X POST http://localhost:5000/api/v1/extract/ocr/42
```

### Success Response – `200 OK`

```json
{
  "document_id": "42",
  "total_pages": 1,
  "engines_used": ["pymupdf", "tesseract"],
  "full_text": "Name Rahul Misra\nCity: Asansol ...",
  "pages": [
    {
      "page_number": 1,
      "full_text": "Name Rahul Misra\n...",
      "avg_confidence": 0.94,
      "word_count": 42,
      "engines_used": ["pymupdf"],
      "words": [
        {
          "text": "Rahul",
          "confidence": 0.97,
          "x": 120.5, "y": 85.3,
          "width": 45.2, "height": 14.0,
          "engine": "pymupdf"
        }
      ]
    }
  ]
}
```

---

## AI + RAG Extraction – `POST /api/v1/extract/ai/{document_id}`

<div class="endpoint-title">
  <span class="http-post">POST</span>
  <code>/api/v1/extract/ai/{document_id}</code>
</div>

Runs the full pipeline: OCR → spaCy NER → rule-based field detection → RAG (LangChain + HuggingFace) refinement. Returns structured field/value pairs.

### Query Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `include_images` | `false` | Include base64 heatmap PNG in response |

### Request Body (optional JSON)

```json
{ "run_rag": true }
```

### Examples

=== "cURL"

    ```bash
    curl -b cookies.txt -X POST \
      "http://localhost:5000/api/v1/extract/ai/42?include_images=false" \
      -H "Content-Type: application/json" \
      -d '{"run_rag": true}'
    ```

=== "Python"

    ```python
    response = session.post(
        "http://localhost:5000/api/v1/extract/ai/42",
        params={"include_images": False},
        json={"run_rag": True}
    )
    data = response.json()
    for field in data["fields"]:
        print(field["field_name"], "→", field["value"], f'({field["confidence_pct"]}%)')
    ```

### Success Response – `200 OK`

```json
{
  "document_id": "42",
  "fields": [
    {
      "field_name": "Name",
      "value": "Rahul Misra",
      "field_type": "name",
      "confidence": 0.96,
      "confidence_pct": 96.0,
      "badge": "green",
      "source": "rule",
      "bbox": { "x": 120.5, "y": 85.0, "width": 90.0, "height": 14.0 }
    },
    {
      "field_name": "Cell Phone",
      "value": "7699888010",
      "field_type": "phone",
      "confidence": 0.98,
      "confidence_pct": 98.0,
      "badge": "green",
      "source": "rag"
    }
  ],
  "quality": {
    "score": 94.5,
    "grade": "Excellent",
    "total_words": 85,
    "high_conf_words": 78,
    "medium_conf_words": 5,
    "low_conf_words": 2
  },
  "heatmaps": [
    {
      "page_number": 1,
      "grid_cols": 40,
      "grid_rows": 56,
      "avg_confidence": 0.94
    }
  ],
  "extraction_time_seconds": 1.23
}
```

### Field Source Values

| Source | Description |
|--------|-------------|
| `rule` | Matched by a rule-based regex pattern |
| `ner` | Detected by spaCy Named Entity Recognition |
| `rag` | Refined by the RAG (LangChain) pipeline |

### RAG Extraction Endpoint – `POST /api/v1/extract/rag/{document_id}`

An alternative RAG-only endpoint is available for direct RAG queries:

```bash
curl -b cookies.txt -X POST http://localhost:5000/api/v1/extract/rag/42
```

### Error Responses

| Code | Reason |
|------|--------|
| 404 | Document not found |
| 422 | Document has no extractable text |
| 500 | OCR or extraction failure |
