# System Architecture Overview

## High-Level Diagram

```mermaid
graph TD
    User["👤 User (Browser)"]
    React["React SPA\n(PDFViewer, FieldsEditor,\nHeatmap, Dashboard)"]
    Flask["Flask Backend\n(Python 3.11)"]
    OCR["OCR Layer\n(Multi-engine ensemble)"]
    Extract["Extraction Layer\n(NER + Rules + RAG)"]
    DB[(SQLite / PostgreSQL)]
    FS[("File System\nuploads/ exports/")]

    User --> React
    React -->|"REST /api/v1"| Flask
    Flask --> OCR
    Flask --> Extract
    Flask --> DB
    Flask --> FS
    OCR --> Extract
```

## System Components

| Component | Technology | Role |
|-----------|-----------|------|
| **Browser** | React 18 | Upload, view, edit, export |
| **Flask Backend** | Python 3.11, Flask 3.0 | API server, auth, business logic |
| **OCR Layer** | Tesseract, EasyOCR, PaddleOCR | Text extraction from images |
| **Extraction Layer** | spaCy, LangChain, HuggingFace | Field detection and refinement |
| **ORM** | SQLAlchemy | Database abstraction |
| **Database** | SQLite / PostgreSQL | Persistent storage |
| **File System** | Local disk / cloud volume | PDF file storage |

## Data Flow

```mermaid
sequenceDiagram
    participant U as User
    participant R as React
    participant F as Flask API
    participant O as OCR Layer
    participant E as Extraction Layer
    participant D as Database

    U->>R: Select PDF
    R->>F: POST /api/v1/upload
    F->>D: INSERT document record
    F-->>R: {document_id: 42}

    U->>R: Click "Extract Fields"
    R->>F: POST /api/v1/extract/ai/42
    F->>O: Run OCR engines
    O-->>F: WordResult[] + confidence
    F->>E: Detect fields (NER + rules)
    E->>E: RAG refinement
    E-->>F: ExtractedField[]
    F->>D: INSERT extracted_fields
    F-->>R: fields[], quality, heatmaps

    U->>R: Edit a field
    R->>F: PUT /api/v1/fields/10
    F->>D: UPDATE field + INSERT history
    F-->>R: Updated field
```

## Authentication Flow

```mermaid
sequenceDiagram
    participant B as Browser
    participant F as Flask

    B->>F: GET /auth/login
    F-->>B: Login form (CSRF token)
    B->>F: POST /auth/login (username, password, csrf_token)
    F->>F: Verify password (bcrypt)
    F-->>B: Set session cookie + redirect to /
    B->>F: GET /api/v1/documents (+ session cookie)
    F->>F: flask_login.current_user check
    F-->>B: 200 OK + documents JSON
```

## Deployment Architecture (Production)

```mermaid
graph LR
    Internet -->|HTTPS 443| nginx
    nginx -->|HTTP| React["React (port 3000)"]
    nginx -->|HTTP /api/*\n/auth/*| Flask["Flask + Gunicorn\n(port 5000)"]
    Flask --> DB[(PostgreSQL)]
    Flask --> Vol[("Persistent Volume\nuploads/ exports/")]
```

In a cloud deployment, PostgreSQL is replaced by a managed database service and the persistent volume by object storage (S3, GCS, Azure Blob).
