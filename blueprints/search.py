"""
blueprints/search.py — Full-text search blueprint.

Routes
------
GET /search/?q=...&status=...&field=...  — search results page
GET /search/api?q=...                   — JSON search endpoint
"""

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from sqlalchemy import or_

from models import Document, ExtractedField

search_bp = Blueprint("search", __name__, template_folder="../templates/search")


def _run_search(query: str, status: str = "", field_name: str = ""):
    """
    Search documents and their extracted fields.

    Args:
        query:      Free-text search term.
        status:     Optional status filter.
        field_name: Optional field-name filter.

    Returns:
        List of matching Document objects.
    """
    q = query.strip()

    # Base queryset
    doc_query = Document.query

    if status:
        doc_query = doc_query.filter(Document.status == status)

    if q:
        # Match on filename
        filename_matches = doc_query.filter(
            Document.filename.ilike(f"%{q}%")
        )

        # Match on field values
        field_doc_ids = (
            ExtractedField.query.filter(
                or_(
                    ExtractedField.field_name.ilike(f"%{q}%"),
                    ExtractedField.value.ilike(f"%{q}%"),
                )
            )
            .with_entities(ExtractedField.document_id)
            .distinct()
        )
        if field_name:
            field_doc_ids = field_doc_ids.filter(
                ExtractedField.field_name.ilike(f"%{field_name}%")
            )

        field_matches = doc_query.filter(
            Document.id.in_(field_doc_ids)
        )

        # Union — collect unique docs preserving order
        seen_ids: set[int] = set()
        results: list[Document] = []
        for doc in list(filename_matches) + list(field_matches):
            if doc.id not in seen_ids:
                seen_ids.add(doc.id)
                results.append(doc)
        return results

    return doc_query.order_by(Document.created_at.desc()).all()


@search_bp.route("/")
@login_required
def results():
    """Render the search results page."""
    query = request.args.get("q", "")
    status = request.args.get("status", "")
    field_name = request.args.get("field", "")
    documents = _run_search(query, status, field_name)
    return render_template(
        "search/results.html",
        documents=documents,
        query=query,
        status=status,
        field_name=field_name,
    )


@search_bp.route("/api")
@login_required
def api_search():
    """Return search results as JSON."""
    query = request.args.get("q", "")
    status = request.args.get("status", "")
    field_name = request.args.get("field", "")
    documents = _run_search(query, status, field_name)
    return jsonify(
        [
            {
                "id": doc.id,
                "filename": doc.filename,
                "status": doc.status,
                "created_at": doc.created_at.isoformat(),
            }
            for doc in documents
        ]
    )
