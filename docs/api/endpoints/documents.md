# Document Management Endpoints

Base URL: `http://localhost:5000/api/v1`

All endpoints require an active session cookie.

---

## Upload PDF

### `POST /api/v1/upload`

Upload a PDF file and create a Document record in the database.

#### Request

- **Method**: POST
- **Content-Type**: `multipart/form-data`
- **Rate Limit**: 10 uploads / minute

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

| Status | Message | Cause |
|--------|---------|-------|
| 400 | `No file part in request` | Field `file` missing from form |
| 400 | `Only PDF files are accepted` | Non-PDF file extension |
| 413 | `File too large` | File exceeds 50 MB |
| 500 | — | Internal server error |

---

## List Documents

### `GET /api/v1/documents`

Return a paginated list of all documents, ordered by upload date (newest first).

#### Query Parameters

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `page` | integer | `1` | — | Page number |
| `per_page` | integer | `20` | `100` | Items per page |

#### Success Response — `200 OK`

```json
{
  "documents": [
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
  ],
  "total": 250,
  "page": 1,
  "per_page": 20,
  "pages": 13
}
```

Document statuses: `uploaded`, `extracted`, `edited`, `approved`, `rejected`.

---

## Get Document

### `GET /api/v1/documents/{document_id}`

Return metadata for a single document.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `document_id` | integer | ✅ | Document ID |

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

| Status | Message | Cause |
|--------|---------|-------|
| 404 | `Document not found` | No document with that ID |

---

## Delete Document

### `DELETE /api/v1/documents/{document_id}`

Delete a document from the database and remove its file from disk.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `document_id` | integer | ✅ | Document ID |

#### Success Response — `200 OK`

```json
{
  "status": "deleted",
  "document_id": "42"
}
```

#### Error Responses

| Status | Message | Cause |
|--------|---------|-------|
| 404 | `Document not found` | No document with that ID |

---

## Serve PDF

### `GET /api/v1/documents/{document_id}/pdf`

Serve the original PDF binary for inline viewing or download.

#### Success Response — `200 OK`

- **Content-Type**: `application/pdf`
- Body: raw PDF bytes

#### Error Responses

| Status | Message | Cause |
|--------|---------|-------|
| 404 | `Document not found` | No DB record |
| 404 | `PDF file not found on disk` | File was manually deleted |

---

## Document Heatmap

### `GET /api/v1/documents/{document_id}/heatmap`

Generate an OCR confidence heatmap for a document page.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | `1` | Page number |
| `image` | boolean | `false` | Include base64 PNG image in response |

#### Success Response — `200 OK`

```json
{
  "document_id": "42",
  "page": 1,
  "avg_confidence": 0.92,
  "zones": [],
  "image": null
}
```

---

## Examples

### Upload — cURL

```bash
curl -b cookies.txt \
  -X POST http://localhost:5000/api/v1/upload \
  -F "file=@invoice.pdf"
```

### List Documents — Python

```python
resp = session.get("http://localhost:5000/api/v1/documents", params={"per_page": 50})
for doc in resp.json()["documents"]:
    print(doc["id"], doc["filename"], doc["status"])
```

### Delete Document — JavaScript

```javascript
const resp = await fetch(`http://localhost:5000/api/v1/documents/${id}`, {
  method: 'DELETE',
  credentials: 'include'
});
const result = await resp.json();
console.log(result.status); // "deleted"
```
