# Getting Started

This guide walks you through your first PDF Manager session.

## 1. Access the Application

After [installation](../installation/index.md), open your browser:

| URL | Purpose |
|-----|---------|
| <http://localhost:5000/auth/login> | Login page |
| <http://localhost:3000> | React frontend (if running separately) |

## 2. Log In

Use the admin credentials you configured in `.env`:

- **Username:** `admin`
- **Password:** value of `ADMIN_PASSWORD`

## 3. Dashboard Overview

After login, the dashboard shows:

- **Documents** – a list of all uploaded PDFs with status and quality scores
- **Upload** button – to add a new document
- **Search / Filter** – to find documents by filename or date

## 4. Your First Document

1. Click **Upload** and select a PDF (up to 50 MB)
2. Wait for the upload confirmation
3. Click **Extract** to run OCR + AI extraction
4. Review the extracted fields in the split-view editor
5. Edit any incorrect fields inline
6. Click **Export** to download JSON or CSV

## 5. Understanding Confidence Scores

Every extracted field carries a confidence score and colour badge:

| Badge | Score | Meaning |
|-------|-------|---------|
| 🟢 Green | ≥ 85% | High confidence – likely correct |
| 🟡 Yellow | 65–84% | Medium confidence – review recommended |
| 🔴 Red | < 65% | Low confidence – manual correction needed |

## 6. Navigation

| Section | Access |
|---------|--------|
| Documents list | `/documents` |
| Upload page | `/upload` |
| Extraction view | `/documents/<id>/extract` |
| Export | Button in extraction view |

## Next Steps

- [Uploading PDFs](uploading.md) – drag-and-drop, file limits, and formats
- [Extracting Data](extraction.md) – OCR engines and AI pipeline
- [Editing Fields](editing.md) – inline editing and history
