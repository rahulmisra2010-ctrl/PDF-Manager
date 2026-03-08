# Rate Limiting

PDF Manager enforces rate limits to protect the API from abuse and ensure fair use.

## Default Limits

| Scope | Limit |
|-------|-------|
| Per authenticated user | 60 requests / minute |
| Upload endpoint | 10 uploads / minute |
| Extraction endpoints | 10 extractions / minute |

## Rate Limit Headers

Every API response includes rate limit headers:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Maximum requests allowed in the current window |
| `X-RateLimit-Remaining` | Requests remaining in the current window |
| `X-RateLimit-Reset` | Unix timestamp when the window resets |

Example response headers:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 42
X-RateLimit-Reset: 1705316400
```

## Rate Limit Exceeded

When the limit is exceeded the server responds with:

- **Status**: `429 Too Many Requests`
- **Body**:

```json
{
  "error": "Rate limit exceeded. Try again after 2024-01-15T10:35:00Z."
}
```

## Handling Rate Limits

### Python

```python
import time
import requests

def call_with_backoff(session, method, url, **kwargs):
    resp = session.request(method, url, **kwargs)
    if resp.status_code == 429:
        reset_ts = int(resp.headers.get("X-RateLimit-Reset", 0))
        wait_secs = max(1, reset_ts - int(time.time()))
        print(f"Rate limited. Sleeping {wait_secs}s …")
        time.sleep(wait_secs)
        resp = session.request(method, url, **kwargs)
    return resp
```

### JavaScript

```javascript
async function callWithBackoff(url, options = {}) {
  const resp = await fetch(url, { credentials: 'include', ...options });
  if (resp.status === 429) {
    const reset = resp.headers.get('X-RateLimit-Reset');
    const waitMs = reset
      ? Math.max(1000, (Number(reset) * 1000) - Date.now())
      : 5000;
    await new Promise(r => setTimeout(r, waitMs));
    return fetch(url, { credentials: 'include', ...options });
  }
  return resp;
}
```

## Best Practices

- Check `X-RateLimit-Remaining` before making burst requests.
- Implement exponential backoff when retrying after a 429 response.
- Batch operations where possible (e.g., upload then extract, rather than many small calls).
- Cache document metadata and field data to reduce redundant reads.
