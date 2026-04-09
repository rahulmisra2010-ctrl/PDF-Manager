# Code Style Guide

## Python

PDF Manager follows [PEP 8](https://peps.python.org/pep-0008/) with these specifics:

- **Line length:** 100 characters
- **Quotes:** Double quotes for strings
- **Imports:** Ordered: standard library → third-party → local, separated by blank lines
- **Type hints:** Required for all public function signatures
- **Docstrings:** Google-style for classes and public methods

### Linting

```bash
# Install linters
pip install flake8 black isort

# Check
flake8 backend/ --max-line-length=100
black --check backend/
isort --check-only backend/

# Auto-format
black backend/
isort backend/
```

### Example

```python
from __future__ import annotations

import os
from typing import Optional

from flask import Flask

from backend.models import Document


class DocumentService:
    """Service for managing PDF documents."""

    def get_by_id(self, document_id: int) -> Optional[Document]:
        """Retrieve a document by its primary key.

        Args:
            document_id: The document's database ID.

        Returns:
            The Document instance, or None if not found.
        """
        return Document.query.get(document_id)
```

## JavaScript / React

Frontend code follows the [Airbnb JavaScript Style Guide](https://github.com/airbnb/javascript):

- **Quotes:** Single quotes
- **Semicolons:** Required
- **Arrow functions:** Preferred for callbacks
- **Component files:** One component per file, named with PascalCase

### Linting

```bash
cd frontend
npm run lint        # ESLint check
npm run lint --fix  # Auto-fix
```

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add confidence heatmap endpoint
fix: handle empty PDF gracefully
docs: update API extraction examples
refactor: extract OCR engine base class
test: add upload endpoint tests
chore: update dependencies
```

Format: `<type>(<optional scope>): <short description>`

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## SQL

- Table names: snake_case, plural (`extracted_fields`, `field_edit_history`)
- Column names: snake_case
- All tables must have a `created_at TIMESTAMP` column
- Use `BIGSERIAL` for primary keys in PostgreSQL
