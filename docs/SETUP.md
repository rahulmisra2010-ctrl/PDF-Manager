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

### File location

The `.env` file belongs in the **project root** — the same directory as `app.py`:

```
PDF-Manager/          ← repository root
├── .env              ← your local settings (git-ignored)
├── .env.example      ← committed template — copy this
└── app.py
```

> `app.py` also loads `backend/.env` for backwards compatibility, but the project
> root is the canonical location.  If a key appears in both files, the root
> `.env` takes precedence.

### Creating the file

```bash
cp .env.example .env   # then open .env and edit the values below
```

### Critical values

#### `SECRET_KEY`

Signs Flask session cookies and CSRF tokens. Generate a strong random value:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

```dotenv
SECRET_KEY=<paste-generated-value>
```

> ⚠️ **Duplicate-key warning** — keep exactly **one** `SECRET_KEY` line in your
> `.env`.  `python-dotenv` silently uses the first occurrence and ignores any
> extras, which can cause hard-to-debug behaviour.  Verify with:
>
> ```bash
> grep -n "SECRET_KEY" .env   # must print exactly one line
> ```

#### `ADMIN_PASSWORD`

Password for the auto-created `admin` account.  Leave blank to have a random
password printed at startup (convenient for a first look), but **always set an
explicit password for any shared or production deployment**:

```dotenv
ADMIN_PASSWORD=<strong-unique-password>
```

### Development vs production

Create a `.env` file in the repository root (copy from `.env.example`):

```dotenv
# Application (development defaults)
DEBUG=true
HOST=0.0.0.0
PORT=5000
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
# Replace this sample value before deploying to production
SECRET_KEY=dev-change-me
# Dev-only default; choose a strong password before deploying
ADMIN_PASSWORD=dev-admin-please-change

# Database (SQLite by default; uncomment PostgreSQL if desired)
DATABASE_URL=sqlite:///instance/pdf_manager.db
# DATABASE_URL=postgresql://pdfmanager:pdfmanager@localhost:5432/pdfmanager

# Storage
UPLOAD_DIR=uploads
EXPORT_DIR=exports
MAX_UPLOAD_SIZE_MB=50

# ML configuration (used when torch is installed)
ML_CONFIDENCE_THRESHOLD=0.75
USE_GPU=false
```

For **production**, change the following from the defaults above:

| Setting | Production value |
|---------|-----------------|
| `DEBUG` | `false` |
| `SECRET_KEY` | Cryptographically random (≥ 32 hex chars) |
| `ADMIN_PASSWORD` | Strong, unique password |
| `DATABASE_URL` | PostgreSQL connection string |
| `ALLOWED_ORIGINS` | Your real frontend domain(s) |

### Getting help

If you cannot locate, create, or correct your `.env` file, open an issue in this
repository and include the error message you're seeing (but **never paste your
actual secret values**).

Let me know if you need any more details about this setup or help correcting your .env for production or development.

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
