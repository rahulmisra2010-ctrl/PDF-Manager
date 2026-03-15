# Exporting Results

Once you have reviewed and corrected the extracted fields, export the data in your preferred format.

## Available Formats

| Format | Description |
|--------|-------------|
| **JSON** | Full field data with confidence scores and metadata |
| **CSV** | Flat table of field names and values |

## Exporting via the UI

1. Open the document extraction view
2. Click the **Export** button
3. Select **JSON** or **CSV**
4. The file downloads immediately

## Exporting via the API

### Export document fields as JSON

```bash
curl http://localhost:5000/api/v1/fields/42 \
  -H "Accept: application/json" > fields.json
```

### Export via the export endpoint

```bash
curl -X POST http://localhost:5000/api/v1/export/42 \
  -H "Content-Type: application/json" \
  -d '{"format": "json"}' \
  --output export.json
```

## JSON Export Structure

```json
{
  "document_id": 42,
  "filename": "address-book.pdf",
  "exported_at": "2026-03-07T18:00:00",
  "fields": [
    {
      "field_name": "Name",
      "value": "Rahul Misra",
      "field_type": "name",
      "confidence": 0.96,
      "confidence_pct": 96.0,
      "badge": "green",
      "source": "rule"
    },
    {
      "field_name": "Cell Phone",
      "value": "7699888010",
      "field_type": "phone",
      "confidence": 0.98,
      "confidence_pct": 98.0,
      "badge": "green",
      "source": "rag"
    }
  ]
}
```

## CSV Export Structure

```csv
field_name,value,confidence,badge,source
Name,Rahul Misra,0.96,green,rule
City,Asansol,0.95,green,rule
State,WB,0.98,green,rule
Cell Phone,7699888010,0.98,green,rag
```

## Tips

- Export **after** editing to capture all corrections.
- The JSON format includes full metadata (confidence, source, bbox); prefer it for programmatic processing.
- The CSV format is more convenient for spreadsheet analysis.
