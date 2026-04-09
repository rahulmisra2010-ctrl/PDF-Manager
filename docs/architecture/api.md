# API Architecture

## Design Principles

- **RESTful** – resources are nouns, HTTP verbs express actions
- **Versioned** – all endpoints under `/api/v1/`
- **JSON** – requests and responses use `application/json` (except file upload/download)
- **Session-based auth** – cookie sessions via Flask-Login

## Blueprint Registration

```python
# app.py
from backend.api.routes import api_bp
app.register_blueprint(api_bp, url_prefix="/api/v1")

from blueprints.rag import rag_bp
app.register_blueprint(rag_bp, url_prefix="/api/v1")
```

## Endpoint Map

```
/api/v1/
├── upload                       POST   – Upload PDF
├── extract/
│   ├── ocr/<document_id>        POST   – OCR extraction
│   ├── ai/<document_id>         POST   – AI + RAG extraction
│   └── rag/<document_id>        POST   – RAG-only extraction
├── fields/
│   ├── <document_id>            GET    – Get all fields
│   ├── <field_id>               PUT    – Update field
│   └── <field_id>/history       GET    – Field history
├── ocr/
│   └── <document_id>/confidence GET    – Character confidence
├── documents/
│   ├── (list)                   GET    – List documents
│   ├── <document_id>            GET    – Document metadata
│   ├── <document_id>            DELETE – Delete document
│   ├── <document_id>/pdf        GET    – Serve PDF
│   └── <document_id>/heatmap   GET    – Confidence heatmap
└── rag/
    └── files                    GET    – List RAG files
```

## Error Handling

All routes return consistent error envelopes:

```python
return jsonify({"error": "Document not found"}), 404
```

See [Error Codes](../api/errors.md) for the full reference.

## Request Validation

Input validation is performed at the route level using standard Flask patterns. File uploads are validated for MIME type (`application/pdf`) and size before being saved.

## Response Pagination

List endpoints support `page` and `per_page` query parameters:

```
GET /api/v1/documents?page=2&per_page=20
```

Response includes pagination metadata:

```json
{
  "documents": [...],
  "total": 150,
  "page": 2,
  "per_page": 20
}
```
