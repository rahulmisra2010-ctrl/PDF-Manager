# API Changelog

All notable changes to the PDF Manager REST API are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Planned
- `GET /api/v1/export/{document_id}` — dedicated export endpoint with JSON and CSV formats
- `GET /api/v1/stats` — REST stats endpoint (currently available at `/api/stats`)
- `GET /api/v1/search` — REST search endpoint (currently available at `/search/api`)
- Webhook delivery for document and extraction events
- API key authentication as an alternative to session cookies
- Admin user management endpoints (`/api/v1/admin/users`)

---

## [1.0.0] — Initial Release

### Added

#### Document Management
- `POST /api/v1/upload` — Upload a PDF file
- `GET /api/v1/documents` — List all documents with pagination
- `GET /api/v1/documents/{id}` — Get document metadata
- `DELETE /api/v1/documents/{id}` — Delete a document
- `GET /api/v1/documents/{id}/pdf` — Serve the original PDF file
- `GET /api/v1/documents/{id}/heatmap` — Generate OCR confidence heatmap

#### Extraction
- `POST /api/v1/extract/ocr/{document_id}` — Multi-engine OCR extraction
- `POST /api/v1/extract/ai/{document_id}` — AI + RAG extraction pipeline

#### Fields
- `GET /api/v1/fields/{document_id}` — List extracted fields for a document
- `PUT /api/v1/fields/{field_id}` — Update a field value (with history recording)
- `GET /api/v1/fields/{field_id}/history` — Get field edit history

#### OCR Data
- `GET /api/v1/ocr/{document_id}/confidence` — Per-character OCR confidence data

#### Authentication (non-versioned)
- `POST /auth/login` — Session login
- `GET /auth/logout` — Session logout

#### Search (non-versioned)
- `GET /search/api` — Full-text search over documents and fields

#### Dashboard (non-versioned)
- `GET /api/stats` — Aggregate statistics for the dashboard

---

## Migration Guide

### Upgrading to v1.0.0

This is the initial stable release. No migration is required from pre-release builds.

Key behaviours to be aware of:

- `document_id` is always an integer (database primary key).
- `field_id` is always an integer.
- Confidence scores are floats in the range `[0.0, 1.0]`.
- The `status` field of a document uses lowercase values: `uploaded`, `extracted`, `edited`, `approved`, `rejected`.
- The `PUT /api/v1/fields/{field_id}` endpoint records the previous value in `FieldEditHistory` automatically.
- AI extraction (`/extract/ai`) **replaces** all existing fields for the document on each call.
