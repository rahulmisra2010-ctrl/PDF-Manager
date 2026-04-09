# Error Reference

A comprehensive reference for error messages you may encounter in PDF Manager.

## Startup Errors

### `RuntimeError: The secret key is not set`

**Cause:** `SECRET_KEY` is missing from `.env`.

**Fix:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Add output to .env as SECRET_KEY=<value>
```

---

### `sqlalchemy.exc.OperationalError: no such table: documents`

**Cause:** Database tables have not been created.

**Fix:** Delete `instance/pdf_manager.db` and restart (SQLite creates tables automatically), or apply `database/schema.sql` for PostgreSQL.

---

### `ModuleNotFoundError: No module named 'cv2'`

**Cause:** OpenCV is not installed.

**Fix:** `pip install opencv-python-headless`

---

## Upload Errors

### `400 Only PDF files are accepted`

**Cause:** The uploaded file is not a PDF.

**Fix:** Ensure the file has a `.pdf` extension and was not renamed from another format.

---

### `413 Request Entity Too Large`

**Cause:** File exceeds `MAX_UPLOAD_SIZE_MB` (default 50 MB).

**Fix:** Increase `MAX_UPLOAD_SIZE_MB` in `.env` or compress the PDF.

---

## OCR Errors

### `500 tesseract not found`

**Cause:** Tesseract is not installed or not on `PATH`.

**Fix:** Install Tesseract (see [Requirements](../installation/requirements.md)).

---

### `422 Document has no extractable text`

**Cause:** The PDF is completely image-based and OCR returned no text.

**Fix:** 
- Ensure Tesseract is installed.
- Try a higher-quality scan of the document.
- Check that the PDF is not encrypted.

---

## Extraction Errors

### `500 RAG extraction failed: model not found`

**Cause:** The HuggingFace model could not be downloaded.

**Fix:**
- Check internet connectivity.
- Verify the HuggingFace cache directory is writable.
- Disable RAG with `{"run_rag": false}` in the request body.

---

### `500 spacy model not found`

**Cause:** The spaCy language model is not installed.

**Fix:**

```bash
python -m spacy download en_core_web_sm
```

---

## Database Errors

### `sqlalchemy.exc.IntegrityError: UNIQUE constraint failed`

**Cause:** A duplicate record was inserted.

**Fix:** This is usually caused by submitting a form twice. Reload the page and try again.

---

### `psycopg2.OperationalError: could not connect to server`

**Cause:** PostgreSQL is not running or `DATABASE_URL` is incorrect.

**Fix:**
1. Check that PostgreSQL is running: `pg_isready`
2. Verify `DATABASE_URL` in `.env`
3. Check network connectivity between the app and the database host

---

## Authentication Errors

### `401 Authentication required`

**Cause:** The request was made without a valid session cookie.

**Fix:** Log in at `/auth/login` first.

---

### `403 Forbidden`

**Cause:** The authenticated user does not have permission for the requested resource.

**Fix:** Log in with an admin account for admin-only operations.

---

## See Also

- [Common Issues](common-issues.md) – step-by-step solutions
- [FAQ](faq.md) – frequently asked questions
- [API Error Codes](../api/errors.md) – API-specific error codes
