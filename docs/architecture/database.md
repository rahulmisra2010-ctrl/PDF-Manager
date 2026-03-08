# Database Schema

PDF Manager uses SQLAlchemy with SQLite (development) or PostgreSQL (production).

## Entity-Relationship Overview

```mermaid
erDiagram
    documents {
        int id PK
        string filename
        string file_path
        int file_size_bytes
        string status
        float quality_score
        timestamp created_at
    }
    extracted_fields {
        int id PK
        int document_id FK
        string field_name
        string field_value
        float confidence
        float bbox_x
        float bbox_y
        float bbox_width
        float bbox_height
        int page_number
        int version
    }
    field_edit_history {
        int id PK
        int field_id FK
        string old_value
        string new_value
        int edited_by FK
        timestamp edited_at
    }
    ocr_character_data {
        int id PK
        int document_id FK
        int page_number
        string character
        float confidence
        float x
        float y
        float width
        float height
        string ocr_engine
    }
    rag_embeddings {
        int id PK
        int document_id FK
        string field_name
        blob embedding
        text text_content
        timestamp created_at
    }
    users {
        int id PK
        string username
        string password_hash
        string role
        timestamp created_at
    }

    documents ||--o{ extracted_fields : "has"
    documents ||--o{ ocr_character_data : "has"
    documents ||--o{ rag_embeddings : "has"
    extracted_fields ||--o{ field_edit_history : "tracks"
    users ||--o{ field_edit_history : "makes"
```

## Table Descriptions

### `documents`

Stores metadata for each uploaded PDF.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `filename` | TEXT | Original filename |
| `file_path` | TEXT | Absolute path on disk |
| `file_size_bytes` | INTEGER | File size |
| `status` | TEXT | `uploaded`, `extracting`, `extracted`, `error` |
| `quality_score` | REAL | Document quality score (0–100) |
| `created_at` | TIMESTAMP | Upload timestamp |

### `extracted_fields`

Stores key/value pairs extracted from documents.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | |
| `document_id` | INTEGER FK | References `documents.id` |
| `field_name` | TEXT | e.g., `Name`, `City`, `Phone` |
| `field_value` | TEXT | Extracted or edited value |
| `confidence` | REAL | 0.0 – 1.0 |
| `bbox_x/y/width/height` | REAL | Bounding box on page |
| `page_number` | INTEGER | 1-based page number |
| `version` | INTEGER | Increments on edit |

### `field_edit_history`

Audit trail for field edits.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | |
| `field_id` | INTEGER FK | References `extracted_fields.id` |
| `old_value` | TEXT | Value before edit |
| `new_value` | TEXT | Value after edit |
| `edited_by` | INTEGER FK | References `users.id` |
| `edited_at` | TIMESTAMP | Edit timestamp |

### `ocr_character_data`

Per-character OCR results for heatmap generation.

### `rag_embeddings`

Stores HuggingFace sentence embeddings for RAG retrieval.

### `users`

Flask-Login user accounts. Passwords are hashed with bcrypt.
