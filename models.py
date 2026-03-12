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
* ExtractionJob    — batch extraction job tracking
* ExtractedSample  — auto-generated extraction samples for ML training
* DocumentType     — learned document type classifications
* FieldPattern     — learned field format patterns
* ExtractionMetric — quality scores per extraction
* MLModel          — trained ML model registry
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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "field_name": self.field_name,
            "correct_value": self.correct_value,
            "field_value": self.field_value,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }

    def __repr__(self) -> str:
        return (
            f"<TrainingExample doc={self.document_id}"
            f" field={self.field_name!r} value={self.correct_value!r}>"
        )


# ===========================================================================
# Automatic Extraction System Models
# ===========================================================================

# ---------------------------------------------------------------------------
# ExtractionJob
# ---------------------------------------------------------------------------

class ExtractionJob(db.Model):
    """Tracks a batch extraction job (1 to thousands of files)."""

    __tablename__ = "extraction_jobs"

    STATUSES = ("queued", "running", "completed", "failed", "cancelled")

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="queued")
    total_files = db.Column(db.Integer, nullable=False, default=0)
    processed_files = db.Column(db.Integer, nullable=False, default=0)
    failed_files = db.Column(db.Integer, nullable=False, default=0)
    tool_chain = db.Column(db.Text, nullable=True)  # JSON list of tools used
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    result_summary = db.Column(db.Text, nullable=True)  # JSON summary

    samples = db.relationship(
        "ExtractedSample",
        backref="job",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        progress = (
            round(self.processed_files / self.total_files * 100, 1)
            if self.total_files
            else 0
        )
        return {
            "id": self.id,
            "job_id": self.job_id,
            "status": self.status,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "progress_pct": progress,
            "tool_chain": self.tool_chain,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "error_message": self.error_message,
            "result_summary": self.result_summary,
        }

    def __repr__(self) -> str:
        return f"<ExtractionJob {self.job_id} status={self.status}>"


# ---------------------------------------------------------------------------
# ExtractedSample
# ---------------------------------------------------------------------------

class ExtractedSample(db.Model):
    """An auto-generated extraction sample stored in the sample database."""

    __tablename__ = "extracted_samples"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(
        db.Integer, db.ForeignKey("extraction_jobs.id"), nullable=True
    )
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(20), nullable=True)
    document_type = db.Column(db.String(100), nullable=True)
    extracted_fields = db.Column(db.Text, nullable=True)  # JSON
    source_tool = db.Column(db.String(50), nullable=True)
    confidence_score = db.Column(db.Float, nullable=True)
    llm_validated = db.Column(db.Boolean, nullable=False, default=False)
    ml_scored = db.Column(db.Boolean, nullable=False, default=False)
    raw_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    feedback_applied = db.Column(db.Boolean, nullable=False, default=False)
    feedback_notes = db.Column(db.Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "document_type": self.document_type,
            "extracted_fields": self.extracted_fields,
            "source_tool": self.source_tool,
            "confidence_score": self.confidence_score,
            "llm_validated": self.llm_validated,
            "ml_scored": self.ml_scored,
            "raw_text": self.raw_text,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "feedback_applied": self.feedback_applied,
            "feedback_notes": self.feedback_notes,
        }

    def __repr__(self) -> str:
        return (
            f"<ExtractedSample {self.filename!r}"
            f" type={self.document_type!r} conf={self.confidence_score}>"
        )


# ---------------------------------------------------------------------------
# DocumentType
# ---------------------------------------------------------------------------

class DocumentType(db.Model):
    """A learned document type with its associated classification keywords."""

    __tablename__ = "document_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    keywords = db.Column(db.Text, nullable=True)  # JSON list
    preferred_tools = db.Column(db.Text, nullable=True)  # JSON list
    sample_count = db.Column(db.Integer, nullable=False, default=0)
    avg_confidence = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "preferred_tools": self.preferred_tools,
            "sample_count": self.sample_count,
            "avg_confidence": self.avg_confidence,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<DocumentType {self.name!r} samples={self.sample_count}>"


# ---------------------------------------------------------------------------
# FieldPattern
# ---------------------------------------------------------------------------

class FieldPattern(db.Model):
    """A learned regex/format pattern for a specific field type."""

    __tablename__ = "field_patterns"

    id = db.Column(db.Integer, primary_key=True)
    field_name = db.Column(db.String(100), nullable=False)
    document_type = db.Column(db.String(100), nullable=True)
    pattern = db.Column(db.Text, nullable=True)  # regex
    example_values = db.Column(db.Text, nullable=True)  # JSON list
    match_count = db.Column(db.Integer, nullable=False, default=0)
    accuracy_score = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "field_name": self.field_name,
            "document_type": self.document_type,
            "pattern": self.pattern,
            "example_values": self.example_values,
            "match_count": self.match_count,
            "accuracy_score": self.accuracy_score,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<FieldPattern field={self.field_name!r}"
            f" doc_type={self.document_type!r}>"
        )


# ---------------------------------------------------------------------------
# ExtractionMetric
# ---------------------------------------------------------------------------

class ExtractionMetric(db.Model):
    """Quality metrics for a single extraction run on a file."""

    __tablename__ = "extraction_metrics"

    id = db.Column(db.Integer, primary_key=True)
    sample_id = db.Column(
        db.Integer, db.ForeignKey("extracted_samples.id"), nullable=True
    )
    job_id = db.Column(db.String(64), nullable=True)
    filename = db.Column(db.String(255), nullable=True)
    tool_used = db.Column(db.String(50), nullable=True)
    fields_extracted = db.Column(db.Integer, nullable=False, default=0)
    confidence_avg = db.Column(db.Float, nullable=True)
    confidence_min = db.Column(db.Float, nullable=True)
    confidence_max = db.Column(db.Float, nullable=True)
    anomalies_detected = db.Column(db.Integer, nullable=False, default=0)
    validation_errors = db.Column(db.Integer, nullable=False, default=0)
    processing_time_ms = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sample_id": self.sample_id,
            "job_id": self.job_id,
            "filename": self.filename,
            "tool_used": self.tool_used,
            "fields_extracted": self.fields_extracted,
            "confidence_avg": self.confidence_avg,
            "confidence_min": self.confidence_min,
            "confidence_max": self.confidence_max,
            "anomalies_detected": self.anomalies_detected,
            "validation_errors": self.validation_errors,
            "processing_time_ms": self.processing_time_ms,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<ExtractionMetric tool={self.tool_used!r}"
            f" fields={self.fields_extracted} conf={self.confidence_avg}>"
        )


# ---------------------------------------------------------------------------
# MLModel
# ---------------------------------------------------------------------------

class MLModel(db.Model):
    """Registry of trained ML models for document/field classification."""

    __tablename__ = "ml_models"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    model_type = db.Column(db.String(50), nullable=True)  # e.g. "field_classifier"
    version = db.Column(db.String(20), nullable=True)
    accuracy = db.Column(db.Float, nullable=True)
    training_samples = db.Column(db.Integer, nullable=False, default=0)
    model_path = db.Column(db.String(512), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    trained_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    metadata_json = db.Column(db.Text, nullable=True)  # JSON

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "model_type": self.model_type,
            "version": self.version,
            "accuracy": self.accuracy,
            "training_samples": self.training_samples,
            "model_path": self.model_path,
            "is_active": self.is_active,
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
            "created_at": self.created_at.isoformat(),
            "metadata_json": self.metadata_json,
        }

    def __repr__(self) -> str:
        return (
            f"<MLModel {self.name!r} v{self.version}"
            f" acc={self.accuracy} active={self.is_active}>"
        )
