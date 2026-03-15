# API Best Practices

## Authentication

- **Always use HTTPS** in production to prevent session cookie interception.
- **Logout** after programmatic sessions to free server resources.
- **Store credentials in environment variables**, not in source code:
  ```python
  import os
  USERNAME = os.environ["PDF_MANAGER_USER"]
  PASSWORD = os.environ["PDF_MANAGER_PASS"]
  ```
- **Rotate secrets** (Flask `SECRET_KEY`, passwords) regularly.

---

## Request Design

### Use the Correct HTTP Method

| Action | Method |
|--------|--------|
| Fetch data | GET |
| Create a resource | POST |
| Update a resource | PUT |
| Delete a resource | DELETE |

### Set the Content-Type Header

Always set `Content-Type: application/json` when sending a JSON body:

```bash
curl -H "Content-Type: application/json" -d '{"value": "new"}' ...
```

### Validate Input Before Sending

Check that:
- Uploaded files have a `.pdf` extension and are ≤ 50 MB
- Field values are non-empty strings before calling PUT
- `document_id` and `field_id` are valid integers

---

## Error Handling

- **Check the HTTP status code** before reading the response body.
- **Do not retry 4xx errors** without fixing the request first.
- **Retry 429** with exponential backoff (see [Rate Limiting](./rate-limiting.md)).
- **Log error responses** in full for debugging.

---

## Pagination

- Fetch only the data you need by using appropriate `per_page` values.
- Always check `pages` before fetching the next page to avoid empty requests.
- For large datasets, process pages sequentially to stay within rate limits.

---

## Performance

- **Cache document metadata** — document IDs and filenames rarely change.
- **Avoid polling** — use the extraction endpoint once and store results.
- **Batch field updates** where possible to minimise round-trips.
- Request **heatmap images** (`?image=true`) only when needed as they add latency.

---

## Extraction Workflow

1. **Upload** the PDF and store the `document_id`.
2. **Extract** using AI extraction (`/extract/ai`) for best results.
3. **Review** fields with confidence < 0.85 for manual correction.
4. **Update** only the fields that need correction.
5. **Export** or integrate the final field values into your system.

---

## Security

- Never log or expose session cookies in application output.
- Use `SESSION_COOKIE_SECURE = True` and `SESSION_COOKIE_HTTPONLY = True` in production.
- Sanitise all user-provided values before displaying them in your application.
- Restrict file upload to trusted users only.

---

## Versioning

The API version is embedded in the path (`/api/v1`). When a new version is released:
- Both versions will be supported for a transition period (at least 6 months).
- Deprecation notices will appear in response headers before removal.
- Check the [Changelog](./changelog.md) for breaking changes.

---

## Testing

- Use a dedicated test database and user account for integration tests.
- Clean up uploaded documents and extracted fields after each test.
- Mock the PDF Manager API in unit tests to avoid external dependencies.
- Use Postman or the cURL examples to manually verify endpoints during development.
