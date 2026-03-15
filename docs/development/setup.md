# Development Environment Setup

## Prerequisites

- Python 3.11+
- Node.js 18+
- Tesseract OCR 4.1+
- Git

## 1. Fork and Clone

```bash
git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
cd PDF-Manager
```

## 2. Backend Setup

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

pip install -r backend/requirements.txt
```

## 3. Environment Configuration

```bash
cp .env.example .env
```

Minimal development `.env`:

```dotenv
DEBUG=true
SECRET_KEY=dev-change-me
ADMIN_PASSWORD=dev-admin
DATABASE_URL=sqlite:///instance/pdf_manager.db
UPLOAD_DIR=uploads
EXPORT_DIR=exports
MAX_UPLOAD_SIZE_MB=50
```

## 4. Start the Backend

```bash
python app.py
# Serving at http://localhost:5000
```

## 5. Frontend Setup (optional)

```bash
cd frontend
npm install
npm start    # http://localhost:3000
```

## 6. Verify Everything Works

```bash
curl http://localhost:5000/health
# → {"status": "ok"}
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Enable Flask debug mode |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `5000` | Port number |
| `SECRET_KEY` | — | Required. Flask session key |
| `ADMIN_PASSWORD` | — | Admin account password |
| `DATABASE_URL` | `sqlite:///instance/pdf_manager.db` | Database connection |
| `UPLOAD_DIR` | `uploads` | Upload storage directory |
| `EXPORT_DIR` | `exports` | Export storage directory |
| `MAX_UPLOAD_SIZE_MB` | `50` | Max upload size in MB |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS allowed origins |

## IDE Recommendations

- **VS Code** with the Python, Pylance, and ESLint extensions
- **PyCharm** Professional for backend development

## Pre-commit Hooks (optional)

```bash
pip install pre-commit
pre-commit install
```
