# PDF-Manager

> Upload a PDF, extract its data intelligently, edit any field, and export the result as PDF, JSON, or CSV.

---

## Features

- 📤 **PDF Upload** – drag-and-drop or browse; up to 50 MB
- 🔍 **Intelligent Extraction** – text and table detection via PyMuPDF + OpenCV, ML field classification with PyTorch
- ✏️ **Inline Editing** – review and correct any extracted field in the browser
- ⬇️ **Export** – download updated data as PDF (with overlaid annotations), JSON, or CSV

---

## Quick Start

### Using Docker Compose (recommended)

```bash
git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
cd PDF-Manager
docker compose up --build
```

| Service   | URL                          |
|-----------|------------------------------|
| Frontend  | http://localhost:3000        |
| Backend   | http://localhost:8000        |
| Swagger   | http://localhost:8000/docs   |

### Manual setup

See [docs/SETUP.md](docs/SETUP.md) for step-by-step instructions.

---

## Project Structure

```
PDF-Manager/
├── backend/
│   ├── app.py                  # FastAPI application
│   ├── models.py               # Pydantic models
│   ├── config.py               # Environment-based configuration
│   ├── routes/
│   │   └── pdf_routes.py       # REST endpoints
│   ├── services/
│   │   ├── pdf_service.py      # PDF extraction & export (PyMuPDF + OpenCV)
│   │   └── ml_service.py       # ML field classification (PyTorch)
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

---

## Direct Python Usage

You can use `PDFManagerApp` as a standalone Python library without starting the web server.

### Prerequisites

```bash
# Install backend dependencies (run once)
cd backend
pip install -r requirements.txt
```

### Running the example

```bash
# Must be run from the backend/ directory so Python can find the modules
cd backend
python - <<'EOF'
from pdf_manager_app import PDFManagerApp

app = PDFManagerApp()

# Upload – replace "invoice.pdf" with the path to your own PDF file
with open("invoice.pdf", "rb") as f:
    resp = app.upload("invoice.pdf", f.read())

# Extract
result = app.extract(resp.document_id)
print(result.fields)

# Export to JSON
path = app.export(resp.document_id, fmt="json")
print("Saved to:", path)
EOF
```

> **Tip:** `pdf_manager_app.py` adds the `backend/` directory to Python's module
> search path automatically, so you can also import it from outside `backend/` as
> long as you provide the full path or have installed the package:
>
> ```bash
> # From the repo root
> PYTHONPATH=backend python my_script.py
> ```

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
| Backend | FastAPI (Python 3.11) |
| PDF parsing | PyMuPDF |
| Image processing | OpenCV |
| ML | PyTorch |
| Database | PostgreSQL 15 |
| Containerisation | Docker Compose |

---

## License

MIT
