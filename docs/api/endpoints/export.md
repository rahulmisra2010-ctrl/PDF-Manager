# Export Endpoints

Base URL: `http://localhost:5000`

> **Note:** A dedicated REST export endpoint (`GET /api/v1/export/{document_id}`) is planned. Current export functionality is available through the web UI and the blueprint routes described below.

---

## Web UI Export

Documents can be exported through the PDF editor interface at:

```
GET /live-pdf/{document_id}/export
```

Supported export formats (via the UI):

| Format | Description |
|--------|-------------|
| JSON | All extracted fields as a JSON object |
| CSV | Fields as comma-separated values |
| PDF | Annotated PDF with overlaid field values |

---

## REST Export (Planned)

### `GET /api/v1/export/{document_id}`

Export a document's extracted fields in the specified format.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `format` | string | `json` | Output format: `json`, `csv` |

#### Success Response — `200 OK` (JSON format)

```json
{
  "document_id": 42,
  "filename": "invoice.pdf",
  "exported_at": "2024-01-15T12:00:00Z",
  "fields": {
    "Name": "John Doe",
    "Date": "2024-01-01",
    "Total": "$1,250.00"
  }
}
```

#### Success Response — `200 OK` (CSV format)

```
Content-Type: text/csv
Content-Disposition: attachment; filename="42_export.csv"

field_name,value,confidence,is_edited
Name,John Doe,0.97,false
Date,2024-01-01,0.95,false
Total,$1250.00,0.89,false
```

---

## Examples

### Export via Python (current approach using fields endpoint)

```python
import json

# Fetch all fields
resp = session.get("http://localhost:5000/api/v1/fields/42")
fields = resp.json()

# Build export dict
export = {f["field_name"]: f["value"] for f in fields}

# Save to JSON
with open("export.json", "w") as fh:
    json.dump(export, fh, indent=2)

print("Exported", len(export), "fields")
```

### Export via JavaScript

```javascript
const resp = await fetch('http://localhost:5000/api/v1/fields/42', {
  credentials: 'include'
});
const fields = await resp.json();

const csv = ['field_name,value,confidence']
  .concat(fields.map(f => `${f.field_name},${f.value},${f.confidence}`))
  .join('\n');

const blob = new Blob([csv], { type: 'text/csv' });
const url = URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url;
a.download = 'fields_export.csv';
a.click();
```
