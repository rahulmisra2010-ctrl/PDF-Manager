"""
PDF-Manager — Production Flask Configuration
Loaded by app.py when FLASK_ENV=production.
"""
import os


class ProductionConfig:
    # -------------------------------------------------------------------------
    # Core
    # -------------------------------------------------------------------------
    ENV = "production"
    DEBUG = False
    TESTING = False

    SECRET_KEY = os.environ["SECRET_KEY"]   # must be set — fail fast if missing

    # -------------------------------------------------------------------------
    # Security
    # -------------------------------------------------------------------------
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    WTF_CSRF_ENABLED = True
    # Trust X-Forwarded-For from Nginx (set to the count of proxies in front)
    PREFERRED_URL_SCHEME = "https"

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///instance/pdf_manager.db",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10,
        "max_overflow": 20,
    }

    # -------------------------------------------------------------------------
    # File storage
    # -------------------------------------------------------------------------
    UPLOAD_FOLDER = os.environ.get("UPLOAD_DIR", "/app/uploads")
    EXPORT_FOLDER = os.environ.get("EXPORT_DIR", "/app/exports")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_SIZE_MB", 100)) * 1024 * 1024

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    LOG_LEVEL = "WARNING"
    LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")

    # -------------------------------------------------------------------------
    # Cache / Redis
    # -------------------------------------------------------------------------
    REDIS_URL = os.environ.get("REDIS_URL", "")
    CACHE_TYPE = "RedisCache" if REDIS_URL else "SimpleCache"
    CACHE_REDIS_URL = REDIS_URL
    CACHE_DEFAULT_TIMEOUT = 300

    # -------------------------------------------------------------------------
    # Feature flags
    # -------------------------------------------------------------------------
    FEATURE_OCR = os.environ.get("FEATURE_OCR", "true").lower() == "true"
    FEATURE_AI_EXTRACTION = (
        os.environ.get("FEATURE_AI_EXTRACTION", "true").lower() == "true"
    )
    FEATURE_RAG = os.environ.get("FEATURE_RAG", "false").lower() == "true"

    # -------------------------------------------------------------------------
    # ML / AI
    # -------------------------------------------------------------------------
    ML_MODEL_DIR = os.environ.get("ML_MODEL_DIR", "/app/models")
    ML_CONFIDENCE_THRESHOLD = float(
        os.environ.get("ML_CONFIDENCE_THRESHOLD", 0.75)
    )
    USE_GPU = os.environ.get("USE_GPU", "false").lower() == "true"

    # -------------------------------------------------------------------------
    # Email / SMTP
    # -------------------------------------------------------------------------
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "")
