"""
Configuration management for PDF-Manager
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "PDF-Manager API"
    API_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Database
    DATABASE_URL: str = "postgresql://pdfmanager:pdfmanager@localhost:5432/pdfmanager"

    # File storage
    UPLOAD_DIR: str = "uploads"
    EXPORT_DIR: str = "exports"
    MAX_UPLOAD_SIZE_MB: int = 50

    # ML/PyTorch settings
    ML_MODEL_DIR: str = "models"
    ML_CONFIDENCE_THRESHOLD: float = 0.75
    USE_GPU: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
