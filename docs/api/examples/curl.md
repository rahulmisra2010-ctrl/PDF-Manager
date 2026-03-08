# cURL Examples

All examples below assume:
- The API is running at `http://localhost:5000`
- You have saved your session cookie to `cookies.txt` after logging in

---

## Authentication

### Login

```bash
# Log in and save the session cookie
curl -c cookies.txt \
  -X POST http://localhost:5000/auth/login \
  -d "username=admin&password=yourpassword"
```

### Logout

```bash
curl -b cookies.txt http://localhost:5000/auth/logout
```

---

## Upload PDF

```bash
curl -b cookies.txt \
  -X POST http://localhost:5000/api/v1/upload \
  -F "file=@/path/to/document.pdf"
```

**Response:**

```json
{
  "document_id": 42,
  "filename": "document.pdf",
  "status": "uploaded",
  "message": "PDF uploaded successfully. Call /api/v1/extract/ocr or /api/v1/extract/ai to process.",
  "file_size_bytes": 102400
}
```

---

## OCR Extraction

```bash
curl -b cookies.txt \
  -X POST http://localhost:5000/api/v1/extract/ocr/42
```

---

## AI Extraction

```bash
curl -b cookies.txt \
  -X POST http://localhost:5000/api/v1/extract/ai/42 \
  -H "Content-Type: application/json" \
  -d '{"run_rag": true}'
```

### AI Extraction with heatmap images

```bash
curl -b cookies.txt \
  -X POST "http://localhost:5000/api/v1/extract/ai/42?include_images=true" \
  -H "Content-Type: application/json" \
  -d '{"run_rag": true}'
```

---

## List Documents

```bash
curl -b cookies.txt http://localhost:5000/api/v1/documents
```

### With pagination

```bash
curl -b cookies.txt "http://localhost:5000/api/v1/documents?page=2&per_page=50"
```

---

## Get Document

```bash
curl -b cookies.txt http://localhost:5000/api/v1/documents/42
```

---

## Delete Document

```bash
curl -b cookies.txt \
  -X DELETE http://localhost:5000/api/v1/documents/42
```

---

## Download PDF

```bash
curl -b cookies.txt \
  -o downloaded.pdf \
  http://localhost:5000/api/v1/documents/42/pdf
```

---

## Get Extracted Fields

```bash
curl -b cookies.txt http://localhost:5000/api/v1/fields/42
```

---

## Update a Field

```bash
curl -b cookies.txt \
  -X PUT http://localhost:5000/api/v1/fields/1 \
  -H "Content-Type: application/json" \
  -d '{"value": "Jane Doe"}'
```

---

## Get Field History

```bash
curl -b cookies.txt http://localhost:5000/api/v1/fields/1/history
```

---

## OCR Confidence Data

```bash
curl -b cookies.txt http://localhost:5000/api/v1/ocr/42/confidence
```

---

## Document Heatmap

```bash
# Heatmap data only
curl -b cookies.txt "http://localhost:5000/api/v1/documents/42/heatmap?page=1"

# Include base64 PNG image
curl -b cookies.txt "http://localhost:5000/api/v1/documents/42/heatmap?page=1&image=true"
```

---

## Dashboard Statistics

```bash
curl -b cookies.txt http://localhost:5000/api/stats
```

---

## Search

```bash
curl -b cookies.txt "http://localhost:5000/search/api?q=invoice"
```

---

## Complete Workflow Script

```bash
#!/bin/bash
set -e

BASE="http://localhost:5000"
COOKIE_JAR="cookies.txt"
PDF_FILE="/path/to/document.pdf"

# 1. Login
echo "Logging in…"
curl -s -c "$COOKIE_JAR" \
  -X POST "$BASE/auth/login" \
  -d "username=admin&password=yourpassword" > /dev/null

# 2. Upload
echo "Uploading PDF…"
DOC_ID=$(curl -s -b "$COOKIE_JAR" \
  -X POST "$BASE/api/v1/upload" \
  -F "file=@$PDF_FILE" | python3 -c "import sys,json; print(json.load(sys.stdin)['document_id'])")
echo "Document ID: $DOC_ID"

# 3. Extract
echo "Extracting with AI…"
curl -s -b "$COOKIE_JAR" \
  -X POST "$BASE/api/v1/extract/ai/$DOC_ID" \
  -H "Content-Type: application/json" \
  -d '{"run_rag": true}' | python3 -m json.tool

# 4. List fields
echo "Fields:"
curl -s -b "$COOKIE_JAR" "$BASE/api/v1/fields/$DOC_ID" | python3 -m json.tool
```

---

## Tips

- Use `-s` (silent) to suppress progress output
- Use `-v` (verbose) to see request and response headers
- Use `| python3 -m json.tool` to pretty-print JSON responses
- Use `-o filename` to save responses to a file
