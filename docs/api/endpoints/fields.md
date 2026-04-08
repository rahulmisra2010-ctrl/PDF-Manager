# Field Endpoints

Base URL: `http://localhost:5000/api/v1`

All endpoints require an active session cookie.

---

## Get Fields

### `GET /api/v1/fields/{document_id}`

Return all extracted fields for a document.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `document_id` | integer | ✅ | Document ID |

#### Success Response — `200 OK`

Returns a JSON array of field objects:

```json
[
  {
    "id": 1,
    "document_id": 42,
    "field_name": "Name",
    "value": "John Doe",
    "confidence": 0.97,
    "is_edited": false,
    "original_value": null,
    "version": 1,
    "bbox_x": 10.0,
    "bbox_y": 20.0,
    "bbox_width": 100.0,
    "bbox_height": 15.0
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique field ID |
| `document_id` | integer | Parent document ID |
| `field_name` | string | Field label (e.g. `"Name"`, `"Date"`) |
| `value` | string | Current field value |
| `confidence` | float | Extraction confidence score (0–1) |
| `is_edited` | boolean | `true` if value was manually edited |
| `original_value` | string\|null | Value before first edit |
| `version` | integer | Edit version counter (starts at 1) |
| `bbox_x/y/width/height` | float\|null | Bounding box on the PDF page |

#### Error Responses

| Status | Message | Cause |
|--------|---------|-------|
| 404 | `Document not found` | Invalid document_id |
| 500 | — | Internal server error |

---

## Update Field

### `PUT /api/v1/fields/{field_id}`

Edit the value of a single extracted field. The previous value is automatically recorded in the field's edit history.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `field_id` | integer | ✅ | Field ID |

#### Request Body — `application/json`

```json
{
  "value": "Jane Doe"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `value` | string | ✅ | New value for the field |

#### Success Response — `200 OK`

Returns the updated field object (same schema as Get Fields).

```json
{
  "id": 1,
  "document_id": 42,
  "field_name": "Name",
  "value": "Jane Doe",
  "confidence": 0.97,
  "is_edited": true,
  "original_value": "John Doe",
  "version": 2,
  "bbox_x": 10.0,
  "bbox_y": 20.0,
  "bbox_width": 100.0,
  "bbox_height": 15.0
}
```

#### Error Responses

| Status | Message | Cause |
|--------|---------|-------|
| 400 | `Missing 'value' in request body` | Body missing `value` key |
| 404 | `Field not found` | Invalid field_id |
| 500 | — | Internal server error |

---

## Field History

### `GET /api/v1/fields/{field_id}/history`

Return the chronological edit history for a field, ordered by most recent first.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `field_id` | integer | ✅ | Field ID |

#### Success Response — `200 OK`

```json
[
  {
    "id": 2,
    "field_id": 1,
    "old_value": "John Doe",
    "new_value": "Jane Doe",
    "edited_by": 1,
    "edited_at": "2024-01-15T11:00:00"
  },
  {
    "id": 1,
    "field_id": 1,
    "old_value": null,
    "new_value": "John Doe",
    "edited_by": 1,
    "edited_at": "2024-01-15T10:30:00"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | History entry ID |
| `field_id` | integer | Parent field ID |
| `old_value` | string\|null | Value before the edit |
| `new_value` | string | Value after the edit |
| `edited_by` | integer\|null | User ID who made the edit |
| `edited_at` | string | ISO 8601 timestamp |

---

## Examples

### Get Fields — cURL

```bash
curl -b cookies.txt http://localhost:5000/api/v1/fields/42
```

### Update Field — Python

```python
resp = session.put(
    "http://localhost:5000/api/v1/fields/1",
    json={"value": "Jane Doe"}
)
print(resp.json())
```

### Update Field — JavaScript

```javascript
const resp = await fetch('http://localhost:5000/api/v1/fields/1', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({ value: 'Jane Doe' })
});
const field = await resp.json();
console.log(field.value); // "Jane Doe"
```

### Get History — cURL

```bash
curl -b cookies.txt http://localhost:5000/api/v1/fields/1/history
```
