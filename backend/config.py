"""
Configuration management for PDF-Manager
"""

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

    # CORS
    ALLOWED_ORIGINS: list = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Database
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", "sqlite:///instance/pdf_manager.db"
    )

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

