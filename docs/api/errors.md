# Error Handling

## Error Response Format

When a request fails, the API returns a JSON object with an `error` field:

```json
{
  "error": "Human-readable error message"
}
```

## HTTP Status Codes

| Status Code | Name | Description |
|-------------|------|-------------|
| `200` | OK | Request succeeded |
| `201` | Created | Resource created successfully |
| `204` | No Content | Request succeeded with no body |
| `302` | Found | Redirect (used by auth endpoints) |
| `400` | Bad Request | Invalid request parameters or body |
| `401` | Unauthorized | Authentication required |
| `403` | Forbidden | Authenticated but not authorised |
| `404` | Not Found | Resource does not exist |
| `413` | Payload Too Large | File exceeds the 50 MB limit |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Unexpected server-side error |

## Common Error Messages

### 400 Bad Request

| Message | Cause | Fix |
|---------|-------|-----|
| `No file part in request` | `multipart/form-data` upload missing the `file` field | Include the file field |
| `Only PDF files are accepted` | Uploaded file is not a `.pdf` | Ensure the file has a `.pdf` extension |
| `Missing 'value' in request body` | PUT /fields body lacks the `value` key | Include `{"value": "..."}` in the body |

### 401 Unauthorized

The session cookie is missing or has expired. Log in again at `POST /auth/login` and re-send the cookie.

### 403 Forbidden

Your role does not allow this action. Contact an Admin to adjust your permissions.

### 404 Not Found

| Message | Cause |
|---------|-------|
| `Document not found` | The `document_id` does not match any record |
| `Field not found` | The `field_id` does not match any record |
| `PDF file not found on disk` | DB record exists but the file was deleted |

### 413 Payload Too Large

The uploaded file exceeds the 50 MB limit configured in `MAX_CONTENT_LENGTH`.

### 429 Too Many Requests

You have exceeded the rate limit for this endpoint. Wait until the `X-RateLimit-Reset` timestamp before retrying.

### 500 Internal Server Error

An unexpected error occurred. Check the server logs. Common causes:

- OCR engine not installed (Tesseract, EasyOCR, PaddleOCR)
- Database connection failure
- Missing environment variable (e.g. `SECRET_KEY`)

## Troubleshooting Common Errors

### "Document not found" after upload

Ensure you are using the `document_id` value from the upload response, not the filename.

### OCR returns empty results

- Verify the PDF contains selectable text or scanned images.
- Check that Tesseract is installed: `tesseract --version`.
- Try the AI extraction endpoint which uses multiple engines.

### Upload fails with 413

Reduce the file size or increase `MAX_CONTENT_LENGTH` in the Flask configuration.

### Fields not persisted after extraction

The extraction endpoint requires a valid database session. Check that `DATABASE_URL` is configured correctly in `.env`.

## Error Handling Best Practices

1. **Always check the HTTP status code** before reading the response body.
2. **Retry on 429** using exponential backoff: wait `2^n` seconds between retries.
3. **Retry on 503** (service unavailable) up to 3 times.
4. **Do not retry on 4xx** (client errors) — fix the request first.
5. **Log the full error response** body for debugging — the `error` field contains context.
6. **Validate inputs client-side** to avoid sending malformed requests.

### Python Example with Retry

```python
import time
import requests

def api_request(session, method, url, **kwargs):
    for attempt in range(3):
        resp = session.request(method, url, **kwargs)
        if resp.status_code == 429:
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(1, reset - int(time.time()))
            print(f"Rate limited. Retrying in {wait}s...")
            time.sleep(wait)
            continue
        return resp
    raise RuntimeError("Max retries exceeded")
```

### JavaScript Example with Retry

```javascript
async function apiRequest(url, options = {}, retries = 3) {
  for (let i = 0; i < retries; i++) {
    const resp = await fetch(url, { credentials: 'include', ...options });
    if (resp.status === 429) {
      const reset = resp.headers.get('X-RateLimit-Reset');
      const wait = reset ? (Number(reset) - (Date.now() / 1000)) * 1000 : 5000;
      await new Promise(r => setTimeout(r, wait));
      continue;
    }
    return resp;
  }
  throw new Error('Max retries exceeded');
}
```
