"""
PDF Manager Application Module

Consolidated application logic for PDF management operations.
Provides a high-level interface for uploading, extracting, editing,
and exporting PDF documents, integrating with the existing FastAPI
services (PDFService and MLService).

Note: This module inserts its own directory (``backend/``) onto
``sys.path`` at import time so that sibling modules (``config``,
``models``, ``services``) can be resolved when this file is imported
from outside the ``backend/`` directory.  The preferred long-term
alternative is to install the backend as a package via ``pip install -e
backend/`` once a ``pyproject.toml`` is added.
"""

import sys
import os

# Ensure the backend directory is on sys.path so this module can be imported
# from any working directory (e.g. the repo root).
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from models import (
    DocumentMetadata,
    EditRequest,
    EditResponse,
    ExtractionResult,
    ExtractedField,
    PDFUploadResponse,
)
from services.ml_service import MLService
from services.pdf_service import PDFService


class PDFManagerApp:
    """
    High-level PDF Manager application class.

    Orchestrates document storage, extraction, editing, and export
    by delegating to PDFService and MLService.
    """

    def __init__(self):
        self.pdf_service = PDFService()
        self.ml_service = MLService()
        # In-memory document store (replace with a database in production)
        self.documents: dict = {}

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload(self, filename: str, content: bytes) -> PDFUploadResponse:
        """
        Save a PDF file and register it in the document store.

        Args:
            filename: Original filename of the uploaded PDF.
            content:  Raw bytes of the PDF file.

        Returns:
            PDFUploadResponse with document metadata.

        Raises:
            ValueError: If the file is not a PDF or exceeds the size limit.
        """
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Only PDF files are accepted")

        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(
                f"File size exceeds maximum of {settings.MAX_UPLOAD_SIZE_MB} MB"
            )

        document_id = str(uuid.uuid4())
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{document_id}.pdf"
        file_path.write_bytes(content)

        self.documents[document_id] = {
            "document_id": document_id,
            "filename": filename,
            "file_path": str(file_path),
            "status": "uploaded",
            "fields": [],
            "upload_time": datetime.now(tz=timezone.utc),
            "file_size_bytes": len(content),
        }

        return PDFUploadResponse(
            document_id=document_id,
            filename=filename,
            status="uploaded",
            message="PDF uploaded successfully",
        )

    # ------------------------------------------------------------------
    # Extract
    # ------------------------------------------------------------------

    def extract(self, document_id: str) -> ExtractionResult:
        """
        Run text and field extraction on a previously uploaded PDF.

        Args:
            document_id: ID returned by :meth:`upload`.

        Returns:
            ExtractionResult containing extracted text, tables, and fields.

        Raises:
            KeyError: If *document_id* is not found.
        """
        import time

        doc = self._get_document(document_id)
        start = time.perf_counter()

        text, tables, page_count = self.pdf_service.extract(doc["file_path"])
        fields: list[ExtractedField] = self.ml_service.extract_fields(text, tables)

        elapsed = round(time.perf_counter() - start, 3)

        # Persist extracted fields for later editing / export
        doc["fields"] = [f.model_dump() for f in fields]
        doc["page_count"] = page_count
        doc["status"] = "extracted"

        return ExtractionResult(
            document_id=document_id,
            filename=doc["filename"],
            total_pages=page_count,
            fields=fields,
            extracted_text=text,
            tables=tables,
            extraction_time_seconds=elapsed,
        )

    # ------------------------------------------------------------------
    # Edit
    # ------------------------------------------------------------------

    def edit(self, request: EditRequest) -> EditResponse:
        """
        Update the stored field values for a document.

        Args:
            request: EditRequest containing the document ID and updated fields.

        Returns:
            EditResponse confirming the number of updated fields.

        Raises:
            KeyError: If the document ID is not found.
        """
        doc = self._get_document(request.document_id)
        doc["fields"] = [f.model_dump() for f in request.fields]
        doc["status"] = "edited"

        return EditResponse(
            document_id=request.document_id,
            status="updated",
            updated_fields=len(request.fields),
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self, document_id: str, fmt: str = "pdf") -> str:
        """
        Export a document with its current field values.

        Args:
            document_id: ID of the document to export.
            fmt:         Output format – ``'pdf'``, ``'json'``, or ``'csv'``.

        Returns:
            File-system path to the exported file.

        Raises:
            KeyError:   If the document ID is not found.
            ValueError: If *fmt* is not a supported format.
        """
        supported = {"pdf", "json", "csv"}
        if fmt not in supported:
            raise ValueError(f"Unsupported format '{fmt}'. Choose from {supported}.")

        doc = self._get_document(document_id)
        return self.pdf_service.export(
            document_id=document_id,
            file_path=doc["file_path"],
            fields=doc.get("fields", []),
            fmt=fmt,
        )

    # ------------------------------------------------------------------
    # Document listing
    # ------------------------------------------------------------------

    def list_documents(self) -> list[DocumentMetadata]:
        """Return metadata for all stored documents."""
        result: list[DocumentMetadata] = []
        for doc in self.documents.values():
            result.append(
                DocumentMetadata(
                    document_id=doc["document_id"],
                    filename=doc["filename"],
                    upload_time=doc["upload_time"],
                    status=doc["status"],
                    page_count=doc.get("page_count"),
                    file_size_bytes=doc.get("file_size_bytes"),
                )
            )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_document(self, document_id: str) -> dict:
        """Retrieve a document record or raise KeyError."""
        if document_id not in self.documents:
            raise KeyError(f"Document '{document_id}' not found")
        return self.documents[document_id]
