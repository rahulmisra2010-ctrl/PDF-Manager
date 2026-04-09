# Manual Installation

Use this guide when you prefer to run the backend and frontend directly without Docker.

## Prerequisites

Ensure you have the packages listed in [Requirements](requirements.md) installed:

- Python 3.11+
- Node.js 18+ and npm 9+
- Tesseract OCR 4.1+

### Install Tesseract (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng
```

### Install Tesseract (macOS)

```bash
brew install tesseract
```

---

## Step 1 – Clone the Repository

```bash
git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
cd PDF-Manager
```

---

## Step 2 – Backend Setup

```bash
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

# Install Python dependencies
pip install -r backend/requirements.txt
```

---

## Step 3 – Environment Configuration

```bash
cp .env.example .env
```

Open `.env` and set at least:

```dotenv
# Flask session signing key – generate a strong random value:
# python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<your-generated-key>

# Password for the auto-created admin account
ADMIN_PASSWORD=<strong-password>

# SQLite (default) – no extra setup needed:
DATABASE_URL=sqlite:///instance/pdf_manager.db
```

---

## Step 4 – Start the Backend

```bash
python app.py
```

The Flask server starts at <http://localhost:5000>.

---

## Step 5 – Frontend Setup (optional)

The Flask backend serves a server-rendered UI at port 5000, so the React frontend is **optional** for basic usage.

```bash
cd frontend
npm install
npm start       # Opens http://localhost:3000
```

---

## Step 6 – Verify

```bash
curl http://localhost:5000/health
# → {"status": "ok"}

curl http://localhost:5000/api/v1/documents
# → {"documents": [], "total": 0, ...}
```

---

## Database Setup (PostgreSQL, optional)

By default, PDF Manager uses an embedded SQLite database. To use PostgreSQL:

```bash
# Create role and database
psql -U postgres <<'SQL'
CREATE ROLE pdfmanager WITH LOGIN PASSWORD 'pdfmanager';
CREATE DATABASE pdfmanager OWNER pdfmanager;
SQL

# Apply schema
psql -U pdfmanager -d pdfmanager -f database/schema.sql

# (Optional) seed initial data
psql -U pdfmanager -d pdfmanager -f database/init.sql
```

Then update `.env`:

```dotenv
DATABASE_URL=postgresql://pdfmanager:pdfmanager@localhost:5432/pdfmanager
```

---

## Running Tests

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm test
```

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| `ModuleNotFoundError: fitz` | `pip install PyMuPDF` |
| `tesseract not found` | Install Tesseract and ensure it is on your `PATH` |
| Port 5000 already in use | Set `PORT=5001` in `.env` |
| Frontend CORS errors | Ensure `ALLOWED_ORIGINS` in `.env` includes `http://localhost:3000` |
| `ADMIN_PASSWORD` not set | Add it to `.env`; the app will print a generated password at startup |

See [Troubleshooting](../troubleshooting/common-issues.md) for more help.
