# Project Structure

```
PDF-Manager/
│
├── app.py                      # Flask application factory (root entry point)
├── pdf_manager_app.py          # CLI entry point (demo / sample sub-commands)
├── models.py                   # SQLAlchemy models (root level)
├── requirements.txt            # Root requirements (delegates to backend/)
├── docker-compose.yml          # Docker Compose service definitions
├── .env.example                # Environment variable template
│
├── backend/
│   ├── __init__.py
│   ├── config.py               # Environment-based configuration
│   ├── database.py             # SQLAlchemy engine and session setup
│   ├── models.py               # SQLAlchemy models (backend copy)
│   ├── requirements.txt        # Python dependencies
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py           # REST API v1 blueprint (/api/v1/*)
│   │
│   ├── ocr/
│   │   ├── __init__.py
│   │   ├── ocr_engine.py       # Multi-engine OCR orchestrator
│   │   ├── confidence_calculator.py  # Per-word/document confidence scoring
│   │   └── heatmap_generator.py      # Confidence heatmap generation
│   │
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── extractor.py        # Main extraction orchestrator
│   │   ├── field_detector.py   # spaCy NER + rule-based field detection
│   │   └── rag_system.py       # LangChain + HuggingFace RAG pipeline
│   │
│   ├── services/
│   │   ├── pdf_service.py      # PDF parsing (PyMuPDF + OpenCV)
│   │   ├── ai_extraction_service.py  # Full AI pipeline service
│   │   ├── rag_service.py      # RAG service (sentence-transformers)
│   │   └── ml_service.py       # ML field classification (optional)
│   │
│   └── cli/
│       └── sample_uploader.py  # CLI helper for batch uploads
│
├── blueprints/
│   ├── auth.py                 # Authentication blueprint (/auth/*)
│   ├── main.py                 # Main UI blueprint
│   └── rag.py                  # RAG API blueprint
│
├── frontend/
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── App.js              # Top-level React component
│   │   ├── components/
│   │   │   ├── PDFViewer.js            # react-pdf based viewer
│   │   │   ├── FieldsEditor.js         # Editable fields table
│   │   │   ├── OCRConfidenceHeatmap.js # Heatmap visualisation
│   │   │   ├── PerformanceDashboard.js # Quality score dashboard
│   │   │   └── ExtractionPage.js       # Split-view extraction page
│   │   ├── services/
│   │   │   └── api.js                  # Fetch wrapper for API calls
│   │   └── styles/
│   │       └── extraction.css
│   └── package.json
│
├── templates/                  # Jinja2 HTML templates (server-rendered UI)
├── static/                     # CSS, JS for server-rendered UI
│
├── database/
│   ├── schema.sql              # PostgreSQL table DDL
│   └── init.sql                # Role creation and seed data
│
└── docs/                       # MkDocs documentation (this site)
```

## Key Entry Points

| File | Purpose |
|------|---------|
| `app.py` | `create_app()` factory — start here |
| `backend/api/routes.py` | All REST API v1 endpoints |
| `blueprints/auth.py` | Login/logout routes |
| `backend/ocr/ocr_engine.py` | OCR engine orchestration |
| `backend/extraction/extractor.py` | AI extraction pipeline |
| `frontend/src/App.js` | React root component |

## Configuration Loading

`app.py` loads `.env` from:

1. Repository root (canonical location)
2. `backend/` (backwards compatibility)

Root values take precedence if a key appears in both files.
