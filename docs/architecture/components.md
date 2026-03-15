# Component Descriptions

## React Frontend (`frontend/src/`)

| Component | File | Description |
|-----------|------|-------------|
| App | `App.js` | Top-level routing and state |
| PDFViewer | `components/PDFViewer.js` | react-pdf viewer with zoom/scroll |
| FieldsEditor | `components/FieldsEditor.js` | Editable fields table with confidence badges |
| OCRConfidenceHeatmap | `components/OCRConfidenceHeatmap.js` | Word-level confidence heatmap grid |
| PerformanceDashboard | `components/PerformanceDashboard.js` | Document quality score and regional breakdown |
| ExtractionPage | `components/ExtractionPage.js` | Split-view orchestrator (PDF + fields) |
| API Service | `services/api.js` | Fetch wrapper for all API calls |

### Confidence Thresholds (Frontend)

| Threshold | Value | Badge |
|-----------|-------|-------|
| High | ≥ 0.85 | 🟢 Green |
| Medium | 0.65 – 0.84 | 🟡 Yellow |
| Low | < 0.65 | 🔴 Red |

---

## Flask Backend

### API Blueprint (`backend/api/routes.py`)

Registered at `/api/v1`. Contains all 12 REST endpoints. Protected by `@login_required`.

### Blueprints (`blueprints/`)

| Blueprint | Prefix | Purpose |
|-----------|--------|---------|
| `auth` | `/auth` | Login, logout |
| `main` | `/` | Server-rendered UI pages |
| `rag` | `/api/v1` | Additional RAG endpoints |

---

## OCR Layer (`backend/ocr/`)

### `ocr_engine.py`

Orchestrates the three OCR engines:

1. **PyMuPDF text layer** – extracts text directly from digital PDFs (fastest)
2. **Tesseract** – general-purpose OCR; always installed
3. **EasyOCR** – optional; better layout handling
4. **PaddleOCR** – optional; better CJK and handwriting

Results are merged using an ensemble algorithm that selects the highest-confidence word result per position.

### `confidence_calculator.py`

Computes:
- Per-word confidence from OCR engine output
- Per-region confidence (header, body, footer)
- Document-level quality score and grade

### `heatmap_generator.py`

Projects word confidence scores onto a grid (40 columns × 56 rows by default) to generate the visual heatmap.

---

## Extraction Layer (`backend/extraction/`)

### `field_detector.py`

Two-pass field detection:

1. **Rule-based regex** – matches known field patterns (phone numbers, zip codes, email addresses, etc.)
2. **spaCy NER** – catches names, organisations, and locations

### `rag_system.py`

LangChain + HuggingFace `all-MiniLM-L6-v2` embeddings:

1. Encodes the OCR text into vector embeddings
2. Retrieves the most relevant passages for each field type
3. Uses a QA prompt to refine ambiguous field values

### `extractor.py`

Orchestrates the full pipeline: OCR → field detection → RAG refinement → confidence assignment.

---

## Services (`backend/services/`)

| Service | Purpose |
|---------|---------|
| `pdf_service.py` | PyMuPDF PDF parsing, text/image extraction, field mapping |
| `ai_extraction_service.py` | Full AI pipeline service wrapping extractor + heatmap |
| `rag_service.py` | RAG embedding storage and retrieval |
| `ml_service.py` | Optional PyTorch field classifier |
