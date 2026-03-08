# Development Guide

## Local Setup (without Docker)

### Prerequisites

- Python 3.11 or later
- Node.js 18 or later
- Tesseract OCR (`sudo apt-get install tesseract-ocr` on Debian/Ubuntu)

### Backend

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Copy environment variables
cp .env.example .env

# Run the Flask development server
python app.py
```

### Frontend

```bash
cd frontend
npm install
npm start
```

## Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests with coverage
pytest
```

Coverage reports are written to `coverage.xml` (for Codecov) and printed to the terminal.

## Code Style

This project uses the following tools (configured in `pyproject.toml`):

| Tool | Purpose |
|------|---------|
| **black** | Opinionated code formatter (line length 88) |
| **isort** | Import order (black-compatible profile) |
| **flake8** | Linting (E9, F-series errors enforced; style warnings optional) |

Run all checks locally:

```bash
pip install black isort flake8
black --check .
isort --check-only .
flake8 .
```

## CI/CD Overview

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | push/PR to main, develop | Lint, test (3.11–3.13), Docker build |
| `lint.yml` | push/PR to main, develop | Dedicated lint job |
| `codeql.yml` | push to main, weekly | Security analysis, pip-audit |
| `docker.yml` | push to main, release | Multi-arch Docker build & push |
| `docs.yml` | push to main, manual | Build & deploy MkDocs to GitHub Pages |
| `release.yml` | release created | Changelog, Docker tags, optional PyPI publish |

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes following [Conventional Commits](https://www.conventionalcommits.org/)
4. Open a pull request against `main`

All PRs must pass the CI pipeline before merging.
