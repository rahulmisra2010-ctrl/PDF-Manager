# Upload Endpoint

Upload a PDF file and create a document record.

---

## `POST /api/v1/upload`

<div class="endpoint-title">
  <span class="http-post">POST</span>
  <code>/api/v1/upload</code>
</div>

### Request

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | ✅ | PDF file (max 50 MB) |

### Examples

=== "cURL"

    ```bash
    curl -b cookies.txt -X POST http://localhost:5000/api/v1/upload \
      -F "file=@/path/to/document.pdf"
    ```

=== "Python"

    ```python
    import requests

    session = requests.Session()
    # ... authenticate first ...

    with open("document.pdf", "rb") as f:
        response = session.post(
            "http://localhost:5000/api/v1/upload",
            files={"file": f}
        )
    print(response.json())
    ```

=== "JavaScript"

    ```javascript
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    const response = await fetch('/api/v1/upload', {
      method: 'POST',
      body: formData,
      credentials: 'include'
    });
    const data = await response.json();
    console.log(data.document_id);
    ```

### Success Response – `201 Created`

```json
{
  "document_id": 42,
  "filename": "document.pdf",
  "status": "uploaded",
  "message": "PDF uploaded successfully",
  "file_size_bytes": 102400
}
```

### Error Responses

| Code | Reason |
|------|--------|
| 400 | No file, wrong type, or exceeds size limit |
| 401 | Not authenticated |
| 413 | File too large |
| 500 | Storage error |

### Rate Limiting

No rate limit applied by default. Configure a reverse proxy (nginx) to add rate limiting in production.
