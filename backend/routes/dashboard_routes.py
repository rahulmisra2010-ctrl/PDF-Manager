from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from models import db, Document, ExtractedField, AuditLog, User
from datetime import datetime, timedelta
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def index():
    if current_user.role == 'Admin':
        total_docs = Document.query.count()
        status_counts = db.session.query(Document.status, func.count(Document.id)).group_by(Document.status).all()
        recent_docs = Document.query.order_by(Document.created_at.desc()).limit(5).all()
    else:
        total_docs = Document.query.filter_by(user_id=current_user.id).count()
        status_counts = db.session.query(Document.status, func.count(Document.id)).filter_by(user_id=current_user.id).group_by(Document.status).all()
        recent_docs = Document.query.filter_by(user_id=current_user.id).order_by(Document.created_at.desc()).limit(5).all()

    total_fields = ExtractedField.query.count()
    total_users = User.query.count()

    status_dict = dict(status_counts)
    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()

    return render_template('dashboard.html',
        total_docs=total_docs,
        total_fields=total_fields,
        total_users=total_users,
        status_dict=status_dict,
        recent_docs=recent_docs,
        recent_logs=recent_logs
    )


@dashboard_bp.route('/api/stats')
@login_required
def stats_api():
    days = []
    counts = []
    for i in range(6, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        count = Document.query.filter(
            func.date(Document.created_at) == day
        ).count()
        days.append(day.strftime('%b %d'))
        counts.append(count)

    status_counts = db.session.query(Document.status, func.count(Document.id)).group_by(Document.status).all()

    return jsonify({
        'days': days,
        'counts': counts,
        'status_labels': [s[0] for s in status_counts],
        'status_values': [s[1] for s in status_counts],
    })
