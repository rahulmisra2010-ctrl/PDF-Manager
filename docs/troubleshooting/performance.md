# Performance Tuning

## Backend Performance

### Use Gunicorn in Production

The Flask development server is single-threaded. Use Gunicorn for production:

```bash
pip install gunicorn
gunicorn "app:create_app()" \
  --workers 4 \
  --bind 0.0.0.0:5000 \
  --timeout 120
```

**Worker count:** `2 × CPU cores + 1` is a common starting point. For OCR-heavy workloads, reduce to `CPU cores` to avoid memory pressure.

### Database Connection Pooling

For PostgreSQL, configure SQLAlchemy's connection pool:

```python
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size": 10,
    "pool_timeout": 30,
    "pool_recycle": 1800,
    "max_overflow": 20,
}
```

### Disable Unused OCR Engines

If EasyOCR or PaddleOCR are installed but not needed, disable them to reduce startup time and memory usage.

### Cache the Embedding Model

The `all-MiniLM-L6-v2` model is loaded once per worker process. It is cached to disk by the `sentence-transformers` library. Ensure `~/.cache/huggingface` (or the configured cache directory) persists between container restarts.

---

## Frontend Performance

### Production Build

Use the optimised React production build:

```bash
cd frontend
npm run build
```

Serve the `build/` directory via nginx or a CDN instead of the development server.

---

## OCR Performance

| Technique | Impact |
|-----------|--------|
| Use PyMuPDF for digital PDFs | Very fast; no image rendering needed |
| Set `include_images=false` | Skips base64 PNG encoding |
| Reduce PDF page count | Process only required pages |
| Use a GPU for PaddleOCR/EasyOCR | 3–5× speed improvement |

### GPU Acceleration

Set `USE_GPU=true` in `.env` if a CUDA-compatible GPU is available:

```dotenv
USE_GPU=true
```

Ensure the appropriate CUDA-enabled packages are installed (e.g., `torch` with CUDA, `paddlepaddle-gpu`).

---

## Memory Usage

| Component | Approximate RAM |
|-----------|----------------|
| Flask (base) | ~150 MB |
| + Tesseract | +50 MB |
| + EasyOCR | +800 MB |
| + PaddleOCR | +1 GB |
| + sentence-transformers | +200 MB |

A minimal deployment (PyMuPDF + Tesseract) requires ~300 MB per worker. A full installation requires ~2 GB per worker.

---

## Database Performance

- Add indexes on `document_id` in `extracted_fields` and `ocr_character_data` (already in `schema.sql`).
- Use `EXPLAIN ANALYZE` in PostgreSQL to identify slow queries.
- Archive or delete old documents to keep the database size manageable.

---

## Profiling

To profile a slow endpoint:

```python
# Temporary; remove before production
import cProfile, pstats, io

pr = cProfile.Profile()
pr.enable()
# ... your code ...
pr.disable()
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(20)
print(s.getvalue())
```
