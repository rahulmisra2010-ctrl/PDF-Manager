# Dashboard Endpoints

Base URL: `http://localhost:5000`

---

## Dashboard Page

### `GET /`

Render the main dashboard with statistics cards and charts.

- **Authentication**: Required
- **Response**: HTML page

---

## Dashboard Statistics (JSON)

### `GET /api/stats`

Return aggregate statistics as JSON for Chart.js consumption.

- **Authentication**: Required
- **Response**: `application/json`

#### Success Response — `200 OK`

```json
{
  "total_documents": 150,
  "total_fields": 2400,
  "total_users": 5,
  "recent_uploads": 12,
  "status_breakdown": {
    "uploaded": 10,
    "extracted": 120,
    "edited": 15,
    "approved": 5,
    "rejected": 0
  },
  "recent_activity": [
    {
      "action": "document_uploaded",
      "resource_type": "Document",
      "resource_id": "42",
      "timestamp": "2024-01-15T10:30:00"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total_documents` | integer | Total documents in the system |
| `total_fields` | integer | Total extracted fields |
| `total_users` | integer | Registered users |
| `recent_uploads` | integer | Documents uploaded in the last 7 days |
| `status_breakdown` | object | Count per document status |
| `recent_activity` | array | Latest audit log entries |

---

## Examples

### cURL

```bash
curl -b cookies.txt http://localhost:5000/api/stats
```

### Python

```python
resp = session.get("http://localhost:5000/api/stats")
stats = resp.json()
print(f"Total documents: {stats['total_documents']}")
print(f"Total fields: {stats['total_fields']}")
```

### JavaScript

```javascript
const resp = await fetch('http://localhost:5000/api/stats', {
  credentials: 'include'
});
const stats = await resp.json();
console.log('Documents:', stats.total_documents);
console.log('Fields:', stats.total_fields);
```
