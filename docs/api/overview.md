# PDF Manager API — Overview

## Base URL

| Environment | URL |
|-------------|-----|
| Development | `http://localhost:5000` |
| Production  | `https://api.pdfmanager.com` *(example — replace with your deployment URL)* |

All REST API endpoints are prefixed with `/api/v1`.

```
http://localhost:5000/api/v1
```

## API Version

The current API version is **v1**. The version is embedded in every endpoint path.

## Authentication

PDF Manager uses **session-based authentication** (cookie) for browser clients. Programmatic API access relies on the same session cookie obtained after logging in at `POST /auth/login`.

See [Authentication](./authentication.md) for full details.

## Response Format

Every API response is a JSON object.

### Success

```json
{
  "document_id": 42,
  "filename": "invoice.pdf",
  "status": "uploaded",
  "message": "PDF uploaded successfully."
}
```

List endpoints wrap results in a named key:

```json
{
  "documents": [ ... ],
  "total": 100,
  "page": 1,
  "per_page": 20,
  "pages": 5
}
```

### Error

```json
{
  "error": "Document not found"
}
```

See [Errors](./errors.md) for the full list of error codes and HTTP status codes.

## Pagination

List endpoints support cursor-free, page-number pagination via query parameters.

| Parameter | Default | Max | Description |
|-----------|---------|-----|-------------|
| `page` | `1` | — | 1-based page number |
| `per_page` | `20` | `100` | Items per page |

See [Pagination](./pagination.md) for detailed information.

## Rate Limiting

Rate limiting protects the API from abuse. Default limits apply per authenticated user.

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Requests allowed in the window |
| `X-RateLimit-Remaining` | Requests remaining |
| `X-RateLimit-Reset` | Unix timestamp when the window resets |

See [Rate Limiting](./rate-limiting.md) for detailed information.

## Content Types

| Scenario | `Content-Type` |
|----------|----------------|
| File upload | `multipart/form-data` |
| JSON body | `application/json` |
| PDF download | `application/pdf` |
| All API responses | `application/json` |

## Changelog

See [Changelog](./changelog.md) for a history of API changes.

## Quick Links

- [Authentication](./authentication.md)
- [Endpoints Reference](./endpoints.md)
- [Error Handling](./errors.md)
- [Pagination](./pagination.md)
- [Rate Limiting](./rate-limiting.md)
- [Webhooks](./webhooks.md)
- [Code Examples](./examples/curl.md)
- [Python SDK](./sdks/python.md)
- [JavaScript SDK](./sdks/javascript.md)
- [Glossary](./glossary.md)
- [Best Practices](./best-practices.md)
