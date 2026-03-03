from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from models import db, Document, ExtractedField

search_bp = Blueprint('search', __name__)


@search_bp.route('/search')
@login_required
def search():
    query_str = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    field_filter = request.args.get('field_name', '')
    page = request.args.get('page', 1, type=int)

    pagination = None
    if query_str:
        if current_user.role == 'Admin':
            doc_query = Document.query
        else:
            doc_query = Document.query.filter_by(user_id=current_user.id)

        if status_filter:
            doc_query = doc_query.filter_by(status=status_filter)

        doc_results = doc_query.filter(Document.filename.ilike(f'%{query_str}%')).all()
        doc_ids_from_name = {d.id for d in doc_results}

        field_query = ExtractedField.query.filter(
            ExtractedField.field_value.ilike(f'%{query_str}%')
        )
        if field_filter:
            field_query = field_query.filter_by(field_name=field_filter)

        field_results = field_query.all()
        doc_ids_from_fields = {f.document_id for f in field_results}

        all_doc_ids = doc_ids_from_name | doc_ids_from_fields

        if current_user.role == 'Admin':
            final_docs = Document.query.filter(Document.id.in_(all_doc_ids))
        else:
            final_docs = Document.query.filter(
                Document.id.in_(all_doc_ids),
                Document.user_id == current_user.id
            )
        if status_filter:
            final_docs = final_docs.filter_by(status=status_filter)

        pagination = final_docs.order_by(Document.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    field_names = db.session.query(ExtractedField.field_name).distinct().all()
    field_names = [f[0] for f in field_names]

    return render_template('search.html',
        query=query_str,
        pagination=pagination,
        status_filter=status_filter,
        field_filter=field_filter,
        field_names=field_names
    )
