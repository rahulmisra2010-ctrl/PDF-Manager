"""
PDF API routes for upload, extraction, editing, and export
"""

import os
import uuid
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from config import settings
from models import (
    DocumentListResponse,
    DocumentMetadata,
    EditRequest,
    EditResponse,
    ExportRequest,
    ExportResponse,
    ExtractionResult,
    PDFUploadResponse,
)
from services.pdf_service import PDFService
from services.ml_service import MLService

router = APIRouter()
pdf_service = PDFService()
ml_service = MLService()

# In-memory document store (replace with DB in production)
documents: dict = {}


@router.post("/upload", response_model=PDFUploadResponse)
async def upload_pdf(file: UploadFile = File(...)):
    """Upload a PDF file for processing."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Check file size
    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds maximum of {settings.MAX_UPLOAD_SIZE_MB} MB",
        )

    # Save file
    document_id = str(uuid.uuid4())
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{document_id}.pdf"
    file_path.write_bytes(content)

    # Store metadata
    documents[document_id] = {
        "document_id": document_id,
        "filename": file.filename,
        "file_path": str(file_path),
        "status": "uploaded",
        "upload_time": datetime.now(timezone.utc),
        "file_size_bytes": len(content),
    }

    return PDFUploadResponse(
        document_id=document_id,
        filename=file.filename,
        status="uploaded",
        message="PDF uploaded successfully. Use /extract to process the document.",
    )


@router.post("/extract/{document_id}", response_model=ExtractionResult)
async def extract_data(document_id: str):
    """Extract text, tables, and structured data from an uploaded PDF."""
    if document_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = documents[document_id]
    file_path = doc["file_path"]

    start_time = time.time()

    # Extract text and tables using PDF service
    text, tables, page_count = pdf_service.extract(file_path)

    # Run ML-based field extraction
    fields = ml_service.extract_fields(text, tables)

    # Run address-book field mapping on the extracted text
    mapped_fields = pdf_service.map_address_book_fields(text)

    elapsed = time.time() - start_time

    # Update document status
    documents[document_id]["status"] = "extracted"
    documents[document_id]["page_count"] = page_count
    documents[document_id]["extracted_text"] = text
    documents[document_id]["fields"] = [f.model_dump() for f in fields]
    documents[document_id]["tables"] = tables
    documents[document_id]["mapped_fields"] = mapped_fields

    return ExtractionResult(
        document_id=document_id,
        filename=doc["filename"],
        total_pages=page_count,
        fields=fields,
        extracted_text=text,
        tables=tables,
        extraction_time_seconds=round(elapsed, 3),
        mapped_fields=mapped_fields,
    )


@router.put("/edit", response_model=EditResponse)
async def edit_data(request: EditRequest):
    """Update extracted fields for a document."""
    if request.document_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")

    documents[request.document_id]["fields"] = [
        f.model_dump() for f in request.fields
    ]
    documents[request.document_id]["status"] = "edited"

    return EditResponse(
        document_id=request.document_id,
        status="updated",
        updated_fields=len(request.fields),
    )


@router.post("/export", response_model=ExportResponse)
async def export_document(request: ExportRequest):
    """Export the document with updated data."""
    if request.document_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = documents[request.document_id]
    export_path = pdf_service.export(
        document_id=request.document_id,
        file_path=doc["file_path"],
        fields=doc.get("fields", []),
        fmt=request.format,
    )

    from datetime import datetime, timedelta

    return ExportResponse(
        document_id=request.document_id,
        download_url=f"/api/v1/download/{request.document_id}?format={request.format}",
        format=request.format,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )


@router.get("/download/{document_id}")
async def download_document(document_id: str, format: str = "pdf"):
    """Download an exported document."""
    if document_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")

    export_dir = Path(settings.EXPORT_DIR)
    export_file = export_dir / f"{document_id}.{format}"

    if not export_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Export not found. Please call /export first.",
        )

    media_types = {
        "pdf": "application/pdf",
        "json": "application/json",
        "csv": "text/csv",
    }

    return FileResponse(
        path=str(export_file),
        media_type=media_types.get(format, "application/octet-stream"),
        filename=f"{documents[document_id]['filename'].rsplit('.', 1)[0]}_export.{format}",
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(page: int = 1, page_size: int = 20):
    """List all uploaded documents with pagination."""
    all_docs = list(documents.values())
    start = (page - 1) * page_size
    end = start + page_size

    metadata_list = [
        DocumentMetadata(
            document_id=d["document_id"],
            filename=d["filename"],
            upload_time=d.get("upload_time", __import__("datetime").datetime.utcnow()),
            status=d["status"],
            page_count=d.get("page_count"),
            file_size_bytes=d.get("file_size_bytes"),
        )
        for d in all_docs[start:end]
    ]

    return DocumentListResponse(
        documents=metadata_list,
        total=len(all_docs),
        page=page,
        page_size=page_size,
    )


@router.get("/documents/{document_id}")
async def get_document(document_id: str):
    """Get details for a specific document."""
    if document_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")
    return documents[document_id]


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete a document and its associated files."""
    if document_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = documents.pop(document_id)
    file_path = Path(doc["file_path"])
    if file_path.exists():
        os.remove(file_path)

    return {"status": "deleted", "document_id": document_id}
