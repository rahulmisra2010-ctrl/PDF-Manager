"""
blueprints/users.py — User management blueprint (Admin only).

Routes
------
GET  /users/              — paginated user list
POST /users/create        — create a new user
POST /users/<id>/toggle   — activate / deactivate a user
POST /users/<id>/role     — change a user's role
GET  /users/audit         — paginated audit log
"""

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from models import AuditLog, User, db

users_bp = Blueprint("users", __name__, template_folder="../templates/users")

_PAGE_SIZE = 20


def _admin_required(f):
    """Decorator: abort 403 for non-Admin users."""
    from functools import wraps

    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "Admin":
            abort(403)
        return f(*args, **kwargs)

    return wrapped


@users_bp.route("/")
@login_required
@_admin_required
def list_users():
    """Show a paginated list of all users."""
    page = request.args.get("page", 1, type=int)
    pagination = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=_PAGE_SIZE, error_out=False
    )
    return render_template("users/list.html", pagination=pagination)


@users_bp.route("/create", methods=["POST"])
@login_required
@_admin_required
def create_user():
    """Create a new user account."""
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "Viewer")

    if not username or not email or not password:
        flash("Username, email, and password are required.", "danger")
        return redirect(url_for("users.list_users"))

    if role not in User.ROLES:
        flash("Invalid role.", "danger")
        return redirect(url_for("users.list_users"))

    if User.query.filter(
        (User.username == username) | (User.email == email)
    ).first():
        flash("A user with that username or email already exists.", "danger")
        return redirect(url_for("users.list_users"))

    try:
        new_user = User(username=username, email=email, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.flush()
        _log(current_user.id, "create_user", "user", str(new_user.id), username)
        db.session.commit()
        flash(f"User '{username}' created.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")

    return redirect(url_for("users.list_users"))


@users_bp.route("/<int:user_id>/toggle", methods=["POST"])
@login_required
@_admin_required
def toggle_user(user_id: int):
    """Activate or deactivate a user account."""
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("users.list_users"))

    user.is_active = not user.is_active
    action = "activate_user" if user.is_active else "deactivate_user"
    _log(current_user.id, action, "user", str(user_id))
    db.session.commit()
    state = "activated" if user.is_active else "deactivated"
    flash(f"User '{user.username}' {state}.", "success")
    return redirect(url_for("users.list_users"))


@users_bp.route("/<int:user_id>/role", methods=["POST"])
@login_required
@_admin_required
def change_role(user_id: int):
    """Change a user's role."""
    user = User.query.get_or_404(user_id)
    new_role = request.form.get("role", "")
    if new_role not in User.ROLES:
        flash("Invalid role.", "danger")
        return redirect(url_for("users.list_users"))

    user.role = new_role
    _log(current_user.id, "change_role", "user", str(user_id), new_role)
    db.session.commit()
    flash(f"Role updated to '{new_role}' for '{user.username}'.", "success")
    return redirect(url_for("users.list_users"))


@users_bp.route("/audit")
@login_required
@_admin_required
def audit_log():
    """Show a paginated audit log."""
    page = request.args.get("page", 1, type=int)
    pagination = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=_PAGE_SIZE, error_out=False
    )
    return render_template("users/audit_log.html", pagination=pagination)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(user_id: int, action: str, resource_type: str, resource_id: str,
         details: str = "") -> None:
    """Insert an AuditLog entry (caller must commit)."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or None,
    )
    db.session.add(entry)
