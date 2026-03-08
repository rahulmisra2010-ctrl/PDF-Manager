# Pagination

All list endpoints in the PDF Manager API use **page-number pagination**.

## Query Parameters

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `page` | integer | `1` | — | 1-based page number |
| `per_page` | integer | `20` | `100` | Number of items per page |

## Response Envelope

Paginated responses wrap the items in a named key and include metadata:

```json
{
  "documents": [ ... ],
  "total": 250,
  "page": 2,
  "per_page": 20,
  "pages": 13
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total` | integer | Total number of items across all pages |
| `page` | integer | Current page number |
| `per_page` | integer | Items per page (as requested) |
| `pages` | integer | Total number of pages |

## Examples

### Fetch the first page

```
GET /api/v1/documents
```

### Fetch the third page with 50 items

```
GET /api/v1/documents?page=3&per_page=50
```

### Python — iterate all pages

```python
import requests

session = requests.Session()
# ... login ...

page = 1
all_docs = []
while True:
    resp = session.get(
        "http://localhost:5000/api/v1/documents",
        params={"page": page, "per_page": 100}
    )
    data = resp.json()
    all_docs.extend(data["documents"])
    if page >= data["pages"]:
        break
    page += 1

print(f"Fetched {len(all_docs)} documents")
```

### JavaScript — iterate all pages

```javascript
async function fetchAllDocuments() {
  const allDocs = [];
  let page = 1;

  while (true) {
    const resp = await fetch(
      `http://localhost:5000/api/v1/documents?page=${page}&per_page=100`,
      { credentials: 'include' }
    );
    const data = await resp.json();
    allDocs.push(...data.documents);
    if (page >= data.pages) break;
    page++;
  }

  return allDocs;
}
```

## Notes

- If `page` exceeds the total number of pages, an empty list is returned.
- `per_page` is capped at `100` regardless of the requested value.
- Items are ordered by `created_at` descending (newest first) unless otherwise noted.
