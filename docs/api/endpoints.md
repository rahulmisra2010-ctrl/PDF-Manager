# API Endpoints Reference

Base URL: `http://localhost:5000/api/v1`

All endpoints require an active session (see [Authentication](./authentication.md)).

---

## Table of Contents

1. [Upload PDF](#upload-pdf)
2. [OCR Extraction](#ocr-extraction)
3. [AI Extraction](#ai-extraction)
4. [List Documents](#list-documents)
5. [Get Document](#get-document)
6. [Delete Document](#delete-document)
7. [Serve PDF](#serve-pdf)
8. [Get Fields](#get-fields)
9. [Update Field](#update-field)
10. [Field History](#field-history)
11. [OCR Confidence](#ocr-confidence)
12. [Document Heatmap](#document-heatmap)

---

## Upload PDF

### `POST /api/v1/upload`

Upload a PDF file and create a Document record.

#### Request

- **Method**: POST
- **Content-Type**: `multipart/form-data`
- **Authentication**: Required

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | ✅ | PDF file (max 50 MB) |

#### Success Response — `201 Created`

```json
{
  "document_id": 42,
  "filename": "invoice.pdf",
  "status": "uploaded",
  "message": "PDF uploaded successfully. Call /api/v1/extract/ocr or /api/v1/extract/ai to process.",
  "file_size_bytes": 102400
}
```

#### Error Responses

| Status | Reason |
|--------|--------|
| 400 | No file part / file is not a PDF |
| 413 | File exceeds 50 MB limit |
| 500 | Internal server error |

#### Examples

```bash
curl -b cookies.txt \
  -X POST http://localhost:5000/api/v1/upload \
  -F "file=@/path/to/document.pdf"
```

```python
import requests

session = requests.Session()
# ... login ...

with open("document.pdf", "rb") as f:
    resp = session.post(
        "http://localhost:5000/api/v1/upload",
        files={"file": f}
    )
print(resp.json())
```

---

## OCR Extraction

### `POST /api/v1/extract/ocr/{document_id}`

Run multi-engine OCR (Tesseract + EasyOCR + PyMuPDF) on the document.

#### Request

- **Method**: POST
- **Authentication**: Required

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `document_id` | integer | ✅ | ID returned by the upload endpoint |

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
      "engines_used": ["pymupdf"]
    }
  ],
  "full_text": "Name: John Doe\nDate: 2024-01-01"
}
```

#### Error Responses

| Status | Reason |
|--------|--------|
| 404 | Document not found |
| 500 | OCR engine failure |

---

## AI Extraction

### `POST /api/v1/extract/ai/{document_id}`

Run the full AI + RAG extraction pipeline. Returns structured fields with confidence scores.

#### Request

- **Method**: POST
- **Content-Type**: `application/json`
- **Authentication**: Required

| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `document_id` | integer | path | Document ID |
| `run_rag` | boolean | body | Enable RAG (default: `true`) |
| `include_images` | boolean | query | Include heatmap images (default: `false`) |

#### Request Body

```json
{
  "run_rag": true
}
```

#### Success Response — `200 OK`

```json
{
  "document_id": "42",
  "fields": [
    {
      "field_name": "Name",
      "value": "John Doe",
      "confidence": 0.97,
      "bbox": { "x": 10, "y": 20, "width": 100, "height": 15 }
    }
  ],
  "heatmaps": []
}
```

#### Error Responses

| Status | Reason |
|--------|--------|
| 404 | Document not found |
| 500 | Extraction pipeline failure |

---

## List Documents

### `GET /api/v1/documents`

Return a paginated list of all documents.

#### Request

- **Method**: GET
- **Authentication**: Required

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | ❌ | `1` | Page number (1-based) |
| `per_page` | integer | ❌ | `20` | Items per page (max 100) |

#### Success Response — `200 OK`

```json
{
  "documents": [
    {
      "id": 42,
      "filename": "invoice.pdf",
      "status": "extracted",
      "page_count": 2,
      "file_size": 102400,
      "uploaded_by": 1,
      "created_at": "2024-01-15T10:30:00"
    }
  ],
  "total": 100,
  "page": 1,
  "per_page": 20,
  "pages": 5
}
```

---

## Get Document

### `GET /api/v1/documents/{document_id}`

Return metadata for a single document.

#### Success Response — `200 OK`

```json
{
  "id": 42,
  "filename": "invoice.pdf",
  "file_path": "/uploads/uuid.pdf",
  "status": "extracted",
  "page_count": 2,
  "file_size": 102400,
  "uploaded_by": 1,
  "created_at": "2024-01-15T10:30:00"
}
```

#### Error Responses

| Status | Reason |
|--------|--------|
| 404 | Document not found |

---

## Delete Document

### `DELETE /api/v1/documents/{document_id}`

Delete a document record and its associated file from disk.

#### Success Response — `200 OK`

```json
{
  "status": "deleted",
  "document_id": "42"
}
```

#### Error Responses

| Status | Reason |
|--------|--------|
| 404 | Document not found |

---

## Serve PDF

### `GET /api/v1/documents/{document_id}/pdf`

Serve the original PDF binary for viewing or download.

#### Success Response — `200 OK`

- **Content-Type**: `application/pdf`
- Body: raw PDF bytes

---

## Get Fields

### `GET /api/v1/fields/{document_id}`

Return all extracted fields for a document.

#### Success Response — `200 OK`

```json
[
  {
    "id": 1,
    "document_id": 42,
    "field_name": "Name",
    "value": "John Doe",
    "confidence": 0.97,
    "is_edited": false,
    "original_value": null,
    "version": 1,
    "bbox_x": 10,
    "bbox_y": 20,
    "bbox_width": 100,
    "bbox_height": 15
  }
]
```

---

## Update Field

### `PUT /api/v1/fields/{field_id}`

Edit a field value. The previous value is recorded in the edit history.

#### Request Body

```json
{
  "value": "Jane Doe"
}
```

#### Success Response — `200 OK`

Returns the updated field object (same schema as Get Fields).

#### Error Responses

| Status | Reason |
|--------|--------|
| 400 | Missing `value` in request body |
| 404 | Field not found |

---

## Field History

### `GET /api/v1/fields/{field_id}/history`

Return the chronological edit history for a field.

#### Success Response — `200 OK`

```json
[
  {
    "id": 1,
    "field_id": 1,
    "old_value": "John Doe",
    "new_value": "Jane Doe",
    "edited_by": 1,
    "edited_at": "2024-01-15T11:00:00"
  }
]
```

---

## OCR Confidence

### `GET /api/v1/ocr/{document_id}/confidence`

Return per-character OCR confidence data for a document.

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

> Response is capped at 5,000 characters. Use the page-level OCR endpoint for full data.

---

## Document Heatmap

### `GET /api/v1/documents/{document_id}/heatmap`

Generate and return an OCR confidence heatmap for a document page.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | `1` | Page number |
| `image` | boolean | `false` | Include base64-encoded PNG image |

#### Success Response — `200 OK`

```json
{
  "document_id": "42",
  "page": 1,
  "avg_confidence": 0.92,
  "zones": [ ... ],
  "image": "<base64-png>"
}
```
