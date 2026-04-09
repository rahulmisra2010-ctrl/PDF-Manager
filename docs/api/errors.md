# Error Codes

This page lists all HTTP error codes returned by the PDF Manager API and their meanings.

## HTTP Status Codes

| Code | Name | Description |
|------|------|-------------|
| `200` | OK | Request succeeded |
| `201` | Created | Resource created successfully (upload) |
| `400` | Bad Request | Invalid input (missing field, wrong file type, etc.) |
| `401` | Unauthorized | Not authenticated; log in first |
| `403` | Forbidden | Authenticated but not authorised for this action |
| `404` | Not Found | Document or field does not exist |
| `413` | Payload Too Large | Uploaded file exceeds `MAX_UPLOAD_SIZE_MB` |
| `422` | Unprocessable Entity | Input is valid but cannot be processed (e.g., no extractable text) |
| `429` | Too Many Requests | Rate limit exceeded (if configured) |
| `500` | Internal Server Error | Unexpected server error |

## Error Response Format

All error responses return JSON:

```json
{
  "error": "Human-readable description of what went wrong",
  "code": 400
}
```

## Common Error Scenarios

### 400 – No file uploaded

```json
{ "error": "No file provided in the request", "code": 400 }
```

**Fix:** Include a `file` field in the `multipart/form-data` request.

---

### 400 – Wrong file type

```json
{ "error": "Only PDF files are accepted", "code": 400 }
```

**Fix:** Ensure the uploaded file has the `.pdf` extension and `application/pdf` MIME type.

---

### 401 – Not authenticated

```json
{ "error": "Authentication required", "code": 401 }
```

**Fix:** Log in at `/auth/login` and include the session cookie in subsequent requests.

---

### 404 – Document not found

```json
{ "error": "Document 99 not found", "code": 404 }
```

**Fix:** Check the `document_id`; the document may have been deleted.

---

### 413 – File too large

```json
{ "error": "File exceeds maximum upload size of 50 MB", "code": 413 }
```

**Fix:** Reduce the file size or increase `MAX_UPLOAD_SIZE_MB` in `.env`.

---

### 422 – No extractable text

```json
{ "error": "Document has no extractable text on page 1", "code": 422 }
```

**Fix:** The PDF may be image-only. Ensure at least one OCR engine (Tesseract) is installed.

---

### 500 – OCR failure

```json
{ "error": "OCR extraction failed: tesseract not found", "code": 500 }
```

**Fix:** Install Tesseract and ensure it is on the system `PATH`. See [Requirements](../installation/requirements.md).

## Debugging Tips

1. Check the Flask server log for the full traceback.
2. Set `DEBUG=true` in `.env` to enable detailed error pages.
3. Use `curl -v` to see full request/response headers.
4. See [Troubleshooting](../troubleshooting/common-issues.md) for more help.
