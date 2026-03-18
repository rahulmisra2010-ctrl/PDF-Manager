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
* ValidationLog    — audit trail for Train Me validation runs
* FieldCorrection  — per-field corrections applied by Train Me
* TrainingExample  — labeled training examples for RAG confidence boosting
* TrainingExample  — labeled field values used by TrainingService
* DocumentSchema   — persisted ordered field labels discovered per document
"""

from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# ValidationLog
# ---------------------------------------------------------------------------

class ValidationLog(db.Model):
    """Audit trail for each Train Me validation run."""

    __tablename__ = "validation_logs"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=False
    )
    reference_set = db.Column(db.String(100), nullable=False)
    validation_timestamp = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    total_fields = db.Column(db.Integer, nullable=False, default=0)
    validated_count = db.Column(db.Integer, nullable=False, default=0)
    accuracy_score = db.Column(db.Float, nullable=False, default=0.0)
    results_json = db.Column(db.Text, nullable=True)  # JSON field-by-field details
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    corrections = db.relationship(
        "FieldCorrection",
        backref="validation_log",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "reference_set": self.reference_set,
            "validation_timestamp": self.validation_timestamp.isoformat(),
            "total_fields": self.total_fields,
            "validated_count": self.validated_count,
            "accuracy_score": self.accuracy_score,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<ValidationLog doc={self.document_id} ref={self.reference_set!r}"
            f" acc={self.accuracy_score:.2f}>"
        )


# ---------------------------------------------------------------------------
# FieldCorrection
# ---------------------------------------------------------------------------

class FieldCorrection(db.Model):
    """Records a single field correction applied during a Train Me run."""

    __tablename__ = "field_corrections"

    CORRECTION_SOURCES = ("train_me", "manual", "rag")

    id = db.Column(db.Integer, primary_key=True)
    validation_log_id = db.Column(
        db.Integer, db.ForeignKey("validation_logs.id"), nullable=False
    )
    field_id = db.Column(
        db.Integer, db.ForeignKey("extracted_fields.id"), nullable=True
    )
    field_name = db.Column(db.String(100), nullable=False)
    original_value = db.Column(db.Text, nullable=True)
    corrected_value = db.Column(db.Text, nullable=True)
    correction_source = db.Column(
        db.String(20), nullable=False, default="train_me"
    )
    validated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "validation_log_id": self.validation_log_id,
            "field_id": self.field_id,
            "field_name": self.field_name,
            "original_value": self.original_value,
            "corrected_value": self.corrected_value,
            "correction_source": self.correction_source,
            "validated_at": self.validated_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<FieldCorrection field={self.field_name!r}"
            f" {self.original_value!r} → {self.corrected_value!r}>"
        )


# ---------------------------------------------------------------------------
# TrainingExample
# ---------------------------------------------------------------------------

class TrainingExample(db.Model):
    """A labeled training example for improving RAG extraction confidence.

    Users upload and manually correct address book PDFs, then mark them as
    training examples. The RAG extractor uses these examples to boost
    confidence scores for fields that match training data.

    Each row stores one field_name / field_value pair drawn from a confirmed
    document. The TrainingService queries these rows to:

    * detect email-domain patterns across all Email examples
    * auto-generate missing emails using ``firstname@domain``
    * fill blank fields using the most recent matching value
    * correct mismatched values when training data disagrees with RAG output
    Each row stores one field_name / field_value pair drawn from a confirmed
    document.  The TrainingService queries these rows to fill blank fields and
    correct incorrect extraction results.
    """

    __tablename__ = "training_examples"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=False
    )
    field_name = db.Column(db.String(255), nullable=False)
    correct_value = db.Column(db.Text, nullable=False)
    field_value = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # ROI metadata — populated by the per-document "all fields at once" trainer
    page_number = db.Column(db.Integer, nullable=True, default=1)
    x0 = db.Column(db.Float, nullable=True)
    y0 = db.Column(db.Float, nullable=True)
    x1 = db.Column(db.Float, nullable=True)
    y1 = db.Column(db.Float, nullable=True)
    engine = db.Column(db.String(64), nullable=True)
    anchor_text = db.Column(db.Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "field_name": self.field_name,
            "correct_value": self.correct_value,
            "field_value": self.field_value,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "page_number": self.page_number,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
            "engine": self.engine,
            "anchor_text": self.anchor_text,
        }

    def __repr__(self) -> str:
        return (
            f"<TrainingExample doc={self.document_id}"
            f" field={self.field_name!r} value={self.correct_value!r}>"
        )


# ---------------------------------------------------------------------------
# DocumentSchema
# ---------------------------------------------------------------------------

class DocumentSchema(db.Model):
    """Persisted ordered list of field labels discovered for a document.

    Created automatically the first time dynamic extraction runs for a document.
    Subsequent extractions map discovered labels to this schema using exact,
    normalised, and fuzzy matching so the field list stays stable across re-runs.
    """

    __tablename__ = "document_schemas"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=False, unique=True
    )
    # Ordered list of label strings serialised as JSON, e.g. '["Name", "Email"]'
    labels_json = db.Column(db.Text, nullable=False, default="[]")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @property
    def labels(self) -> list[str]:
        """Return the ordered list of field labels."""
        return json.loads(self.labels_json)

    @labels.setter
    def labels(self, value: list[str]) -> None:
        """Set and serialise the ordered list of field labels."""
        self.labels_json = json.dumps(value, ensure_ascii=False)
        self.updated_at = datetime.utcnow()

    def __repr__(self) -> str:
        return f"<DocumentSchema doc={self.document_id} n={len(self.labels)}>"
