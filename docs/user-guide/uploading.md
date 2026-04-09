# Uploading PDFs

## Supported Formats

- **PDF** (`.pdf`) – the only supported format
- Maximum file size: **50 MB** (configurable via `MAX_UPLOAD_SIZE_MB`)

## How to Upload

### Via the Web UI

1. Navigate to the **Upload** page
2. Drag and drop a PDF onto the upload area, or click **Browse** to select a file
3. The file is validated (type, size) before upload begins
4. A progress indicator shows the upload status
5. On success, you are redirected to the document view

### Via the API

```bash
curl -X POST http://localhost:5000/api/v1/upload \
  -F "file=@/path/to/document.pdf"
```

**Response:**

```json
{
  "document_id": 42,
  "filename": "document.pdf",
  "status": "uploaded",
  "message": "PDF uploaded successfully",
  "file_size_bytes": 102400
}
```

Use the `document_id` in subsequent extraction and export requests.

## Storage

Uploaded files are saved to the directory configured by `UPLOAD_DIR` (default: `uploads/`). Each file is stored with its original filename (sanitised to avoid path traversal).

## Upload Limits

| Setting | Default | Notes |
|---------|---------|-------|
| `MAX_UPLOAD_SIZE_MB` | 50 | Configurable in `.env` |
| File type | PDF only | Other types are rejected with HTTP 400 |

## Error Responses

| Code | Reason |
|------|--------|
| 400 | No file provided, wrong file type, or file exceeds size limit |
| 413 | File too large |
| 500 | Server-side storage error |

## Next Steps

After a successful upload, proceed to [Extracting Data](extraction.md).
