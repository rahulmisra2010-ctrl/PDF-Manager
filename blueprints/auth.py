"""
blueprints/auth.py — Authentication blueprint.

Routes
------
GET  /auth/login   — render login form
POST /auth/login   — validate credentials and start session
GET  /auth/logout  — destroy session and redirect to login
"""

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from models import AuditLog, User, db

auth_bp = Blueprint("auth", __name__, template_folder="../templates/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Render and process the login form."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            login_user(user, remember=bool(request.form.get("remember")))
            _log(user.id, "login", "user", str(user.id))
            next_page = request.args.get("next") or url_for("dashboard.index")
            return redirect(next_page)

        flash("Invalid username or password.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """End the current user session."""
    _log(current_user.id, "logout", "user", str(current_user.id))
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(user_id: int, action: str, resource_type: str, resource_id: str) -> None:
    """Insert an AuditLog entry."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    db.session.add(entry)
    db.session.commit()
