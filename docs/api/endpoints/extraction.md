# Extraction Endpoints

Base URL: `http://localhost:5000/api/v1`

All endpoints require an active session cookie.

---

## OCR Extraction

### `POST /api/v1/extract/ocr/{document_id}`

Run multi-engine OCR extraction on the document. Uses a combination of PyMuPDF, Tesseract, EasyOCR, and PaddleOCR engines. Character-level confidence data is stored in the database for heatmap generation.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `document_id` | integer | ✅ | Document ID from upload response |

#### Request

- **Method**: POST
- **Authentication**: Required
- **Rate Limit**: 10 requests / minute

#### Success Response — `200 OK`

```json
{
  "document_id": "42",
  "total_pages": 2,
  "engines_used": ["pymupdf", "tesseract"],
  "pages": [
    {
      "page_number": 1,
      "full_text": "Name: John Doe\nDate: 2024-01-01",
      "avg_confidence": 0.94,
      "word_count": 20,
      "engines_used": ["pymupdf"],
      "words": [
        {
          "text": "John",
          "confidence": 0.99,
          "x": 10.0,
          "y": 20.0,
          "width": 30.0,
          "height": 10.0,
          "engine": "pymupdf"
        }
      ]
    }
  ],
  "full_text": "Name: John Doe\nDate: 2024-01-01"
}
```

#### Error Responses

| Status | Message | Cause |
|--------|---------|-------|
| 404 | `Document not found` | Invalid document_id |
| 500 | `OCR failed: <reason>` | OCR engine error |

---

## AI / RAG Extraction

### `POST /api/v1/extract/ai/{document_id}`

Run the full AI + RAG (Retrieval-Augmented Generation) extraction pipeline. Returns structured fields with confidence scores and optional heatmap data. Replaces any existing extracted fields for the document.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `document_id` | integer | ✅ | Document ID from upload response |

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_images` | boolean | `false` | Include base64 heatmap images in response |

#### Request Body — `application/json`

```json
{
  "run_rag": true
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `run_rag` | boolean | `true` | Enable RAG for improved extraction |

#### Success Response — `200 OK`

```json
{
  "document_id": "42",
  "fields": [
    {
      "field_name": "Name",
      "value": "John Doe",
      "confidence": 0.97,
      "bbox": {
        "x": 10,
        "y": 20,
        "width": 100,
        "height": 15
      }
    },
    {
      "field_name": "Date",
      "value": "2024-01-01",
      "confidence": 0.95,
      "bbox": null
    }
  ],
  "heatmaps": []
}
```

#### Error Responses

| Status | Message | Cause |
|--------|---------|-------|
| 404 | `Document not found` | Invalid document_id |
| 500 | `Extraction failed: <reason>` | AI pipeline error |

---

## OCR Confidence Data

### `GET /api/v1/ocr/{document_id}/confidence`

Return stored per-character OCR confidence data for a document.

#### Success Response — `200 OK`

```json
{
  "document_id": "42",
  "total_characters": 1500,
  "avg_confidence": 0.91,
  "characters": [
    {
      "character": "J",
      "confidence": 0.99,
      "page_number": 1,
      "x": 10.0,
      "y": 20.0,
      "width": 5.0,
      "height": 10.0,
      "ocr_engine": "pymupdf"
    }
  ]
}
```

> Response is capped at 5,000 characters.

---

## Extraction Workflow

The recommended extraction workflow is:

1. **Upload** the PDF via `POST /api/v1/upload` → receive `document_id`
2. **Extract** using `POST /api/v1/extract/ai/{document_id}` (recommended) or OCR-only
3. **Review** the extracted fields via `GET /api/v1/fields/{document_id}`
4. **Edit** incorrect fields via `PUT /api/v1/fields/{field_id}`
5. **Export** the final data via `GET /api/v1/export/{document_id}` (see [export docs](./export.md))

---

## Examples

### OCR Extraction — cURL

```bash
curl -b cookies.txt \
  -X POST http://localhost:5000/api/v1/extract/ocr/42
```

### AI Extraction — Python

```python
resp = session.post(
    "http://localhost:5000/api/v1/extract/ai/42",
    json={"run_rag": True}
)
data = resp.json()
for field in data["fields"]:
    print(f"{field['field_name']}: {field['value']} ({field['confidence']:.0%})")
```

### AI Extraction — JavaScript

```javascript
const resp = await fetch('http://localhost:5000/api/v1/extract/ai/42', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({ run_rag: true })
});
const { fields } = await resp.json();
fields.forEach(f => console.log(f.field_name, f.value));
```
