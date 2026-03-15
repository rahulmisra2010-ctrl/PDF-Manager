# Export & Document Endpoints

---

## List Documents – `GET /api/v1/documents`

<div class="endpoint-title">
  <span class="http-get">GET</span>
  <code>/api/v1/documents</code>
</div>

List all uploaded documents with pagination.

### Query Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `page` | `1` | Page number |
| `per_page` | `20` | Items per page (max 100) |

### Example

```bash
curl -b cookies.txt "http://localhost:5000/api/v1/documents?page=1&per_page=20"
```

### Response – `200 OK`

```json
{
  "documents": [
    {
      "id": 42,
      "filename": "document.pdf",
      "file_size_bytes": 102400,
      "status": "extracted",
      "quality_score": 94.5,
      "created_at": "2026-03-07T12:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 20
}
```

---

## Get Document – `GET /api/v1/documents/{document_id}`

<div class="endpoint-title">
  <span class="http-get">GET</span>
  <code>/api/v1/documents/{document_id}</code>
</div>

Get metadata for a specific document.

---

## Serve PDF – `GET /api/v1/documents/{document_id}/pdf`

<div class="endpoint-title">
  <span class="http-get">GET</span>
  <code>/api/v1/documents/{document_id}/pdf</code>
</div>

Stream the original PDF file for embedding in the browser viewer.

**Response:** `application/pdf` binary stream.

---

## Delete Document – `DELETE /api/v1/documents/{document_id}`

<div class="endpoint-title">
  <span class="http-delete">DELETE</span>
  <code>/api/v1/documents/{document_id}</code>
</div>

Delete a document and its associated file from disk.

```bash
curl -b cookies.txt -X DELETE http://localhost:5000/api/v1/documents/42
```

### Response – `200 OK`

```json
{ "message": "Document 42 deleted successfully" }
```

---

## Export Fields

The extracted fields can be exported by fetching `GET /api/v1/fields/{document_id}` and serialising the result.

### JSON Export (Python)

```python
import json, requests

session = requests.Session()
# ... authenticate ...

fields = session.get("http://localhost:5000/api/v1/fields/42").json()
with open("export.json", "w") as f:
    json.dump(fields, f, indent=2)
```

### CSV Export (Python)

```python
import csv, requests

fields = session.get("http://localhost:5000/api/v1/fields/42").json()
with open("export.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["field_name", "value", "confidence", "badge"])
    writer.writeheader()
    for field in fields:
        writer.writerow({k: field[k] for k in writer.fieldnames})
```
