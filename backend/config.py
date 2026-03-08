"""
Configuration management for PDF-Manager
"""

import json
import os


class Settings:
    """Application settings loaded from environment variables with defaults."""

    # Application
    APP_NAME: str = os.environ.get("APP_NAME", "PDF-Manager")
    API_VERSION: str = os.environ.get("API_VERSION", "1.0.0")
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"

    # Server
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", "5000"))

    # CORS — parse from JSON array or comma-separated string
    _raw_origins: str = os.environ.get(
        "ALLOWED_ORIGINS",
        '["http://localhost:3000","http://127.0.0.1:3000"]',
    )
    try:
        ALLOWED_ORIGINS: list = json.loads(_raw_origins)
    except (ValueError, TypeError):
        ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

    # Database
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", "sqlite:///instance/pdf_manager.db"
    )

    # SQLAlchemy connection pool (production-ready defaults)
    SQLALCHEMY_POOL_SIZE: int = int(os.environ.get("SQLALCHEMY_POOL_SIZE", "20"))
    SQLALCHEMY_POOL_RECYCLE: int = int(os.environ.get("SQLALCHEMY_POOL_RECYCLE", "3600"))
    SQLALCHEMY_POOL_PRE_PING: bool = (
        os.environ.get("SQLALCHEMY_POOL_PRE_PING", "true").lower() == "true"
    )
    SQLALCHEMY_ECHO: bool = os.environ.get("DEBUG", "false").lower() == "true"

    # Rate limiting
    RATELIMIT_STORAGE_URI: str = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT: str = os.environ.get("RATELIMIT_DEFAULT", "10 per minute")
    RATELIMIT_UPLOAD: str = os.environ.get("RATELIMIT_UPLOAD", "5 per minute")
    RATELIMIT_EXTRACT: str = os.environ.get("RATELIMIT_EXTRACT", "5 per minute")
    RATELIMIT_FIELDS: str = os.environ.get("RATELIMIT_FIELDS", "20 per minute")

    # File storage
    UPLOAD_DIR: str = os.environ.get("UPLOAD_DIR", "uploads")
    EXPORT_DIR: str = os.environ.get("EXPORT_DIR", "exports")
    MAX_UPLOAD_SIZE_MB: int = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "50"))

    # ML/PyTorch settings (only relevant when torch is installed)
    ML_MODEL_DIR: str = os.environ.get("ML_MODEL_DIR", "models")
    ML_CONFIDENCE_THRESHOLD: float = float(
        os.environ.get("ML_CONFIDENCE_THRESHOLD", "0.75")
    )
    USE_GPU: bool = os.environ.get("USE_GPU", "false").lower() == "true"


settings = Settings()

