# API Reference – PDF Manager

Base URL: `http://localhost:5000/api/v1`

Interactive docs: Not enabled by default in the Flask build. Use the endpoints
below with a tool like `curl` or Postman.

---

## Health

### `GET /health`
Returns API status.

**Response 200**
```json
{ "status": "healthy", "version": "1.0.0" }
```

---

## PDF Endpoints

### `POST /api/v1/upload`
Upload a PDF file.

**Request** – `multipart/form-data`
| Field | Type | Description |
|-------|------|-------------|
| `file` | File | PDF file (max 50 MB) |

**Response 200**
```json
{
  "document_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "filename": "invoice.pdf",
  "status": "uploaded",
  "message": "PDF uploaded successfully. Use /extract to process the document."
}
```

**Errors**
| Code | Reason |
|------|--------|
| 400  | File is not a PDF |
| 413  | File exceeds size limit |

---

### `POST /api/v1/extract/{document_id}`
Extract text, tables, and structured fields from an uploaded PDF.

**Path params**
| Param | Type | Description |
|-------|------|-------------|
| `document_id` | UUID | ID returned by `/upload` |

**Response 200**
```json
{
  "document_id": "3fa85f64-...",
  "filename": "invoice.pdf",
  "total_pages": 2,
  "fields": [
    {
      "field_name": "date",
      "value": "01/15/2025",
      "confidence": 0.92,
      "page_number": 1,
      "bounding_box": null
    }
  ],
  "extracted_text": "Invoice #INV-1234\nDate: 01/15/2025 ...",
  "tables": [
    [["Item", "Qty", "Price"], ["Widget", "2", "$9.99"]]
  ],
  "extraction_time_seconds": 0.843
}
```

**Errors**
| Code | Reason |
|------|--------|
| 404  | Document not found |

---

### `PUT /api/v1/edit`
Update extracted fields for a document.

**Request body**
```json
{
  "document_id": "3fa85f64-...",
  "fields": [
    {
      "field_name": "amount",
      "value": "19.99",
      "confidence": 0.95,
      "page_number": 1
    }
  ]
}
```

**Response 200**
```json
{
  "document_id": "3fa85f64-...",
  "status": "updated",
  "updated_fields": 1
}
```

---

### `POST /api/v1/export`
Export a document with updated data.

**Request body**
```json
{
  "document_id": "3fa85f64-...",
  "format": "pdf",
  "include_annotations": false
}
```
`format` must be one of `pdf`, `json`, `csv`.

**Response 200**
```json
{
  "document_id": "3fa85f64-...",
  "download_url": "/api/v1/download/3fa85f64-...?format=pdf",
  "format": "pdf",
  "expires_at": "2025-02-02T00:00:00Z"
}
```

---

### `GET /api/v1/download/{document_id}?format=pdf`
Download an exported file.

**Query params**
| Param | Default | Options |
|-------|---------|---------|
| `format` | `pdf` | `pdf`, `json`, `csv` |

**Response** – binary file stream with appropriate `Content-Type`.

---

### `GET /api/v1/documents`
List all documents (paginated).

**Query params**
| Param | Default |
|-------|---------|
| `page` | 1 |
| `page_size` | 20 |

**Response 200**
```json
{
  "documents": [ { "document_id": "...", "filename": "...", ... } ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

---

### `GET /api/v1/documents/{document_id}`
Get details for a specific document.

**Response 200** – raw document dict including extracted fields and text.

---

### `DELETE /api/v1/documents/{document_id}`
Delete a document and remove the file from disk.

**Response 200**
```json
{ "status": "deleted", "document_id": "3fa85f64-..." }
```
