# Local Development Setup

## Prerequisites

| Tool | Minimum Version |
|------|----------------|
| Python | 3.11 |
| Node.js | 18 |
| npm | 9 |
| Docker & Docker Compose | 24 |
| PostgreSQL (optional, if not using Docker) | 15 |

---

## Option A – Docker Compose (Recommended)

This starts the backend, frontend, and PostgreSQL together.

```bash
# Clone the repository
git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
cd PDF-Manager

# Build and start all services
docker compose up --build

# First-time database initialization (in another terminal)
docker compose exec postgres psql -U pdfmanager -d pdfmanager -f /docker-entrypoint-initdb.d/init.sql
```

Services:
| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend / UI | http://localhost:5000 |
| Login page | http://localhost:5000/auth/login |
| PostgreSQL | localhost:5432 |

---

## Option B – Manual Setup

### 1. Backend (Flask)

```bash
cd PDF-Manager    # repository root

# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Create .env file
cp .env.example .env             # edit as needed

# Start the Flask server (UI + JSON endpoints)
python app.py                    # http://localhost:5000
```

### 2. Database

```bash
# Create the role and database
psql -U postgres <<'SQL'
CREATE ROLE pdfmanager WITH LOGIN PASSWORD 'pdfmanager';
CREATE DATABASE pdfmanager OWNER pdfmanager;
SQL

# Apply schema
psql -U pdfmanager -d pdfmanager -f database/schema.sql

# Seed initial data
psql -U pdfmanager -d pdfmanager -f database/init.sql
```

### 3. Frontend

```bash
cd frontend
npm install
npm start     # http://localhost:3000
```

---

## Environment Variables

Create a `backend/.env` file (copy from `.env.example`):

```dotenv
DEBUG=true
HOST=0.0.0.0
PORT=5000
ALLOWED_ORIGINS=["http://localhost:3000"]
DATABASE_URL=postgresql://pdfmanager:pdfmanager@localhost:5432/pdfmanager
UPLOAD_DIR=uploads
EXPORT_DIR=exports
MAX_UPLOAD_SIZE_MB=50
ML_CONFIDENCE_THRESHOLD=0.75
USE_GPU=false
```

---

## Running Tests

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
npm test
```

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| `ModuleNotFoundError: fitz` | Run `pip install PyMuPDF` |
| Port 5000 already in use | Change `PORT` in `.env` or kill the process |
| CORS error in browser | Ensure `ALLOWED_ORIGINS` includes your frontend URL |
| DB connection refused | Check `DATABASE_URL` and that PostgreSQL is running |
