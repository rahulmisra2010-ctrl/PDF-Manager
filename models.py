"""
models.py — SQLAlchemy models for the Flask PDF-Manager application.

Models
------
* User             — application users with RBAC roles
* Document         — uploaded PDF files
* ExtractedField   — individual fields parsed from a Document
* FieldEditHistory — history of field edits
* OCRCharacterData — per-character OCR confidence + bounding boxes
* RAGEmbedding     — vector embeddings for RAG search
* AuditLog         — immutable audit trail for all user actions
"""

from __future__ import annotations

from datetime import datetime

from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
bcrypt = Bcrypt()


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    """Application user with role-based access control."""

    __tablename__ = "users"

    ROLES = ("Admin", "Verifier", "Viewer")

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="Viewer")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    documents = db.relationship("Document", backref="uploader", lazy="dynamic")
    audit_logs = db.relationship("AuditLog", backref="user", lazy="dynamic",
                                 foreign_keys="AuditLog.user_id")

    def set_password(self, password: str) -> None:
        """Hash *password* (minimum 8 characters) and store it."""
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Return *True* if *password* matches the stored hash."""
        return bcrypt.check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username!r} role={self.role!r}>"


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class Document(db.Model):
    """An uploaded PDF file and its processing status."""

    __tablename__ = "documents"

    STATUSES = ("uploaded", "extracted", "edited", "approved", "rejected")

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="uploaded")
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    page_count = db.Column(db.Integer, nullable=True)
    file_size = db.Column(db.Integer, nullable=True)  # bytes

    fields = db.relationship(
        "ExtractedField",
        backref="document",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} status={self.status!r}>"


# ---------------------------------------------------------------------------
# ExtractedField
# ---------------------------------------------------------------------------

class ExtractedField(db.Model):
    """A single field extracted from a Document."""

    __tablename__ = "extracted_fields"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=False
    )
    field_name = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Text, nullable=True)
    confidence = db.Column(db.Float, nullable=False, default=1.0)
    is_edited = db.Column(db.Boolean, nullable=False, default=False)
    original_value = db.Column(db.Text, nullable=True)
    # Bounding box coordinates (PDF point units)
    bbox_x = db.Column(db.Float, nullable=True)
    bbox_y = db.Column(db.Float, nullable=True)
    bbox_width = db.Column(db.Float, nullable=True)
    bbox_height = db.Column(db.Float, nullable=True)
    page_number = db.Column(db.Integer, nullable=True, default=1)
    version = db.Column(db.Integer, nullable=False, default=1)

    edit_history = db.relationship(
        "FieldEditHistory",
        backref="field",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return {
            "id": self.id,
            "document_id": self.document_id,
            "field_name": self.field_name,
            "value": self.value,
            "confidence": self.confidence,
            "is_edited": self.is_edited,
            "original_value": self.original_value,
            "bbox": {
                "x": self.bbox_x,
                "y": self.bbox_y,
                "width": self.bbox_width,
                "height": self.bbox_height,
            } if self.bbox_x is not None else None,
            "page_number": self.page_number,
            "version": self.version,
        }

    def __repr__(self) -> str:
        return f"<ExtractedField {self.field_name!r}={self.value!r}>"


# ---------------------------------------------------------------------------
# FieldEditHistory
# ---------------------------------------------------------------------------

class FieldEditHistory(db.Model):
    """Tracks every edit made to an ExtractedField."""

    __tablename__ = "field_edit_history"

    id = db.Column(db.Integer, primary_key=True)
    field_id = db.Column(
        db.Integer, db.ForeignKey("extracted_fields.id"), nullable=False
    )
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    edited_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    edited_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "field_id": self.field_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "edited_by": self.edited_by,
            "edited_at": self.edited_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<FieldEditHistory field_id={self.field_id} at={self.edited_at}>"


# ---------------------------------------------------------------------------
# OCRCharacterData
# ---------------------------------------------------------------------------

class OCRCharacterData(db.Model):
    """Per-character OCR output with bounding box and confidence."""

    __tablename__ = "ocr_character_data"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=False
    )
    page_number = db.Column(db.Integer, nullable=False, default=1)
    character = db.Column(db.String(10), nullable=False)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    # Bounding box in PDF point units
    x = db.Column(db.Float, nullable=True)
    y = db.Column(db.Float, nullable=True)
    width = db.Column(db.Float, nullable=True)
    height = db.Column(db.Float, nullable=True)
    ocr_engine = db.Column(db.String(50), nullable=True)  # tesseract/easyocr/paddleocr

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "page_number": self.page_number,
            "character": self.character,
            "confidence": self.confidence,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "ocr_engine": self.ocr_engine,
        }

    def __repr__(self) -> str:
        return f"<OCRCharacterData char={self.character!r} conf={self.confidence:.2f}>"


# ---------------------------------------------------------------------------
# RAGEmbedding
# ---------------------------------------------------------------------------

class RAGEmbedding(db.Model):
    """Vector embedding for a field/chunk used by the RAG system."""

    __tablename__ = "rag_embeddings"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=False
    )
    field_name = db.Column(db.String(100), nullable=True)
    text_content = db.Column(db.Text, nullable=False)
    # Serialised embedding vector (JSON list of floats)
    embedding = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "field_name": self.field_name,
            "text_content": self.text_content,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<RAGEmbedding doc={self.document_id} field={self.field_name!r}>"


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------

class AuditLog(db.Model):
    """Immutable audit trail for all user actions."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50), nullable=True)
    resource_id = db.Column(db.String(100), nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AuditLog action={self.action!r} at={self.timestamp}>"
