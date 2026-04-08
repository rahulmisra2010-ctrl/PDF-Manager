# PDF Manager

**PDF Manager** is an AI-powered PDF management application that extracts structured data from scanned documents using OCR and field-mapping heuristics.

## Features

- **OCR Extraction** – Tesseract-based text extraction from scanned PDFs
- **Field Mapping** – Automatically maps extracted text to address-book fields
- **REST API** – Flask-based API (v1) for all extraction and document operations
- **RAG Support** – Retrieval-Augmented Generation for semantic document search
- **React Frontend** – Modern web UI for document management
- **Docker** – Fully containerised with Docker Compose

## Quick Start

```bash
# Clone the repository
git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
cd PDF-Manager

# Copy the environment template
cp .env.example .env

# Start with Docker Compose
docker compose up --build
```

The application will be available at:

- **Frontend**: <http://localhost:3000>
- **Backend API**: <http://localhost:5000/api/v1>

## Documentation Sections

| Section | Description |
|---------|-------------|
| [API Reference](api/index.md) | REST API endpoints and request/response formats |
| [Deployment](deployment/index.md) | Docker, environment variables, and production setup |
| [Development](development/index.md) | Local setup, testing, and contribution guidelines |
