# Fields Endpoints

Retrieve, update, and query the history of extracted fields.

---

## Get Fields – `GET /api/v1/fields/{document_id}`

<div class="endpoint-title">
  <span class="http-get">GET</span>
  <code>/api/v1/fields/{document_id}</code>
</div>

Retrieve all extracted fields for a document.

### Example

```bash
curl -b cookies.txt http://localhost:5000/api/v1/fields/42
```

### Response – `200 OK`

```json
[
  {
    "id": 10,
    "document_id": 42,
    "field_name": "Name",
    "value": "Rahul Misra",
    "field_type": "name",
    "confidence": 0.96,
    "confidence_pct": 96.0,
    "badge": "green",
    "source": "rule",
    "bbox": { "x": 120.5, "y": 85.0, "width": 90.0, "height": 14.0 },
    "page_number": 1
  }
]
```

---

## Update a Field – `PUT /api/v1/fields/{field_id}`

<div class="endpoint-title">
  <span class="http-put">PUT</span>
  <code>/api/v1/fields/{field_id}</code>
</div>

Edit a single field value. The change is recorded in `field_edit_history`.

### Request Body

```json
{ "value": "Rahul K. Misra" }
```

### Example

```bash
curl -b cookies.txt -X PUT http://localhost:5000/api/v1/fields/10 \
  -H "Content-Type: application/json" \
  -d '{"value": "Rahul K. Misra"}'
```

### Response – `200 OK`

Updated field object (same structure as GET).

---

## Field Edit History – `GET /api/v1/fields/{field_id}/history`

<div class="endpoint-title">
  <span class="http-get">GET</span>
  <code>/api/v1/fields/{field_id}/history</code>
</div>

Get the full edit history for a field.

### Example

```bash
curl -b cookies.txt http://localhost:5000/api/v1/fields/10/history
```

### Response – `200 OK`

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

## OCR Confidence – `GET /api/v1/ocr/{document_id}/confidence`

<div class="endpoint-title">
  <span class="http-get">GET</span>
  <code>/api/v1/ocr/{document_id}/confidence</code>
</div>

Retrieve per-character OCR confidence data for a document.

### Response – `200 OK`

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

## Confidence Heatmap – `GET /api/v1/documents/{document_id}/heatmap`

<div class="endpoint-title">
  <span class="http-get">GET</span>
  <code>/api/v1/documents/{document_id}/heatmap</code>
</div>

### Query Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `page` | `1` | Page number (1-based) |
| `image` | `false` | Include base64 PNG heatmap image |

### Response – `200 OK`

```json
{
  "page_number": 1,
  "grid_cols": 40,
  "grid_rows": 56,
  "avg_confidence": 0.94,
  "cells": [
    { "row": 0, "col": 0, "confidence": 0.97, "color": "green" }
  ],
  "word_markers": [
    { "text": "Rahul", "confidence": 0.97, "color": "green", "x": 120.5, "y": 85.3 }
  ],
  "image": "data:image/png;base64,..."
}
```
