# Extracting Data

PDF Manager offers two extraction modes: OCR-only and full AI extraction (recommended).

## OCR Extraction

Runs the three-engine OCR ensemble and returns raw text with per-word confidence scores.

**Via UI:** Click **Run OCR** on the document page.

**Via API:**

```bash
curl -X POST http://localhost:5000/api/v1/extract/ocr/42
```

**Response includes:**

- `full_text` – concatenated text from all pages
- `pages[]` – per-page text, word list, and confidence scores
- `engines_used` – which OCR engines ran successfully

## AI / RAG Extraction (Recommended)

Runs OCR, then applies spaCy NER, rule-based field detection, and a RAG (LangChain + HuggingFace) refinement step. Returns structured field/value pairs.

**Via UI:** Click **Extract Fields** on the document page.

**Via API:**

```bash
curl -X POST "http://localhost:5000/api/v1/extract/ai/42?include_images=false" \
  -H "Content-Type: application/json" \
  -d '{"run_rag": true}'
```

**Response includes:**

- `fields[]` – extracted key/value pairs with confidence and source
- `quality` – document quality score and breakdown
- `heatmaps[]` – per-page confidence heatmap data
- `extraction_time_seconds` – total elapsed time

## OCR Engines

| Engine | Status | Notes |
|--------|--------|-------|
| PyMuPDF (text layer) | Always enabled | Fastest; best for digital PDFs |
| Tesseract | Enabled when installed | Good general-purpose OCR |
| EasyOCR | Optional | Better for complex layouts |
| PaddleOCR | Optional | Better for CJK and handwriting |

Engines are tried in order; results are merged using an ensemble confidence algorithm.

## Confidence Heatmap

After extraction, click **Heatmap** to view the confidence visualisation:

- 🟢 **Green** (≥ 85%) – high confidence
- 🟡 **Yellow** (65–84%) – medium confidence
- 🔴 **Red** (< 65%) – low confidence

Click any cell to see the words in that region and their individual scores.

## Next Steps

- [Editing Fields](editing.md) – correct low-confidence or incorrect fields
- [Exporting Results](exporting.md) – download results as JSON or CSV
