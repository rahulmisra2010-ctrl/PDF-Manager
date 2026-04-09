# Frequently Asked Questions

## Installation

**Q: Do I need all three OCR engines?**

No. PyMuPDF and Tesseract are the only required engines. EasyOCR and PaddleOCR are optional and improve accuracy for complex layouts, but they significantly increase install size and startup time.

---

**Q: Can I run PDF Manager without Docker?**

Yes. See the [Manual Installation](../installation/manual.md) guide.

---

**Q: Does PDF Manager support Windows?**

Yes, with some limitations. Docker (via WSL2) is the recommended approach on Windows. Manual setup is possible but Tesseract installation is more involved. See the [Tesseract Windows installation guide](https://github.com/UB-Mannheim/tesseract/wiki).

---

## Usage

**Q: What is the maximum PDF file size?**

50 MB by default. Change `MAX_UPLOAD_SIZE_MB` in `.env` to increase this limit.

---

**Q: Why is extraction slow on the first run?**

On the first run, sentence-transformers downloads the `all-MiniLM-L6-v2` model (~80 MB). Subsequent runs use the cached model.

---

**Q: Why are some fields missing from the extraction results?**

- The PDF may not contain text in the expected format. Check the `full_text` from the OCR response.
- The field type may not have a matching rule or NER label. Consider adding a custom rule.
- If confidence is very low (< 0.65), the field may not be extracted. Try a higher-quality PDF scan.

---

**Q: Can I extract data from scanned PDFs?**

Yes, as long as at least one OCR engine (Tesseract) is installed. Scanned PDFs are slower to process than digital PDFs because the text layer must be generated from the image.

---

**Q: How do I reset the admin password?**

Set a new value for `ADMIN_PASSWORD` in `.env` and restart the application. The admin account password is updated on startup.

---

## API

**Q: How do I authenticate API requests programmatically?**

Use a `requests.Session()` in Python to persist the session cookie. See [Authentication](../api/authentication.md).

---

**Q: Is there an OpenAPI / Swagger UI?**

Not yet. The [API Reference](../api/index.md) in this documentation covers all endpoints.

---

## Deployment

**Q: Can I use SQLite in production?**

SQLite is suitable for single-server deployments with low concurrent load. For multiple workers or concurrent requests, use PostgreSQL.

---

**Q: How do I back up the database?**

See [Backup & Recovery](../deployment/backup.md).

---

**Q: How do I update PDF Manager to a newer version?**

```bash
git pull origin main
docker compose build && docker compose up -d
```

Always back up the database before updating.
