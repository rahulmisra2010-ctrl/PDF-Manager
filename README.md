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

## OCR Fallback for Image-Based PDFs

Some PDFs contain scanned pages where text-based extraction (pdfplumber / PyMuPDF)
yields no words.  The **OCR fallback** automatically detects this condition for the
**Street Address** field and re-extracts it using [EasyOCR](https://github.com/JaidedAI/EasyOCR).

### How it works

1. After the primary extraction run completes, the `/pdf/<id>/extract` route
   inspects the **Street Address** value.
2. If the value is empty, `backend/services/ocr_utils.fill_missing_fields_with_ocr`
   is called.
3. PyMuPDF renders the first page at 300 DPI and EasyOCR reads the resulting image.
4. `extract_street_address_from_ocr` locates the line that follows the
   "Street Address" label in the OCR output and returns it as the field value.

### First-run model download

EasyOCR downloads its recognition models (~150 MB) the **first time** it runs.
The models are cached in `~/.EasyOCR/model/` and are not re-downloaded on
subsequent runs.

### CPU-only mode

The EasyOCR reader is initialised with `gpu=False` by default, making it
compatible with machines that do not have a CUDA-capable GPU.

### Enabling / disabling OCR fallback

| Environment variable     | Default | Effect |
|--------------------------|---------|--------|
| `OCR_FALLBACK_ENABLED`   | `1`     | Set to `0` / `false` to disable OCR entirely |
| `OCR_FALLBACK_DPI`       | `300`   | Render resolution; increase for better accuracy on small text |
| `OCR_FALLBACK_PAGE`      | `0`     | Zero-based page index to OCR (not used by the route directly; pass via code) |

Add these to your `.env` file or export them as shell variables before starting
the app.

---

## Troubleshooting OCR / EasyOCR

### CMD vs Python — "command not recognized" errors

When you are in **Windows CMD** your prompt looks like:

```
(.venv) C:\Users\RAHUL MISRA\PDF-Manager>
```

In CMD you run **script files**, not individual Python statements:

```bat
python easyocr_on_image.py     ← correct: run a .py file
```

If your prompt shows `>>>` you are inside the **Python REPL**; Python
statements can be typed there directly.  Type `exit()` to return to CMD
before running `python script.py`.

### My file is named `.png` but OCR says it is a PDF

A file extension does not determine the actual file type.  A PDF document
can be saved with a `.png` extension and it will still be a PDF internally.

**Check the file signature in PowerShell:**

```powershell
# Shows the first 4 bytes as decimal numbers
(Get-Content -Path "test.png" -Encoding Byte -TotalCount 4) -join " "
```

| Result | Meaning |
|--------|---------|
| `137 80 78 71` | Real PNG file (hex `89 50 4E 47`) ✔ |
| `37 80 68 70` or starts with `%PDF` | PDF renamed to `.png` — use a real screenshot |

**Create a genuine PNG screenshot on Windows:**

1. Press **Win + Shift + S** to open the Snipping Tool.
2. Select the area you want to capture.
3. Click the notification → **Save as** → choose a folder and save as `.png`.
4. Use the saved file path in your script or upload it to PDF Manager.

### `ocr_image_text` vs `ocr_page_text`

| Function | Input | Use when |
|----------|-------|----------|
| `ocr_page_text(pdf_path)` | PDF file | You have a PDF document |
| `ocr_image_text(image_path)` | PNG / JPG | You have a real screenshot or photo |

`ocr_image_text` validates the file signature and raises a clear error if the
file is actually a PDF.  It uses **OpenCV** (`cv2.imread`) to load the image,
which is more reliable than `skimage.io.imread` and avoids missing-backend
errors.

### OpenCV returns `None` (image cannot be opened)

If you see a message like *"OpenCV could not open …"*, check:

- The full file path is correct (copy-paste from File Explorer to avoid typos).
- The file extension matches the actual format (`.png`, `.jpg`, `.bmp`, etc.).
- Run the PowerShell signature check above to confirm it is a real image.

---

## License

MIT
