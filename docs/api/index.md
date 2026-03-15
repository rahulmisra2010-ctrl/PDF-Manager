# API Reference

PDF Manager exposes a RESTful JSON API at `/api/v1`.

**Base URL:** `http://localhost:5000/api/v1`

## Endpoints at a Glance

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Upload a PDF |
| `POST` | `/extract/ocr/{id}` | Run OCR extraction |
| `POST` | `/extract/ai/{id}` | Run AI + RAG extraction |
| `GET` | `/fields/{document_id}` | Get extracted fields |
| `PUT` | `/fields/{field_id}` | Update a field |
| `GET` | `/fields/{field_id}/history` | Field edit history |
| `GET` | `/ocr/{document_id}/confidence` | Per-character OCR confidence |
| `GET` | `/documents/{id}/heatmap` | Confidence heatmap |
| `GET` | `/documents/{id}/pdf` | Serve original PDF |
| `GET` | `/documents/{id}` | Document metadata |
| `GET` | `/documents` | List all documents |
| `DELETE` | `/documents/{id}` | Delete a document |

## Common Headers

```http
Content-Type: application/json
Accept: application/json
```

For file upload, use `multipart/form-data` (see [Upload](upload.md)).

## Authentication

All API endpoints require an authenticated session. See [Authentication](authentication.md).

## Response Format

All JSON responses follow this envelope:

```json
{
  "data": { ... },
  "error": null
}
```

Errors follow:

```json
{
  "error": "Description of what went wrong",
  "code": 400
}
```

See [Error Codes](errors.md) for the full list.
