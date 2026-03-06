# Phase 1 – Week 1-2 Development Guide

## Overview

Phase 1 focuses on the core pipeline: **upload → extract → store → preview**.
By the end of Week 2, you should have a working end-to-end flow where users
can upload a PDF, see the extracted text and tables, and download a JSON/CSV
copy of the data.

---

## Week 1 – Backend Foundations

### Goals
- Set up the Flask backend
- Implement PDF upload and basic text extraction
- Detect tables with OpenCV
- Store document metadata and extracted fields in PostgreSQL

### Day-by-Day Checklist

| Day | Task |
|-----|------|
| 1   | Clone repo, install Python deps, start Flask dev server |
| 2   | Implement `POST /api/v1/upload` – accept PDF, save to disk |
| 3   | Implement `POST /api/v1/extract/{id}` – text extraction with PyMuPDF |
| 4   | Add OpenCV table detection in `pdf_service.py` |
| 5   | Wire up PostgreSQL – insert extracted fields into `extracted_fields` table |

### Key Commands

```bash
# Install Python dependencies
cd PDF-Manager    # repository root
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

# Start the backend (Flask, port 5000)
python app.py

# Initialize the database
psql -U postgres -c "CREATE DATABASE pdfmanager OWNER pdfmanager;"
psql -U pdfmanager -d pdfmanager -f database/init.sql
```

### Acceptance Criteria – Week 1
- [ ] PDF upload endpoint returns a `document_id`
- [ ] `/extract/{id}` returns `extracted_text` and `tables`
- [ ] Data is stored in the `documents` and `extracted_fields` tables
- [ ] `/health` returns `{"status": "healthy"}`

---

## Week 2 – Frontend & Integration

### Goals
- Build the React UI (upload, display, basic edit)
- Connect frontend to backend API
- Add JSON/CSV export
- Manual end-to-end testing

### Day-by-Day Checklist

| Day | Task |
|-----|------|
| 6   | Scaffold React app, install deps, wire up `api.js` |
| 7   | Build `UploadPDF` component with drag-and-drop |
| 8   | Build `DataDisplay` – show fields table and raw text |
| 9   | Build `EditData` – inline field editing |
| 10  | Export flow (PDF / JSON / CSV) + download link |

### Key Commands

```bash
cd frontend
npm install
npm start         # starts dev server on http://localhost:3000
npm test          # run tests
npm run build     # production build
```

### Acceptance Criteria – Week 2
- [ ] User can drag-and-drop or browse for a PDF
- [ ] After upload, clicking "Extract Data" shows fields and tables
- [ ] User can edit any field value and save
- [ ] User can export to PDF, JSON, or CSV and download

---

## Useful Tools

| Tool | Purpose |
|------|---------|
| [Dashboard login](http://localhost:5000/auth/login) | Web UI once the backend is running |
| [pgAdmin](https://www.pgadmin.org/) | PostgreSQL GUI |
| React DevTools | Debug component state |

---

## Next Steps (Phase 2)

- Improve ML extraction accuracy with a fine-tuned model
- Add user authentication
- Deploy to cloud (AWS / GCP)
- Add batch processing for multiple PDFs
