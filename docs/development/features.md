# Creating New Features

## Workflow Overview

1. Create a feature branch from `main`
2. Implement backend changes (model → service → API route)
3. Implement frontend changes (API call → component → UI)
4. Write tests
5. Open a pull request

## Adding a New API Endpoint

### Step 1 – Define the Route

Add your endpoint to `backend/api/routes.py`:

```python
@api_bp.route("/documents/<int:document_id>/summary", methods=["GET"])
@login_required
def get_document_summary(document_id):
    """Return a text summary of the document."""
    doc = db.session.get(Document, document_id)
    if doc is None:
        return jsonify({"error": "Document not found"}), 404

    summary = SummaryService.summarise(document_id)
    return jsonify({"document_id": document_id, "summary": summary}), 200
```

### Step 2 – Add a Service

Create `backend/services/summary_service.py`:

```python
class SummaryService:
    @staticmethod
    def summarise(document_id: int) -> str:
        # Your logic here
        return "Summary text..."
```

### Step 3 – Update the Frontend

Add an API call in `frontend/src/services/api.js`:

```javascript
export const getDocumentSummary = (documentId) =>
  fetch(`/api/v1/documents/${documentId}/summary`, { credentials: 'include' })
    .then(r => r.json());
```

Use it in a component:

```javascript
import { getDocumentSummary } from '../services/api';

const [summary, setSummary] = useState('');
useEffect(() => {
  getDocumentSummary(documentId).then(data => setSummary(data.summary));
}, [documentId]);
```

### Step 4 – Document the Endpoint

Add a new page under `docs/api/` following the pattern of existing endpoint pages.

## Adding a New OCR Engine

1. Create `backend/ocr/my_engine.py` implementing the `run(image)` method that returns `List[WordResult]`.
2. Register it in `backend/ocr/ocr_engine.py` under the engine selection logic.
3. Add an optional dependency to `backend/requirements.txt`.

## Database Schema Changes

Add migrations manually to `database/schema.sql`:

```sql
ALTER TABLE documents ADD COLUMN summary TEXT;
```

For development with SQLite, the database is recreated on startup when `DEBUG=true`.

!!! warning "No migration framework yet"
    PDF Manager currently uses raw SQL files. For production, back up the database before applying schema changes.
