# PDF-Manager

> **Production-Ready PDF Manager** — Upload a PDF, extract data with triple OCR engines + AI/RAG, edit fields interactively, and export.

---

## Features

- 📤 **PDF Upload** – drag-and-drop or browse; up to 50 MB
- 🔍 **Triple OCR Engine** – Tesseract + EasyOCR + PaddleOCR with ensemble confidence scoring
- 🤖 **AI Field Extraction** – NER (spaCy) + rule-based + RAG (LangChain + HuggingFace embeddings)
- 🔥 **Confidence Heatmaps** – pixel-wise Green/Yellow/Red visualisation per word
- 📊 **Performance Dashboard** – document quality score, regional scores, word confidence breakdown
- 🖊️ **Inline Editing** – split layout: PDF viewer on left, editable fields on right
- ⬇️ **Export** – JSON or CSV with full metadata and confidence scores
- 📜 **Edit History** – all field edits are versioned and audited

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                     Browser (React)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │  PDFViewer   │  │ FieldsEditor │  │ Heatmap / │  │
│  │  (react-pdf) │  │  (inline     │  │ Dashboard │  │
│  │  zoom/scroll │  │   edit)      │  │           │  │
│  └──────────────┘  └──────────────┘  └───────────┘  │
└──────────────────────────┬──────────────────────────┘
                           │ REST /api/v1
┌──────────────────────────▼──────────────────────────┐
│                Flask Backend (Python)                 │
│  ┌─────────────────────────────────────────────────┐ │
│  │               API v1 Blueprint                  │ │
│  │  POST /upload  POST /extract/ocr  POST /extract/ai│ │
│  │  GET  /fields  PUT  /fields/:id   GET /heatmap  │ │
│  └──────────────────┬──────────────────────────────┘ │
│                     │                                 │
│  ┌──────────────────▼──────────────────────────────┐ │
│  │                 OCR Layer                        │ │
│  │  Tesseract ─┐                                   │ │
│  │  EasyOCR   ─┼─ Ensemble Merge → WordResult[]   │ │
│  │  PaddleOCR ─┘                                   │ │
│  └──────────────────┬──────────────────────────────┘ │
│                     │                                 │
│  ┌──────────────────▼──────────────────────────────┐ │
│  │              Extraction Layer                    │ │
│  │  FieldDetector (NER + rules)                    │ │
│  │  RAGSystem (LangChain + sentence-transformers)  │ │
│  │  ConfidenceCalculator → DocumentQuality         │ │
│  │  HeatmapGenerator → JSON + PNG                  │ │
│  └──────────────────┬──────────────────────────────┘ │
│                     │                                 │
│  ┌──────────────────▼──────────────────────────────┐ │
│  │              SQLAlchemy (SQLite / PostgreSQL)    │ │
│  │  documents · extracted_fields · field_edit_history│ │
│  │  ocr_character_data · rag_embeddings · audit_logs│ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## Project Structure

```
PDF-Manager/
├── backend/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── models.py              (Pydantic API models)
│   ├── requirements.txt
│   ├── app.py                 (entry point)
│   ├── ocr/
│   │   ├── __init__.py
│   │   ├── ocr_engine.py      (Tesseract + EasyOCR + PaddleOCR)
│   │   ├── confidence_calculator.py
│   │   └── heatmap_generator.py
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── extractor.py       (orchestrator)
│   │   ├── rag_system.py      (LangChain + HuggingFace)
│   │   └── field_detector.py  (NER + rules)
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py          (REST API v1 blueprint)
│   └── services/
│       ├── pdf_service.py
│       ├── ai_extraction_service.py
│       └── ml_service.py
├── frontend/
│   ├── public/index.html
│   ├── src/
│   │   ├── App.js
│   │   ├── components/
│   │   │   ├── PDFViewer.js           (react-pdf)
│   │   │   ├── FieldsEditor.js        (editable fields table)
│   │   │   ├── OCRConfidenceHeatmap.js
│   │   │   ├── PerformanceDashboard.js
│   │   │   └── ExtractionPage.js      (split layout orchestrator)
│   │   ├── services/api.js
│   │   └── styles/extraction.css
│   └── package.json
├── models.py                  (SQLAlchemy models)
├── blueprints/                (Flask web-UI blueprints)
├── templates/                 (Jinja2 HTML templates)
├── static/                    (CSS, JS for server-rendered UI)
├── database/                  (SQL init scripts)
├── docs/
│   ├── API.md
│   ├── ARCHITECTURE.md
│   └── SETUP.md
├── docker-compose.yml
└── README.md
```

---

## Quick Start

### Using Docker Compose (recommended)

```bash
git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
cd PDF-Manager
docker compose up --build
```

| Service                  | URL                         |
|--------------------------|-----------------------------|
| Frontend (React)         | http://localhost:3000       |
| Backend (Flask + UI/API) | http://localhost:5000       |
| Dashboard login          | http://localhost:5000/auth/login |

### Manual setup

If you prefer not to use Docker:

```bash
git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
cd PDF-Manager

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

cp .env.example .env               # optional; adjust values as needed
python app.py                      # opens http://localhost:5000
```

See [docs/SETUP.md](docs/SETUP.md) for more details.

---

## .env Configuration

### Where to place the file

The `.env` file must be created in the **project root** (the same directory that contains `app.py`):

```
PDF-Manager/          ← repository root
├── .env              ← place it here
├── .env.example      ← template to copy from
├── app.py
└── ...
```

> `app.py` also checks for a `backend/.env` file for backwards compatibility, but the
> **project root** is the canonical location.

---

### Creating the file

Copy the bundled template and edit it with your values:

```bash
cp .env.example .env
```

Then open `.env` in your editor and set at least the two critical keys described below.

---

### Critical values

#### `SECRET_KEY`

Used by Flask to sign session cookies and CSRF tokens. Every restart with a new
key invalidates all active sessions.

Generate a strong value:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Then set it in `.env`:

```dotenv
SECRET_KEY=<paste-the-generated-value-here>
```

> ⚠️ **Duplicate-key warning** — Your `.env` file must contain **exactly one**
> `SECRET_KEY` line. If the key appears more than once, `python-dotenv` uses the
> first occurrence and silently ignores the rest, which can cause confusing
> behaviour. Search the file before saving:
>
> ```bash
> grep -n "SECRET_KEY" .env   # should print exactly one line
> ```

#### `ADMIN_PASSWORD`

Password for the auto-created `admin` account on first run. Leave it blank to
have the app generate and print a random password at startup, but **always set
an explicit password in production**:

```dotenv
ADMIN_PASSWORD=<your-strong-password>
```

---

### Production vs development settings

| Setting | Development | Production |
|---------|-------------|------------|
| `DEBUG` | `true` | `false` |
| `SECRET_KEY` | Any non-empty string | Cryptographically random value (≥ 32 hex chars) |
| `ADMIN_PASSWORD` | Convenient test value | Strong, unique password |
| `DATABASE_URL` | `sqlite:///instance/pdf_manager.db` | PostgreSQL connection string |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Your real frontend domain(s) |

A minimal **development** `.env`:

```dotenv
DEBUG=true
SECRET_KEY=dev-change-me
ADMIN_PASSWORD=dev-admin-please-change
DATABASE_URL=sqlite:///instance/pdf_manager.db
```

A minimal **production** `.env`:

```dotenv
DEBUG=false
SECRET_KEY=<output-of-secrets.token_hex(32)>
ADMIN_PASSWORD=<strong-unique-password>
DATABASE_URL=postgresql://pdfmanager:<password>@db-host:5432/pdfmanager
ALLOWED_ORIGINS=["https://your-frontend-domain.com"]
```

---

### Support

If you run into any problems locating, creating, or editing your `.env` — for
either production or development — open an issue in this repository and include
the error message you are seeing (but **never paste the actual secret values**).

Let me know if you need any more details about this setup or help correcting your .env for production or development.

---

## Project Structure

```
PDF-Manager/
├── app.py                     # Flask application factory (root)
├── pdf_manager_app.py         # Convenience entry point / demo runner
├── backend/
│   ├── app.py                 # Wrapper that loads the root app.py
│   ├── models.py              # SQLAlchemy models
│   ├── config.py              # Environment-based configuration
│   ├── routes/
│   │   └── pdf_routes.py      # REST endpoints (legacy)
│   ├── services/
│   │   ├── pdf_service.py     # PDF extraction & export (PyMuPDF + OpenCV)
│   │   └── ml_service.py      # ML field classification (PyTorch)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.js
│   │   ├── components/
│   │   │   ├── UploadPDF.js
│   │   │   ├── DataDisplay.js
│   │   │   └── EditData.js
│   │   └── services/
│   │       └── api.js
│   └── package.json
├── database/
│   ├── schema.sql              # PostgreSQL table definitions
│   └── init.sql                # Role creation & seed data
├── docs/
│   ├── PHASE_1.md              # Week 1-2 development guide
│   ├── ARCHITECTURE.md         # System design
│   ├── API_DOCS.md             # REST API reference
│   └── SETUP.md                # Local development setup
├── docker-compose.yml
├── requirements.txt            # Root-level (delegates to backend/)
└── .gitignore
```

A note on entry points: the root-level `app.py` is the primary Flask application.
`backend/app.py` is a thin compatibility wrapper so the app can also be started
from inside the `backend/` directory, but `python app.py` from the repository
root is the recommended command.

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/PHASE_1.md](docs/PHASE_1.md) | Week 1-2 task checklist and acceptance criteria |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and component diagram |
| [docs/API_DOCS.md](docs/API_DOCS.md) | Full REST API reference |
| [docs/SETUP.md](docs/SETUP.md) | Local development setup guide |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 |
| Backend | Flask (Python 3.11) |
| PDF parsing | PyMuPDF |
| Image processing | OpenCV |
| ML | PyTorch |
| Database | SQLite (default) / PostgreSQL (optional) |
| Containerisation | Docker Compose |

---

## License

MIT
