# Python SDK

A thin wrapper around the `requests` library for the PDF Manager API.

## Installation

The SDK is not yet published to PyPI. Copy the class below into your project or install from source.

```bash
# Future installation (planned)
pip install pdf-manager-sdk
```

---

## Quick Start

```python
from pdf_manager_sdk import PDFManagerClient

client = PDFManagerClient(
    base_url="http://localhost:5000",
    username="admin",
    password="yourpassword",
)

# Upload a PDF
doc = client.upload("invoice.pdf")
print(f"Uploaded: {doc['document_id']}")

# Extract data
extraction = client.extract_ai(doc["document_id"])
for field in extraction["fields"]:
    print(f"  {field['field_name']}: {field['value']}")

# Update a field
fields = client.get_fields(doc["document_id"])
client.update_field(fields[0]["id"], "corrected value")

# Delete the document
client.delete_document(doc["document_id"])
```

---

## SDK Source

Save this as `pdf_manager_sdk.py` in your project:

```python
"""pdf_manager_sdk.py — Python SDK for the PDF Manager REST API."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests


class PDFManagerClient:
    """Simple SDK for the PDF Manager REST API."""

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        username: str | None = None,
        password: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self._session = requests.Session()
        if username and password:
            self.login(username, password)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> None:
        """Authenticate and store the session cookie."""
        resp = self._session.post(
            f"{self.base_url}/auth/login",
            data={"username": username, "password": password},
        )
        resp.raise_for_status()

    def logout(self) -> None:
        """End the current session."""
        self._request("GET", "/auth/logout")

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def upload(self, file_path: str | Path) -> dict[str, Any]:
        """Upload a PDF file. Returns the upload response dict."""
        path = Path(file_path)
        with path.open("rb") as f:
            resp = self._session.post(
                f"{self.base_url}/api/v1/upload",
                files={"file": (path.name, f, "application/pdf")},
            )
        return self._handle(resp)

    def list_documents(self, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        """Return a paginated list of documents."""
        return self._request("GET", "/api/v1/documents", params={
            "page": page, "per_page": per_page
        })

    def get_document(self, document_id: int | str) -> dict[str, Any]:
        """Return metadata for a single document."""
        return self._request("GET", f"/api/v1/documents/{document_id}")

    def delete_document(self, document_id: int | str) -> dict[str, Any]:
        """Delete a document and its file."""
        return self._request("DELETE", f"/api/v1/documents/{document_id}")

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def extract_ocr(self, document_id: int | str) -> dict[str, Any]:
        """Run OCR extraction on a document."""
        return self._request("POST", f"/api/v1/extract/ocr/{document_id}")

    def extract_ai(
        self,
        document_id: int | str,
        run_rag: bool = True,
        include_images: bool = False,
    ) -> dict[str, Any]:
        """Run AI + RAG extraction on a document."""
        params = {"include_images": "true" if include_images else "false"}
        return self._request(
            "POST",
            f"/api/v1/extract/ai/{document_id}",
            json={"run_rag": run_rag},
            params=params,
        )

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    def get_fields(self, document_id: int | str) -> list[dict[str, Any]]:
        """Return all extracted fields for a document."""
        return self._request("GET", f"/api/v1/fields/{document_id}")

    def update_field(self, field_id: int, value: str) -> dict[str, Any]:
        """Update the value of a field."""
        return self._request("PUT", f"/api/v1/fields/{field_id}", json={"value": value})

    def get_field_history(self, field_id: int) -> list[dict[str, Any]]:
        """Return edit history for a field."""
        return self._request("GET", f"/api/v1/fields/{field_id}/history")

    # ------------------------------------------------------------------
    # Stats & Search
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return dashboard statistics."""
        return self._request("GET", "/api/stats")

    def search(self, query: str) -> dict[str, Any]:
        """Search documents and fields."""
        return self._request("GET", "/search/api", params={"q": query})

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        for attempt in range(self.max_retries):
            resp = self._session.request(method, url, **kwargs)
            if resp.status_code == 429:
                reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(1, reset - int(time.time()))
                time.sleep(wait)
                continue
            return self._handle(resp)
        raise RuntimeError("Max retries exceeded")

    @staticmethod
    def _handle(resp: requests.Response) -> Any:
        if not resp.ok:
            try:
                error = resp.json().get("error", resp.text)
            except Exception:
                error = resp.text
            raise RuntimeError(f"API {resp.status_code}: {error}")
        try:
            return resp.json()
        except Exception:
            return resp.content
```

---

## API Reference

### `PDFManagerClient(base_url, username, password, max_retries)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | str | `http://localhost:5000` | API server URL |
| `username` | str\|None | None | Auto-login username |
| `password` | str\|None | None | Auto-login password |
| `max_retries` | int | 3 | Retries on 429 rate limit |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `login(username, password)` | None | Authenticate |
| `logout()` | None | End session |
| `upload(file_path)` | dict | Upload PDF |
| `list_documents(page, per_page)` | dict | List documents |
| `get_document(document_id)` | dict | Get document metadata |
| `delete_document(document_id)` | dict | Delete document |
| `extract_ocr(document_id)` | dict | OCR extraction |
| `extract_ai(document_id, run_rag, include_images)` | dict | AI extraction |
| `get_fields(document_id)` | list | Get extracted fields |
| `update_field(field_id, value)` | dict | Update field value |
| `get_field_history(field_id)` | list | Get field edit history |
| `get_stats()` | dict | Dashboard statistics |
| `search(query)` | dict | Search documents/fields |
