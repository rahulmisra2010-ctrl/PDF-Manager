"""
models.py — SQLAlchemy models for the Flask PDF-Manager application.

Models
------
* User         — application users with RBAC roles
* Document     — uploaded PDF files
* ExtractedField — individual fields parsed from a Document
* AuditLog     — immutable audit trail for all user actions
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
        }

    def __repr__(self) -> str:
        return f"<ExtractedField {self.field_name!r}={self.value!r}>"


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
