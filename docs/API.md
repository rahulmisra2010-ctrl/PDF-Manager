# PDF Manager — API Reference

> Base URL: `http://localhost:5000/api/v1`

---

## Upload

### `POST /api/v1/upload`

Upload a PDF file for processing.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | ✅ | PDF file (max 50 MB) |

**Response `201`:**
```json
{
  "document_id": 42,
  "filename": "RAG1.pdf",
  "status": "uploaded",
  "message": "PDF uploaded successfully...",
  "file_size_bytes": 12345
}
```

---

## OCR Extraction

### `POST /api/v1/extract/ocr/{document_id}`

Run multi-engine OCR (Tesseract + EasyOCR + PaddleOCR) on the document.

**Response `200`:**
```json
{
  "document_id": "42",
  "total_pages": 1,
  "engines_used": ["pymupdf", "tesseract"],
  "pages": [
    {
      "page_number": 1,
      "full_text": "Name Rahul Misra\nCity: Asansol ...",
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
  ],
  "full_text": "Name Rahul Misra\n..."
}
```

---

## AI Extraction (RAG)

### `POST /api/v1/extract/ai/{document_id}`

Run full AI pipeline: OCR → Field Detection (NER + rules) → RAG refinement.

**Query Params:**

| Param | Default | Description |
|-------|---------|-------------|
| `include_images` | `false` | Include base64 heatmap PNG in response |

**Request body (optional JSON):**
```json
{ "run_rag": true }
```

**Response `200`:**
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
      "bbox": { "x": 120.5, "y": 85.0, "width": 90.0, "height": 14.0 },
      "char_confidences": [0.97, 0.97, 0.95, ...]
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
    "header_score": 95.0,
    "body_score": 94.0,
    "footer_score": 90.0,
    "total_words": 85,
    "high_conf_words": 78,
    "medium_conf_words": 5,
    "low_conf_words": 2,
    "page_scores": [94.5]
  },
  "heatmaps": [
    {
      "page_number": 1,
      "grid_cols": 40,
      "grid_rows": 56,
      "avg_confidence": 0.94,
      "word_markers": [...]
    }
  ],
  "engines_available": ["pymupdf", "tesseract"],
  "extraction_time_seconds": 1.23
}
```

---

## Fields

### `GET /api/v1/fields/{document_id}`

Retrieve all extracted fields for a document.

**Response `200`:** Array of field objects (same structure as above).

---

### `PUT /api/v1/fields/{field_id}`

Edit a single field value. Records history.

**Request body:**
```json
{ "value": "New Value" }
```

**Response `200`:** Updated field object.

---

### `GET /api/v1/fields/{field_id}/history`

Get the edit history for a field.

**Response `200`:**
```json
[
  {
    "id": 1,
    "field_id": 10,
    "old_value": "Rahul Misra",
    "new_value": "Rahul K. Misra",
    "edited_by": 1,
    "edited_at": "2026-03-07T16:33:06"
  }
]
```

---

## OCR Confidence

### `GET /api/v1/ocr/{document_id}/confidence`

Get stored per-character OCR confidence data.

**Response `200`:**
```json
{
  "document_id": "42",
  "total_characters": 350,
  "avg_confidence": 0.94,
  "characters": [
    {
      "id": 1,
      "character": "R",
      "confidence": 0.97,
      "x": 120.5, "y": 85.3,
      "width": 7.2, "height": 14.0,
      "ocr_engine": "tesseract",
      "page_number": 1
    }
  ]
}
```

---

## Heatmap

### `GET /api/v1/documents/{document_id}/heatmap`

Generate a confidence heatmap for a specific page.

**Query Params:**

| Param | Default | Description |
|-------|---------|-------------|
| `page` | `1` | Page number (1-based) |
| `image` | `false` | Include base64 PNG heatmap image |

**Response `200`:**
```json
{
  "page_number": 1,
  "grid_cols": 40,
  "grid_rows": 56,
  "page_width": 595.0,
  "page_height": 842.0,
  "avg_confidence": 0.94,
  "cells": [
    { "row": 0, "col": 0, "confidence": 0.97, "color": "green" }
  ],
  "word_markers": [
    { "text": "Rahul", "confidence": 0.97, "color": "green", "x": 120.5, ... }
  ],
  "image": "data:image/png;base64,..."
}
```

---

## PDF Serving

### `GET /api/v1/documents/{document_id}/pdf`

Serve the original PDF file for embedding in the browser viewer.

**Response:** `application/pdf` binary stream.

---

## Documents

### `GET /api/v1/documents`

List all documents.

**Query Params:** `page` (default 1), `per_page` (default 20, max 100).

---

### `GET /api/v1/documents/{document_id}`

Get document metadata.

---

### `DELETE /api/v1/documents/{document_id}`

Delete a document and its associated file.

---

## Database Schema

| Table | Columns |
|-------|---------|
| `extracted_fields` | id, document_id, field_name, field_value, confidence, bbox_x, bbox_y, bbox_width, bbox_height, page_number, version |
| `field_edit_history` | id, field_id, old_value, new_value, edited_by, edited_at |
| `ocr_character_data` | id, document_id, page_number, character, confidence, x, y, width, height, ocr_engine |
| `rag_embeddings` | id, document_id, field_name, embedding, text_content, created_at |

---

## Example: Address Book Extraction

**Input text** (`RAG1.txt`):
```
Address Book A-B-C
Name Rahul Misra
Street Address Sumoth pally. Durgamandir
City: Asansol State: WB Zip Code: 713301
Home Phone: Cell Phone: 7699888010
Work Phone: Email:
```

**Output** (from `POST /api/v1/extract/ai/{id}`):
```json
[
  { "field_name": "Name",           "value": "Rahul Misra",             "confidence": 0.96, "badge": "green" },
  { "field_name": "Street Address", "value": "Sumoth pally. Durgamandir","confidence": 0.92, "badge": "green" },
  { "field_name": "City",           "value": "Asansol",                 "confidence": 0.95, "badge": "green" },
  { "field_name": "State",          "value": "WB",                      "confidence": 0.98, "badge": "green" },
  { "field_name": "Zip Code",       "value": "713301",                  "confidence": 0.99, "badge": "green" },
  { "field_name": "Cell Phone",     "value": "7699888010",              "confidence": 0.99, "badge": "green" }
]
```
