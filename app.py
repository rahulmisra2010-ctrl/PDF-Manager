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
* Centralised error handling (400 / 404 / 500) with JSON responses
* Rate limiting via Flask-Limiter (5 req/min uploads, 10 req/min others)
* Request / response logging with timestamps and duration
* CORS support (configurable via ALLOWED_ORIGINS env var)
* SQLAlchemy connection pool tuned for production

Usage
-----
    # Development
    python app.py

    # Production (gunicorn)
    gunicorn -w 4 "app:create_app()"
"""

import logging
import os
import secrets
import sys
import time
import traceback

from flask import Flask, g, json, jsonify, redirect, request, url_for
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user
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

from logging_config import setup_logging  # noqa: E402
from models import User, db, bcrypt  # noqa: E402

# ---------------------------------------------------------------------------
# Logging — set up once, before the app factory runs
# ---------------------------------------------------------------------------
setup_logging()
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_origins(raw: str) -> list[str]:
    """Parse *raw* into a list of allowed CORS origin strings.

    Accepts either a JSON array (``'["http://a.com","http://b.com"]'``) or a
    comma-separated string (``"http://a.com,http://b.com"``).
    """
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except (ValueError, TypeError):
        pass
    return [o.strip() for o in raw.split(",") if o.strip()]


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

    # SQLAlchemy connection pool settings (production-ready defaults)
    # Pool size / recycle options only apply to non-SQLite databases.
    _db_url = os.environ.get("DATABASE_URL", _default_db)
    _is_sqlite = _db_url.startswith("sqlite")
    if not _is_sqlite:
        app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {
            "pool_size": int(os.environ.get("SQLALCHEMY_POOL_SIZE", "20")),
            "pool_recycle": int(os.environ.get("SQLALCHEMY_POOL_RECYCLE", "3600")),
            "pool_pre_ping": os.environ.get("SQLALCHEMY_POOL_PRE_PING", "true").lower() == "true",
        })
    else:
        # For SQLite, only pool_pre_ping is meaningful
        app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {
            "pool_pre_ping": True,
        })

    if config:
        app.config.update(config)

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    CORS(
        app,
        origins=_parse_origins(os.environ.get("ALLOWED_ORIGINS", "")),
        supports_credentials=True,
        max_age=600,
    )

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=["10 per minute"],
        storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
    )
    app.extensions["limiter"] = limiter

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
    # Request / response logging
    # ------------------------------------------------------------------
    @app.before_request
    def _log_request_start():  # noqa: WPS430
        g.request_start_time = time.monotonic()

    @app.after_request
    def _log_request_end(response):  # noqa: WPS430
        elapsed_ms = (
            (time.monotonic() - g.request_start_time) * 1000
            if hasattr(g, "request_start_time")
            else -1
        )
        user_info = (
            current_user.username
            if current_user and current_user.is_authenticated
            else "anonymous"
        )
        _logger.info(
            "%s %s %s %.1fms user=%s",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
            user_info,
        )
        return response

    # ------------------------------------------------------------------
    # Error handlers
    # ------------------------------------------------------------------
    @app.errorhandler(400)
    def bad_request(exc):  # noqa: WPS430
        _logger.warning("400 Bad Request: %s %s — %s", request.method, request.path, exc)
        return jsonify(error="Bad Request", message=str(exc)), 400

    @app.errorhandler(404)
    def not_found(exc):  # noqa: WPS430
        _logger.info("404 Not Found: %s %s", request.method, request.path)
        return jsonify(error="Not Found", message=str(exc)), 404

    @app.errorhandler(429)
    def rate_limit_exceeded(exc):  # noqa: WPS430
        _logger.warning(
            "429 Rate limit exceeded: %s %s — %s", request.method, request.path, exc
        )
        return (
            jsonify(
                error="Too Many Requests",
                message="Rate limit exceeded. Please slow down and try again later.",
            ),
            429,
        )

    @app.errorhandler(500)
    def internal_error(exc):  # noqa: WPS430
        _logger.error(
            "500 Internal Server Error: %s %s\n%s",
            request.method,
            request.path,
            traceback.format_exc(),
        )
        return jsonify(error="Internal Server Error", message="An unexpected error occurred."), 500

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

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(pdf_bp, url_prefix="/pdf")
    app.register_blueprint(ai_pdf_bp, url_prefix="/ai-pdf")
    app.register_blueprint(pdf_editor_bp, url_prefix="/live-pdf")
    app.register_blueprint(address_book_bp, url_prefix="/address-book")
    app.register_blueprint(address_book_live_bp, url_prefix="/address-book-live")
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(search_bp, url_prefix="/search")
    app.register_blueprint(users_bp, url_prefix="/users")

    # REST API v1 — apply tighter rate limits to upload/extract endpoints
    try:
        from backend.api.routes import api_v1_bp
        app.register_blueprint(api_v1_bp)

        # Apply upload / extract rate limits (5/min) after blueprint registration
        for _endpoint in ("api_v1.upload_pdf", "api_v1.extract_ocr", "api_v1.extract_ai"):
            view_func = app.view_functions.get(_endpoint)
            if view_func:
                limiter.limit("5 per minute")(view_func)
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
