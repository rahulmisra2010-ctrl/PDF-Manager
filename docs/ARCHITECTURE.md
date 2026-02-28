# Architecture – PDF Manager

## System Overview

```
┌──────────────────────────────────────────────────────────┐
│                        Browser                           │
│  React SPA  (Upload · Display · Edit · Export)           │
└──────────────────┬───────────────────────────────────────┘
                   │ HTTP / JSON
                   ▼
┌──────────────────────────────────────────────────────────┐
│                  FastAPI Backend                          │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ pdf_routes  │  │  PDFService  │  │    MLService    │ │
│  │  (REST API) │→ │ (PyMuPDF +   │→ │ (PyTorch +      │ │
│  │             │  │  OpenCV)     │  │  regex heuristic│ │
│  └─────────────┘  └──────────────┘  └─────────────────┘ │
│              │                                           │
│              ▼                                           │
│  ┌───────────────────────┐                               │
│  │   SQLAlchemy / asyncpg│                               │
│  └───────────┬───────────┘                               │
└──────────────┼───────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│               PostgreSQL Database                        │
│  users · documents · extracted_fields                    │
│  detected_tables · exports                               │
└──────────────────────────────────────────────────────────┘
```

## Component Descriptions

### React Frontend (`frontend/`)
- **App.js** – top-level state machine (upload → display → edit)
- **UploadPDF.js** – drag-and-drop file picker, calls `POST /upload`
- **DataDisplay.js** – renders extracted fields and tables, export controls
- **EditData.js** – inline editor for field values, calls `PUT /edit`
- **services/api.js** – thin `fetch` wrapper for all API calls

### FastAPI Backend (`backend/`)
- **app.py** – CORS middleware, router registration, lifespan handler
- **config.py** – environment-based settings via `pydantic-settings`
- **models.py** – Pydantic request/response models (single source of truth)
- **routes/pdf_routes.py** – REST endpoints (upload, extract, edit, export, …)
- **services/pdf_service.py** – PDF text/table extraction and file export
- **services/ml_service.py** – PyTorch `FieldClassifier` + regex patterns

### PostgreSQL Database (`database/`)
- **schema.sql** – table DDL, indexes, triggers
- **init.sql** – role creation, grants, seed data

## Data Flow

```
1. User selects PDF  →  UploadPDF calls POST /upload
2. Backend saves file to disk, returns document_id
3. User clicks "Extract"  →  DataDisplay calls POST /extract/{id}
4. PDFService opens PDF with PyMuPDF, reads text page-by-page
5. OpenCV detects table grid lines on each rendered page image
6. MLService runs regex patterns + FieldClassifier neural net
7. Extracted fields returned to frontend, rendered in DataDisplay
8. User edits a value  →  EditData calls PUT /edit
9. User exports  →  DataDisplay calls POST /export
10. Backend writes PDF/JSON/CSV to exports/  →  user downloads file
```

## Technology Choices

| Layer | Technology | Reason |
|-------|-----------|--------|
| Frontend | React 18 | Component model, wide ecosystem |
| API | FastAPI | Fast, async, auto-docs (OpenAPI) |
| PDF parsing | PyMuPDF | Fast, accurate, pure-Python bindings |
| Image processing | OpenCV | Industry-standard table detection |
| ML | PyTorch | Flexible model definition, GPU support |
| Database | PostgreSQL | ACID, JSONB for flexible table storage |
| ORM | SQLAlchemy async | Type-safe, migrations-friendly |
| Config | pydantic-settings | `.env` → typed Python settings |

## Deployment

For local development, use the provided `docker-compose.yml`.
All services (backend, frontend, postgres) start with:

```bash
docker compose up --build
```

See `docs/SETUP.md` for full instructions.
