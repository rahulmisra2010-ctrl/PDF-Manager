"""
app.py — PDF-Manager Flask application factory.

Features
--------
* Blueprint registration for auth, pdf, dashboard, search, and users
* Auto-created default admin on first run (password from ADMIN_PASSWORD env var,
  or a securely generated random token printed at startup)
* SQLAlchemy with SQLite (configurable via DATABASE_URL)
* CSRF protection via Flask-WTF
* Password hashing via Flask-Bcrypt (minimum 8 characters)
* Role-based access control: Admin, Verifier, Viewer

Usage
-----
    # Development
    python app.py

    # Production (gunicorn)
    gunicorn -w 4 "app:create_app()"
"""

import os
import secrets
import sys

from flask import Flask, redirect, url_for
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Ensure backend/ is on sys.path so services can be imported, but keep root
# ahead of backend so that root-level modules (models, blueprints) take priority.
# ---------------------------------------------------------------------------
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_ROOT_DIR, "backend")

# Insert root at position 0 (highest priority)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

# Append backend after root so services/ and config are importable
if _BACKEND_DIR not in sys.path:
    sys.path.append(_BACKEND_DIR)

# Load environment variables from both the repository root and backend/
# to stay compatible with earlier setup instructions.
for _env_file in (os.path.join(_ROOT_DIR, ".env"), os.path.join(_BACKEND_DIR, ".env")):
    load_dotenv(_env_file)

from models import User, db, bcrypt  # noqa: E402


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config: dict | None = None) -> Flask:
    """
    Create and configure the Flask application.

    Args:
        config: Optional mapping of configuration overrides (useful for tests).

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "")
    if not app.config["SECRET_KEY"]:
        import warnings
        _generated_key = secrets.token_hex(32)
        app.config["SECRET_KEY"] = _generated_key
        warnings.warn(
            "SECRET_KEY is not set — a random key was generated. "
            "All sessions and CSRF tokens will be invalidated on restart. "
            "Set the SECRET_KEY environment variable in production.",
            stacklevel=2,
        )

    # Build a default absolute SQLite URL so the db file is always
    # created next to the application, regardless of the working directory.
    _default_db = f"sqlite:///{os.path.join(_ROOT_DIR, 'instance', 'pdf_manager.db')}"
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", _default_db)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_DIR", "uploads")
    app.config["EXPORT_FOLDER"] = os.environ.get("EXPORT_DIR", "exports")
    app.config["MAX_CONTENT_LENGTH"] = (
        int(os.environ.get("MAX_UPLOAD_SIZE_MB", 50)) * 1024 * 1024
    )
    app.config["WTF_CSRF_ENABLED"] = True

    if config:
        app.config.update(config)

    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    db.init_app(app)
    bcrypt.init_app(app)
    CSRFProtect(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id: str):  # noqa: WPS430
        return User.query.get(int(user_id))

    # ------------------------------------------------------------------
    # Blueprints
    # ------------------------------------------------------------------
    from blueprints.auth import auth_bp
    from blueprints.pdf import pdf_bp
    from blueprints.dashboard import dashboard_bp
    from blueprints.search import search_bp
    from blueprints.users import users_bp
    from blueprints.ai_pdf import ai_pdf_bp
    from blueprints.pdf_editor import pdf_editor_bp
    from blueprints.address_book import address_book_bp
    from blueprints.address_book_live import address_book_live_bp
    from blueprints.rag import rag_bp
    from blueprints.training import training_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(pdf_bp, url_prefix="/pdf")
    app.register_blueprint(ai_pdf_bp, url_prefix="/ai-pdf")
    app.register_blueprint(pdf_editor_bp, url_prefix="/live-pdf")
    app.register_blueprint(address_book_bp, url_prefix="/address-book")
    app.register_blueprint(address_book_live_bp, url_prefix="/address-book-live")
    app.register_blueprint(rag_bp)  # url_prefix="/api/v1" is set in the blueprint
    app.register_blueprint(training_bp)  # routes defined per-function
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(search_bp, url_prefix="/search")
    app.register_blueprint(users_bp, url_prefix="/users")

    # ------------------------------------------------------------------
    # Context processor — make training example count available in all templates
    # ------------------------------------------------------------------
    from models import TrainingExample  # noqa: E402

    @app.context_processor
    def inject_training_count():  # noqa: WPS430
        try:
            count = TrainingExample.query.count()
        except Exception:
            count = 0
        return {"training_examples_count": count}

    # REST API v1
    try:
        from backend.api.routes import api_v1_bp
        app.register_blueprint(api_v1_bp)
    except Exception as _api_exc:
        import warnings
        warnings.warn(f"Could not register API v1 blueprint: {_api_exc}", stacklevel=2)

    # Redirect root to dashboard
    @app.route("/")
    def root():  # noqa: WPS430
        return redirect(url_for("dashboard.index"))

    # ------------------------------------------------------------------
    # Database initialisation + default admin
    # ------------------------------------------------------------------
    with app.app_context():
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        os.makedirs(app.config["EXPORT_FOLDER"], exist_ok=True)
        # Ensure the SQLite instance directory exists when using a file-based DB
        db_url: str = app.config["SQLALCHEMY_DATABASE_URI"]
        if db_url.startswith("sqlite:///") and db_url != "sqlite:///:memory:":
            db_path = db_url[len("sqlite:///"):]
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
        db.create_all()
        _create_default_admin(app)

    return app


def _create_default_admin(app: Flask) -> None:
    """
    Create a default Admin user if no users exist.

    The password is taken from the ``ADMIN_PASSWORD`` key in ``app.config``
    (which falls back to the ``ADMIN_PASSWORD`` environment variable).
    If neither is set, a cryptographically secure random token is generated
    and printed to stdout so the operator can log in for the first time.
    """
    if User.query.count() > 0:
        return

    admin_password = (
        app.config.get("ADMIN_PASSWORD")
        or os.environ.get("ADMIN_PASSWORD")
        or secrets.token_urlsafe(24)
    )
    admin = User(
        username="admin",
        email="admin@pdfmanager.local",
        role="Admin",
        is_active=True,
    )
    admin.set_password(admin_password)
    db.session.add(admin)
    db.session.commit()
    if not app.config.get("TESTING"):
        print(
            f"[PDF-Manager] Default admin account created.\n"
            f"  Username : admin\n"
            f"  Password : {admin_password}\n"
            f"  Change this password after first login!",
            flush=True,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
