# API Reference

The PDF Manager REST API is available at `/api/v1`.

## Authentication

The API uses session-based authentication. Log in via the web UI or use the `/api/v1/login` endpoint.

## Endpoints

### Documents

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/documents` | List all documents |
| `GET` | `/api/v1/documents/<id>` | Get a single document |
| `DELETE` | `/api/v1/documents/<id>` | Delete a document |

### Upload & Extraction

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/upload` | Upload a PDF file |
| `POST` | `/api/v1/extract/ocr` | Extract text via Tesseract OCR |
| `POST` | `/api/v1/extract/ai` | Extract fields using AI mapping |
| `POST` | `/api/v1/extract/rag/<id>` | RAG-based extraction for a document |

### Fields

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/fields/<id>` | Get extracted fields for a document |
| `PUT` | `/api/v1/fields/<id>` | Update fields for a document |
| `GET` | `/api/v1/fields/<id>/history` | Get field edit history |

### OCR Confidence

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/ocr-confidence/<id>` | Get per-word OCR confidence scores |
| `GET` | `/api/v1/heatmap/<id>` | Get confidence heatmap data |

### PDF Serving

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/documents/<id>/pdf` | Stream the original PDF |
| `POST` | `/api/v1/documents/<id>/pdf` | Re-upload / replace a PDF |

### RAG

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/rag/files` | List available RAG text files |

## Example: Upload a PDF

```bash
curl -X POST http://localhost:5000/api/v1/upload \
  -F "file=@/path/to/document.pdf"
```

## Example: Run OCR

```bash
curl -X POST http://localhost:5000/api/v1/extract/ocr \
  -H "Content-Type: application/json" \
  -d '{"document_id": 1}'
```
