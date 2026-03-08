# Editing Fields

After extraction, you can review and correct any field in the split-view editor.

## Split-View Editor

The extraction view shows:

- **Left panel** – the original PDF rendered in the browser (zoomable/scrollable)
- **Right panel** – extracted fields as an editable table

## Editing a Field

1. Click the pencil icon (✏️) next to any field value
2. The cell becomes an input; type your correction
3. Press **Enter** or click **Save** to confirm
4. The field is updated and the change is recorded in history

Every edit triggers a `PUT /api/v1/fields/<field_id>` request and logs an entry in `field_edit_history`.

## Edit History

To see all changes made to a field:

1. Click the clock icon (🕐) next to the field
2. A history panel expands showing old → new values, user, and timestamp

**Via API:**

```bash
curl http://localhost:5000/api/v1/fields/10/history
```

**Response:**

```json
[
  {
    "id": 1,
    "field_id": 10,
    "old_value": "Rahul Misra",
    "new_value": "Rahul K. Misra",
    "edited_by": 1,
    "edited_at": "2026-03-07T16:33:06"
  }
]
```

## Field Types

| Field Type | Example Value |
|------------|---------------|
| `name` | Rahul Misra |
| `street_address` | 123 Main St |
| `city` | Asansol |
| `state` | WB |
| `zip_code` | 713301 |
| `phone` | 7699888010 |
| `email` | user@example.com |

## Tips

- Fields highlighted in **red** have low confidence and are most likely to need correction.
- Use the PDF viewer on the left to locate the original text for any questionable field.
- All edits are reversible by reviewing history and re-entering the original value.

## Next Steps

- [Exporting Results](exporting.md) – download the corrected data
