# Common Issues and Solutions

## Installation Issues

### `ModuleNotFoundError: No module named 'fitz'`

PyMuPDF is not installed or the virtual environment is not active.

```bash
source .venv/bin/activate
pip install PyMuPDF
```

---

### `tesseract: command not found`

Tesseract is not installed or not on the PATH.

=== "Ubuntu/Debian"

    ```bash
    sudo apt-get install tesseract-ocr tesseract-ocr-eng
    ```

=== "macOS"

    ```bash
    brew install tesseract
    ```

=== "Windows"

    Download the installer from [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) and add the install directory to your PATH.

---

### Port 5000 is already in use

Another process is using port 5000 (commonly macOS AirPlay on macOS 12+).

```bash
# Change the port
echo "PORT=5001" >> .env
python app.py
```

Or kill the conflicting process:

```bash
# Find the process
lsof -i :5000
# Kill it (replace <PID>)
kill <PID>
```

---

### `SECRET_KEY` is not set

```
RuntimeError: The secret key is not set. Set the application's secret key.
```

Add `SECRET_KEY` to your `.env`:

```bash
echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" >> .env
```

---

## Extraction Issues

### Extraction returns empty fields

1. Check that the PDF has extractable text: `curl -X POST /api/v1/extract/ocr/<id>` and inspect `full_text`.
2. If `full_text` is empty, the PDF is image-only and requires OCR. Ensure Tesseract is installed.
3. If OCR returns text but AI extraction returns no fields, the text format may not match any rules. Check the raw text and compare against the field detection patterns.

---

### Very low confidence scores

- The PDF may be a low-quality scan. Try a higher-DPI scan (300 DPI recommended).
- The PDF may contain non-standard fonts. Enable EasyOCR for better font handling.

---

### RAG extraction takes too long

The first RAG run downloads the embedding model (~80 MB). Subsequent runs use the cache.

For faster operation, disable RAG:

```bash
curl -X POST http://localhost:5000/api/v1/extract/ai/42 \
  -H "Content-Type: application/json" \
  -d '{"run_rag": false}'
```

---

## Upload Issues

### `413 Request Entity Too Large`

The file exceeds the configured limit.

```dotenv
MAX_UPLOAD_SIZE_MB=100
```

If using nginx, also update `client_max_body_size`:

```nginx
client_max_body_size 110m;
```

---

## Database Issues

### `OperationalError: no such table`

The database has not been initialised.

```bash
# SQLite: delete and recreate
rm instance/pdf_manager.db
python app.py  # creates tables on startup

# PostgreSQL
psql -U pdfmanager -d pdfmanager -f database/schema.sql
```

---

### `connection refused` to PostgreSQL

1. Check that PostgreSQL is running: `pg_isready -U pdfmanager`
2. Verify `DATABASE_URL` in `.env`
3. Check the database host and port

---

## CORS Errors in Browser

```
Access to fetch at 'http://localhost:5000' from origin 'http://localhost:3000' has been blocked by CORS policy
```

Add the frontend origin to `ALLOWED_ORIGINS` in `.env`:

```dotenv
ALLOWED_ORIGINS=["http://localhost:3000"]
```

Restart the Flask server after changing `.env`.
