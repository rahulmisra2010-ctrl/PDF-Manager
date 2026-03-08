# Testing Guidelines

## Backend Tests

Backend tests use `pytest`. Run from the repository root:

```bash
# Activate virtual environment first
source .venv/bin/activate

# Run all backend tests
cd backend && pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_ocr.py

# Run with coverage
pytest --cov=backend --cov-report=html
```

## Test Configuration

The Flask app is tested with an in-memory SQLite database:

```python
from app import create_app

app = create_app({
    "TESTING": True,
    "WTF_CSRF_ENABLED": False,
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    "ADMIN_PASSWORD": "testpass123",
})
```

## Writing Backend Tests

Place tests in `backend/tests/` or the top-level `tests/` directory:

```python
import pytest
from app import create_app

@pytest.fixture()
def client():
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "ADMIN_PASSWORD": "testpass",
    })
    with app.test_client() as client:
        with app.app_context():
            yield client

def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"

def test_upload_no_file(client):
    resp = client.post("/api/v1/upload")
    assert resp.status_code == 400
```

## Frontend Tests

Frontend tests use Jest and React Testing Library:

```bash
cd frontend
npm test

# Run once (CI mode)
npm test -- --watchAll=false

# Coverage
npm test -- --coverage --watchAll=false
```

## What to Test

| Layer | Test Focus |
|-------|-----------|
| API routes | HTTP status codes, response structure, error handling |
| Services | Business logic, edge cases, exception handling |
| OCR engines | Engine availability fallback, confidence scoring |
| React components | Rendering, user interactions, API calls (mocked) |

## Mocking External Services

OCR engines (EasyOCR, PaddleOCR) can be slow to load. Mock them in unit tests:

```python
from unittest.mock import patch

@patch("backend.ocr.ocr_engine.EasyOCR.run", return_value=[])
def test_ocr_fallback(mock_easyocr, client):
    # EasyOCR returns empty; ensure Tesseract fallback works
    ...
```

## CI

Tests run automatically via GitHub Actions on every push and pull request. See `.github/workflows/` for the workflow definitions.
