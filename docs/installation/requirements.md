# Requirements

Before installing PDF Manager, ensure your environment meets the following requirements.

## Hardware

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8 GB+ |
| Disk | 10 GB | 20 GB+ |
| GPU | — | Optional (for GPU-accelerated OCR) |

## Software

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.11 | Required for backend |
| Node.js | 18 | Required for React frontend |
| npm | 9 | Bundled with Node.js |
| Docker | 24 | Required for Docker install |
| Docker Compose | 2.20 | Required for Docker install |
| PostgreSQL | 15 | Optional; SQLite used by default |
| Tesseract OCR | 4.1+ | Required for OCR features |

## Operating Systems

- **Linux** (Ubuntu 22.04+, Debian 11+) — fully supported
- **macOS** (12 Monterey+) — supported for development
- **Windows** (10/11 with WSL2) — Docker recommended

## Python Packages

Key backend dependencies (installed automatically via `pip install -r backend/requirements.txt`):

| Package | Purpose |
|---------|---------|
| Flask 3.0+ | Web framework |
| Flask-SQLAlchemy 3.1+ | ORM |
| PyMuPDF 1.25+ | PDF parsing |
| pytesseract 0.3.10+ | Tesseract OCR bindings |
| opencv-python-headless 4.11+ | Image processing |
| sentence-transformers 2.7+ | RAG embeddings |
| langchain 0.2+ | RAG orchestration |
| spacy 3.7+ | Named Entity Recognition |
| Pillow | Image utilities |
| python-dotenv | Environment configuration |

## Network Ports

| Service | Default Port |
|---------|-------------|
| Flask Backend | 5000 |
| React Frontend | 3000 |
| PostgreSQL | 5432 |

## Environment Variables

A `.env` file in the project root is required. Copy `.env.example` to get started:

```bash
cp .env.example .env
```

Critical variables:

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask session signing key (generate with `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `ADMIN_PASSWORD` | Password for the admin account |
| `DATABASE_URL` | Database connection string (defaults to SQLite) |

See the [Development Setup](../development/setup.md) guide for a full variable reference.
