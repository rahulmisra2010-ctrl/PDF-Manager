import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///pdfmanager.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get('UPLOAD_DIR', 'uploads')
    EXPORT_FOLDER = os.environ.get('EXPORT_DIR', 'exports')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    ML_CONFIDENCE_THRESHOLD = 0.3
    WTF_CSRF_ENABLED = True
