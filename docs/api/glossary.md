# Glossary

Common terms used throughout the PDF Manager API documentation.

---

## A

**API (Application Programming Interface)**
A set of rules and endpoints that allow programs to communicate with PDF Manager. The REST API is available under `/api/v1`.

**API Key**
A token used to authenticate API requests without a session cookie. Not yet implemented; planned for a future release.

**Audit Log**
An immutable record of user actions (uploads, edits, deletions) stored in the `audit_logs` table.

---

## B

**Base URL**
The root address of the API server, e.g. `http://localhost:5000`. All API paths are appended to this.

**Bounding Box (bbox)**
The rectangular region on a PDF page where a field or word was detected, described by `x`, `y`, `width`, and `height` in page-coordinate units.

**Blueprint**
A Flask component that groups related routes. PDF Manager uses blueprints for `auth`, `pdf`, `dashboard`, `search`, `users`, and `api_v1`.

---

## C

**Confidence Score**
A float between `0.0` and `1.0` representing the OCR/AI engine's certainty about an extracted value. Scores ≥ 0.85 are considered high confidence.

**Cookie**
The `session` cookie set by the server after login. Must be included in every authenticated request.

**CSRF Token**
A Cross-Site Request Forgery token required for form submissions. Managed automatically by Flask-WTF.

---

## D

**Document**
An uploaded PDF file represented in the database with an integer `id`, filename, status, and associated extracted fields.

**Document ID**
The integer primary key of a `Document` record. Returned in the upload response as `document_id`.

---

## E

**EasyOCR**
An open-source OCR library used as one of the extraction engines in the multi-engine pipeline.

**Extraction**
The process of identifying and extracting structured field values from a PDF using OCR and/or AI models.

**ExtractedField**
A single named key-value pair extracted from a document (e.g. `Name: John Doe`). Stored in the `extracted_fields` table.

---

## F

**Field**
See *ExtractedField*.

**Field Edit History**
A log of all changes made to an `ExtractedField`, stored in the `field_edit_history` table.

---

## H

**Heatmap**
A visual overlay on a PDF page showing OCR confidence by color (green = high, red = low).

**HTTP Status Code**
A 3-digit number indicating the outcome of an API request (e.g. `200 OK`, `404 Not Found`).

---

## J

**JSON (JavaScript Object Notation)**
The data format used for all API request bodies and responses.

---

## O

**OCR (Optical Character Recognition)**
The technology that converts images of text (scanned PDFs) into machine-readable strings. PDF Manager supports PyMuPDF, Tesseract, EasyOCR, and PaddleOCR.

---

## P

**Pagination**
Splitting a large list response into multiple pages. Controlled with `page` and `per_page` query parameters.

**PaddleOCR**
An open-source OCR framework used as one of the extraction engines.

**PyMuPDF**
A Python binding for MuPDF used for fast text extraction from selectable PDFs.

---

## R

**RAG (Retrieval-Augmented Generation)**
A technique that combines vector-based document retrieval with language model generation to improve extraction accuracy. Enabled by default in the AI extraction endpoint.

**Rate Limit**
A cap on the number of API requests allowed in a time window. Excess requests receive a `429 Too Many Requests` response.

**REST (Representational State Transfer)**
The architectural style used by the PDF Manager API. Endpoints use standard HTTP methods: GET, POST, PUT, DELETE.

**Role**
A permission level assigned to each user: `Admin`, `Verifier`, or `Viewer`.

---

## S

**Session**
Server-side state associated with a logged-in user, identified by the session cookie.

**Status**
The processing state of a document: `uploaded`, `extracted`, `edited`, `approved`, or `rejected`.

---

## T

**Tesseract**
An open-source OCR engine developed by Google, used as one of the extraction engines.

**Token**
A credential used to authenticate API requests. Session tokens are stored in the session cookie.

---

## V

**Version**
The edit version counter on an `ExtractedField`. Starts at `1` and increments with each update.
