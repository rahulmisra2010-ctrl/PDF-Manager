# Python Code Examples

## Prerequisites

```bash
pip install requests
```

## Authentication

```python
import requests

# Create a persistent session to manage cookies
session = requests.Session()

def login(base_url: str, username: str, password: str) -> bool:
    """Log in and store the session cookie."""
    resp = session.post(f"{base_url}/auth/login", data={
        "username": username,
        "password": password,
    })
    return resp.ok

base_url = "http://localhost:5000"
login(base_url, "admin", "yourpassword")
```

---

## Upload a PDF

```python
def upload_pdf(file_path: str) -> dict:
    with open(file_path, "rb") as f:
        resp = session.post(
            f"{base_url}/api/v1/upload",
            files={"file": (file_path.split("/")[-1], f, "application/pdf")},
        )
    resp.raise_for_status()
    return resp.json()

result = upload_pdf("/path/to/document.pdf")
document_id = result["document_id"]
print(f"Uploaded: {result['filename']} → ID {document_id}")
```

---

## Extract Data (AI + RAG)

```python
def extract_ai(document_id: int, run_rag: bool = True) -> dict:
    resp = session.post(
        f"{base_url}/api/v1/extract/ai/{document_id}",
        json={"run_rag": run_rag},
    )
    resp.raise_for_status()
    return resp.json()

extraction = extract_ai(document_id)
for field in extraction["fields"]:
    print(f"  {field['field_name']}: {field['value']} ({field['confidence']:.0%})")
```

---

## Extract Data (OCR only)

```python
def extract_ocr(document_id: int) -> dict:
    resp = session.post(f"{base_url}/api/v1/extract/ocr/{document_id}")
    resp.raise_for_status()
    return resp.json()

ocr = extract_ocr(document_id)
print(f"Pages: {ocr['total_pages']}, engines: {ocr['engines_used']}")
print(ocr["full_text"][:500])
```

---

## List Documents

```python
def list_documents(page: int = 1, per_page: int = 20) -> dict:
    resp = session.get(
        f"{base_url}/api/v1/documents",
        params={"page": page, "per_page": per_page},
    )
    resp.raise_for_status()
    return resp.json()

data = list_documents()
print(f"Total: {data['total']} documents across {data['pages']} pages")
for doc in data["documents"]:
    print(f"  [{doc['id']}] {doc['filename']} — {doc['status']}")
```

---

## Get Extracted Fields

```python
def get_fields(document_id: int) -> list:
    resp = session.get(f"{base_url}/api/v1/fields/{document_id}")
    resp.raise_for_status()
    return resp.json()

fields = get_fields(document_id)
for f in fields:
    edited = " (edited)" if f["is_edited"] else ""
    print(f"  {f['field_name']}: {f['value']}{edited}")
```

---

## Update a Field

```python
def update_field(field_id: int, new_value: str) -> dict:
    resp = session.put(
        f"{base_url}/api/v1/fields/{field_id}",
        json={"value": new_value},
    )
    resp.raise_for_status()
    return resp.json()

updated = update_field(field_id=1, new_value="Jane Doe")
print(f"Updated to: {updated['value']} (version {updated['version']})")
```

---

## Get Field History

```python
def get_field_history(field_id: int) -> list:
    resp = session.get(f"{base_url}/api/v1/fields/{field_id}/history")
    resp.raise_for_status()
    return resp.json()

history = get_field_history(field_id=1)
for entry in history:
    print(f"  {entry['edited_at']}: '{entry['old_value']}' → '{entry['new_value']}'")
```

---

## Delete a Document

```python
def delete_document(document_id: int) -> dict:
    resp = session.delete(f"{base_url}/api/v1/documents/{document_id}")
    resp.raise_for_status()
    return resp.json()

result = delete_document(document_id)
print(f"Status: {result['status']}")
```

---

## Complete Workflow

```python
import requests

BASE_URL = "http://localhost:5000"
session = requests.Session()

# 1. Login
session.post(f"{BASE_URL}/auth/login", data={"username": "admin", "password": "pass"})

# 2. Upload
with open("invoice.pdf", "rb") as f:
    resp = session.post(f"{BASE_URL}/api/v1/upload", files={"file": f})
doc_id = resp.json()["document_id"]

# 3. Extract
extraction = session.post(
    f"{BASE_URL}/api/v1/extract/ai/{doc_id}",
    json={"run_rag": True}
).json()

# 4. Review and correct fields
fields = session.get(f"{BASE_URL}/api/v1/fields/{doc_id}").json()
for field in fields:
    if field["confidence"] < 0.85:
        print(f"Low confidence: {field['field_name']} = {field['value']}")

# 5. Export fields as JSON
export = {f["field_name"]: f["value"] for f in fields}
print(export)
```

---

## Error Handling

```python
from requests.exceptions import HTTPError
import time

def safe_request(session, method, url, **kwargs):
    """Make a request with retry on rate limiting."""
    for attempt in range(3):
        resp = session.request(method, url, **kwargs)
        if resp.status_code == 429:
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(1, reset - int(time.time()))
            print(f"Rate limited. Retrying in {wait}s …")
            time.sleep(wait)
            continue
        try:
            resp.raise_for_status()
        except HTTPError as exc:
            error = resp.json().get("error", str(exc))
            raise RuntimeError(f"API error {resp.status_code}: {error}") from exc
        return resp
    raise RuntimeError("Max retries exceeded")
```
