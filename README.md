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

## Project Structure

```
PDF-Manager/
├── app.py                     # Flask application factory (root)
├── pdf_manager_app.py         # Convenience entry point / demo runner
├── backend/
│   ├── app.py                 # Wrapper that loads the root app.py
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
| Database | PostgreSQL 15 |
| Containerisation | Docker Compose |

---

## License

MIT
