"""
blueprints/dashboard.py — Dashboard blueprint.

Routes
------
GET  /          — main dashboard with stats cards and charts
GET  /api/stats — JSON stats endpoint consumed by Chart.js
"""

from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from models import AuditLog, Document, ExtractedField, User, db

dashboard_bp = Blueprint("dashboard", __name__, template_folder="../templates/dashboard")


@dashboard_bp.route("/")
@login_required
def index():
    """Render the main dashboard."""
    return render_template("dashboard/index.html")


@dashboard_bp.route("/api/stats")
@login_required
def stats():
    """Return aggregate statistics as JSON for Chart.js consumption."""
    total_docs = Document.query.count()
    status_counts: dict[str, int] = {}
    for status in Document.STATUSES:
        status_counts[status] = Document.query.filter_by(status=status).count()

    total_fields = ExtractedField.query.count()
    total_users = User.query.count()

    # Recent activity — last 10 audit log entries
    recent = (
        AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
    )
    recent_activity = [
        {
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "timestamp": entry.timestamp.isoformat(),
        }
        for entry in recent
    ]

    return jsonify(
        {
            "total_documents": total_docs,
            "status_counts": status_counts,
            "total_fields": total_fields,
            "total_users": total_users,
            "recent_activity": recent_activity,
        }
    )
