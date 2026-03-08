# Search Endpoints

Base URL: `http://localhost:5000/search`

The search blueprint provides full-text search over documents and extracted fields.

---

## Search Results Page

### `GET /search/`

Render the search results page in the browser UI.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | ✅ | Search query string |
| `status` | string | ❌ | Filter by document status |
| `field` | string | ❌ | Filter by field name |

---

## JSON Search API

### `GET /search/api`

Return search results as JSON. Searches document filenames and extracted field values.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | ✅ | Search query string |

#### Success Response — `200 OK`

```json
{
  "query": "invoice",
  "documents": [
    {
      "id": 42,
      "filename": "invoice.pdf",
      "status": "extracted",
      "created_at": "2024-01-15T10:30:00"
    }
  ],
  "fields": [
    {
      "id": 1,
      "document_id": 42,
      "field_name": "Type",
      "value": "Invoice",
      "confidence": 0.95
    }
  ],
  "total_documents": 1,
  "total_fields": 1
}
```

---

## Examples

### cURL

```bash
curl -b cookies.txt \
  "http://localhost:5000/search/api?q=invoice"
```

### Python

```python
resp = session.get("http://localhost:5000/search/api", params={"q": "invoice"})
data = resp.json()
print(f"Found {data['total_documents']} documents and {data['total_fields']} fields")
```

### JavaScript

```javascript
const query = encodeURIComponent('invoice');
const resp = await fetch(`http://localhost:5000/search/api?q=${query}`, {
  credentials: 'include'
});
const results = await resp.json();
console.log(results.documents, results.fields);
```
