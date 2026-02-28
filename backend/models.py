"""
Pydantic models for PDF-Manager API
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class PDFUploadResponse(BaseModel):
    """Response model for PDF upload."""

    document_id: str
    filename: str
    status: str
    message: str


class ExtractedField(BaseModel):
    """A single extracted data field from a PDF."""

    field_name: str
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    page_number: int = Field(ge=1)
    bounding_box: dict[str, float] | None = None


class ExtractionResult(BaseModel):
    """Result of ML-based data extraction from a PDF."""

    document_id: str
    filename: str
    total_pages: int
    fields: list[ExtractedField]
    extracted_text: str
    tables: list[list[list[str]]]
    extraction_time_seconds: float


class EditRequest(BaseModel):
    """Request model for editing extracted data."""

    document_id: str
    fields: list[ExtractedField]


class EditResponse(BaseModel):
    """Response model for edit operations."""

    document_id: str
    status: str
    updated_fields: int


class ExportRequest(BaseModel):
    """Request model for exporting a document."""

    document_id: str
    format: str = Field(default="pdf", pattern="^(pdf|json|csv)$")
    include_annotations: bool = False


class ExportResponse(BaseModel):
    """Response model for export operations."""

    document_id: str
    download_url: str
    format: str
    expires_at: datetime


class DocumentMetadata(BaseModel):
    """Metadata for a stored document."""

    document_id: str
    filename: str
    upload_time: datetime
    status: str
    page_count: int | None = None
    file_size_bytes: int | None = None


class DocumentListResponse(BaseModel):
    """Response model for listing documents."""

    documents: list[DocumentMetadata]
    total: int
    page: int
    page_size: int
