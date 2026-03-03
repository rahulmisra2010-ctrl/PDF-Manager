import os
import uuid
from datetime import datetime
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Document, ExtractedField, AuditLog
from services.pdf_service import PDFService
from services.export_service import ExportService

pdf_bp = Blueprint('pdf', __name__, url_prefix='/documents')
pdf_service = PDFService()
export_service = ExportService()

ALLOWED_EXTENSIONS = {'pdf'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def log_action(user_id, action, resource_type, resource_id=None, details=None):
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        details=details,
        timestamp=datetime.utcnow()
    )
    db.session.add(entry)
    db.session.commit()


@pdf_bp.route('/')
@login_required
def list_documents():
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    if current_user.role == 'Admin':
        query = Document.query
    else:
        query = Document.query.filter_by(user_id=current_user.id)
    if status_filter:
        query = query.filter_by(status=status_filter)
    pagination = query.order_by(Document.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('documents/list.html', pagination=pagination, status_filter=status_filter)


@pdf_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if current_user.role == 'Viewer':
        flash('You do not have permission to upload documents.', 'danger')
        return redirect(url_for('pdf.list_documents'))
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)
        if not allowed_file(file.filename):
            flash('Only PDF files are allowed.', 'danger')
            return redirect(request.url)
        filename = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4()}_{filename}"
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, unique_name)
        file.save(file_path)
        file_size = os.path.getsize(file_path)
        doc = Document(
            user_id=current_user.id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            status='uploaded'
        )
        db.session.add(doc)
        db.session.commit()
        log_action(current_user.id, 'upload', 'Document', doc.id, f'Uploaded {filename}')
        # Auto-extract
        try:
            _extract_document(doc)
            flash(f'"{filename}" uploaded and extracted successfully.', 'success')
        except Exception as e:
            current_app.logger.error(f'Extraction failed for {filename}: {e}')
            flash('Uploaded but text extraction failed. You can still view the document.', 'warning')
        return redirect(url_for('pdf.detail', doc_id=doc.id))
    return render_template('documents/upload.html')


def _extract_document(doc):
    text, fields_data, page_count = pdf_service.extract(doc.file_path)
    doc.page_count = page_count
    doc.status = 'extracted'
    # Remove existing fields
    ExtractedField.query.filter_by(document_id=doc.id).delete()
    for fd in fields_data:
        field = ExtractedField(
            document_id=doc.id,
            field_name=fd['field_name'],
            field_value=fd['field_value'],
            confidence=fd['confidence'],
            page_number=fd.get('page_number', 1),
            bbox_json=str(fd.get('bbox', {}))
        )
        db.session.add(field)
    db.session.commit()


@pdf_bp.route('/<int:doc_id>')
@login_required
def detail(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if current_user.role != 'Admin' and doc.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('pdf.list_documents'))
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    return render_template('documents/detail.html', doc=doc, fields=fields)


@pdf_bp.route('/<int:doc_id>/edit', methods=['POST'])
@login_required
def edit_fields(doc_id):
    if current_user.role == 'Viewer':
        flash('Access denied.', 'danger')
        return redirect(url_for('pdf.detail', doc_id=doc_id))
    doc = Document.query.get_or_404(doc_id)
    if current_user.role != 'Admin' and doc.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('pdf.list_documents'))
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    for field in fields:
        new_value = request.form.get(f'field_{field.id}', field.field_value)
        if new_value != field.field_value:
            field.field_value = new_value
            field.is_edited = True
            field.updated_at = datetime.utcnow()
    doc.status = 'extracted'
    doc.updated_at = datetime.utcnow()
    db.session.commit()
    log_action(current_user.id, 'edit_fields', 'Document', doc_id, f'Edited fields for doc {doc_id}')
    flash('Fields updated successfully.', 'success')
    return redirect(url_for('pdf.detail', doc_id=doc_id))


@pdf_bp.route('/<int:doc_id>/approve', methods=['POST'])
@login_required
def approve(doc_id):
    if current_user.role not in ('Admin', 'Verifier'):
        flash('Access denied.', 'danger')
        return redirect(url_for('pdf.detail', doc_id=doc_id))
    doc = Document.query.get_or_404(doc_id)
    doc.status = 'approved'
    doc.updated_at = datetime.utcnow()
    ExtractedField.query.filter_by(document_id=doc_id).update({'is_approved': True})
    db.session.commit()
    log_action(current_user.id, 'approve', 'Document', doc_id, f'Approved doc {doc_id}')
    flash('Document approved.', 'success')
    return redirect(url_for('pdf.detail', doc_id=doc_id))


@pdf_bp.route('/<int:doc_id>/reject', methods=['POST'])
@login_required
def reject(doc_id):
    if current_user.role not in ('Admin', 'Verifier'):
        flash('Access denied.', 'danger')
        return redirect(url_for('pdf.detail', doc_id=doc_id))
    doc = Document.query.get_or_404(doc_id)
    doc.status = 'rejected'
    doc.updated_at = datetime.utcnow()
    db.session.commit()
    log_action(current_user.id, 'reject', 'Document', doc_id, f'Rejected doc {doc_id}')
    flash('Document rejected.', 'warning')
    return redirect(url_for('pdf.detail', doc_id=doc_id))


@pdf_bp.route('/<int:doc_id>/export/<fmt>')
@login_required
def export(doc_id, fmt):
    if fmt not in ('csv', 'xlsx', 'json'):
        flash('Invalid export format.', 'danger')
        return redirect(url_for('pdf.detail', doc_id=doc_id))
    doc = Document.query.get_or_404(doc_id)
    fields = ExtractedField.query.filter_by(document_id=doc_id).all()
    export_folder = current_app.config['EXPORT_FOLDER']
    os.makedirs(export_folder, exist_ok=True)
    file_path = export_service.export(doc, fields, fmt, export_folder)
    log_action(current_user.id, 'export', 'Document', doc_id, f'Exported doc {doc_id} as {fmt}')
    return send_file(file_path, as_attachment=True, download_name=f'{doc.filename}_{doc_id}.{fmt}')


@pdf_bp.route('/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete(doc_id):
    if current_user.role not in ('Admin',):
        flash('Access denied.', 'danger')
        return redirect(url_for('pdf.detail', doc_id=doc_id))
    doc = Document.query.get_or_404(doc_id)
    try:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except Exception:
        pass
    db.session.delete(doc)
    db.session.commit()
    log_action(current_user.id, 'delete', 'Document', doc_id, f'Deleted doc {doc_id}')
    flash('Document deleted.', 'success')
    return redirect(url_for('pdf.list_documents'))
