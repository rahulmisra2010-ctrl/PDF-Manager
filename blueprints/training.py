"""
blueprints/training.py — Training examples API and UI blueprint.

Routes
------
POST /api/v1/training/add         — save labeled training examples for a document
GET  /api/v1/training/examples    — list all training examples as JSON
GET  /training/examples           — HTML view of all training examples
GET  /training/upload-sample      — form UI to create a sample training entry
POST /training/upload-sample      — process the uploaded sample form
POST /training/examples/<id>/delete — delete a training example group (document)
"""

from __future__ import annotations

import io
import logging
import os
import re

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from models import AuditLog, Document, ExtractedField, TrainingExample, db

logger = logging.getLogger(__name__)

# Document types available for the upload-sample form
DOCUMENT_TYPES = [
    "Address Book",
    "Invoice",
    "Receipt",
    "Contract",
    "Resume",
    "Medical Record",
    "Tax Form",
    "Bank Statement",
    "Other",
]

training_bp = Blueprint("training", __name__)

# Allowed file extensions for the file-upload mode
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".xlsx", ".xls"}


def _extract_fields_from_file(file_storage: FileStorage) -> dict[str, str]:
    """Extract field name → value pairs from an uploaded file.

    Supports PDF, TXT, DOCX, and XLSX/XLS files.
    For generic files the parser looks for lines matching ``Field: Value``.
    Returns an ordered dict (insertion-ordered in Python 3.7+).
    """
    filename = file_storage.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    data = file_storage.read()

    if ext == ".txt":
        return _parse_txt(data.decode("utf-8", errors="replace"))

    if ext == ".pdf":
        return _parse_pdf(data)

    if ext == ".docx":
        return _parse_docx(data)

    if ext in (".xlsx", ".xls"):
        return _parse_excel(data, ext)

    return {}


def _parse_txt(text: str) -> dict[str, str]:
    """Parse ``Field: Value`` pairs from plain text (one per line)."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Accept lines like "Name: Rahul Misra" or "Name = Rahul Misra"
        m = re.match(r"^([^:=]+?)\s*[:=]\s*(.+)$", line)
        if m:
            fname = m.group(1).strip()
            fval = m.group(2).strip()
            if fname and fval:
                fields[fname] = fval
    return fields


# ---------------------------------------------------------------------------
# Well-known field labels used for PDF text parsing heuristics.
# These are recognised both in colon-separated and space-only contexts.
# ---------------------------------------------------------------------------
_KNOWN_LABELS: list[str] = [
    "Name", "First Name", "Last Name", "Street Address",
    "City", "State", "Zip Code", "Zip", "Postal Code", "Country",
    "Home Phone", "Cell Phone", "Work Phone", "Phone", "Mobile",
    "Email", "Email Address", "Company", "Organization", "Birthday",
    "Notes", "Fax", "Website", "Invoice No", "Invoice Number",
    "Date", "Amount", "Total", "Bill To", "Ship To",
]
# Short / ambiguous labels that should only be matched when followed by ":"
_COLON_ONLY_LABELS: frozenset[str] = frozenset({"Address", "Phone", "Date", "Amount", "Total", "Notes"})


def _parse_pdf_text(text: str) -> dict[str, str]:
    """Parse field→value pairs from PDF-extracted text using multiple heuristics.

    Three strategies are tried in order:

    1. **Multi-field lines** — a single line contains several ``Label: Value``
       pairs (e.g. ``City: Asansol State: WB Zip Code: 713301``).  Known
       labels are used as anchors so that city/state values are not mistaken
       for label names.

    2. **Standard single-field lines** — ``Field: Value`` or ``Field = Value``
       on one line.  Lines already handled by strategy 1 are skipped.

    3. **No-separator labels** — a known label at the start of a line followed
       by its value with no punctuation separator (e.g. ``Name Rahul Misra``).
    """
    fields: dict[str, str] = {}

    # Build regex patterns
    _known_set = set(_KNOWN_LABELS)
    all_labels = _KNOWN_LABELS + [lbl for lbl in _COLON_ONLY_LABELS if lbl not in _known_set]
    all_sorted = sorted(all_labels, key=len, reverse=True)
    all_pattern = "|".join(re.escape(lbl) for lbl in all_sorted)
    label_re = re.compile(rf"(?:^|(?<=\s))({all_pattern})\s*:", re.IGNORECASE)

    lines = text.splitlines()

    # Pre-identify multi-field lines (≥2 known labels with colons on one line)
    multi_field_lines: set[int] = set()
    for i, line in enumerate(lines):
        if len(label_re.findall(line.strip())) >= 2:
            multi_field_lines.add(i)

    # ── Strategy 1: multi-field lines ──────────────────────────────────────
    for i in multi_field_lines:
        line = lines[i].strip()
        matches = list(label_re.finditer(line))
        for j, m in enumerate(matches):
            fname = m.group(1).strip()
            val_start = m.end()
            val_end = matches[j + 1].start() if j + 1 < len(matches) else len(line)
            fval = line[val_start:val_end].strip()
            if fname and fval and fname not in fields:
                fields[fname] = fval

    # ── Strategy 2: single-field colon/equals lines ────────────────────────
    for i, line in enumerate(lines):
        if i in multi_field_lines:
            continue
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([^:=]+?)\s*[:=]\s*(.+)$", line)
        if m:
            fname = m.group(1).strip()
            fval = m.group(2).strip()
            # Skip if the value contains another known-label:colon pair
            # (indicates a multi-field line that strategy 1 should have handled)
            value_contains_nested_label = bool(label_re.search(fval))
            if fname and fval and fname not in fields and not value_contains_nested_label:
                fields[fname] = fval

    # ── Strategy 3: known labels without separator ─────────────────────────
    no_sep_labels = [lbl for lbl in _KNOWN_LABELS if lbl not in _COLON_ONLY_LABELS]
    no_sep_sorted = sorted(no_sep_labels, key=len, reverse=True)
    no_sep_pattern = "|".join(re.escape(lbl) for lbl in no_sep_sorted)
    no_sep_re = re.compile(rf"^({no_sep_pattern})\s+(.+)$", re.IGNORECASE)

    for i, line in enumerate(lines):
        if i in multi_field_lines:
            continue
        line = line.strip()
        if not line:
            continue
        m = no_sep_re.match(line)
        if m:
            fname = m.group(1).strip()
            fval = m.group(2).strip()
            if fname and fval and fname not in fields:
                fields[fname] = fval

    return fields


def _extract_text_from_pdf(data: bytes) -> str:
    """Return the full text of a PDF, trying PyMuPDF then pdfplumber as fallback."""
    # Primary: PyMuPDF (fitz)
    try:
        import fitz  # PyMuPDF  # noqa: PLC0415

        doc = fitz.open(stream=data, filetype="pdf")
        parts = [page.get_text() for page in doc]
        doc.close()
        text = "\n".join(parts)
        if text.strip():
            return text
    except Exception as exc:
        logger.warning("_extract_text_from_pdf (PyMuPDF): %s", exc)

    # Fallback: pdfplumber
    try:
        import pdfplumber  # noqa: PLC0415

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            parts = [page.extract_text() or "" for page in pdf.pages]
        text = "\n".join(parts)
        if text.strip():
            return text
    except Exception as exc:
        logger.warning("_extract_text_from_pdf (pdfplumber): %s", exc)

    return ""


def _parse_pdf(data: bytes) -> dict[str, str]:
    """Extract key-value pairs from PDF bytes.

    Uses PyMuPDF (primary) or pdfplumber (fallback) to get the raw text, then
    applies multi-strategy heuristic parsing to find field→value pairs.  The
    parser handles:

    * Standard ``Field: Value`` and ``Field = Value`` lines.
    * Multiple pairs on one line (``City: Asansol State: WB Zip Code: 713301``).
    * Known address-book labels without any separator (``Name Rahul Misra``).
    """
    full_text = _extract_text_from_pdf(data)
    if not full_text.strip():
        logger.warning("_parse_pdf: no text could be extracted from PDF")
        return {}
    return _parse_pdf_text(full_text)


def _parse_docx(data: bytes) -> dict[str, str]:
    """Extract key-value pairs from a .docx file."""
    try:
        import docx  # python-docx

        doc = docx.Document(io.BytesIO(data))
        lines = [p.text for p in doc.paragraphs]
        # Also include table cells
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                # Treat a two-column row as field:value
                if len(cells) == 2 and cells[0] and cells[1]:
                    lines.append(f"{cells[0]}: {cells[1]}")
                else:
                    lines.append("  ".join(cells))
        return _parse_txt("\n".join(lines))
    except Exception as exc:
        logger.warning("_parse_docx: failed to parse DOCX: %s", exc)
        return {}


def _parse_excel(data: bytes, ext: str) -> dict[str, str]:
    """Extract key-value pairs from an Excel file (.xlsx or .xls)."""
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        ws = wb.active
        fields: dict[str, str] = {}
        for row in ws.iter_rows(values_only=True):
            non_empty = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if len(non_empty) >= 2:
                # First cell = field name, second cell = value
                fname = non_empty[0]
                fval = non_empty[1]
                if fname and fval:
                    fields[fname] = fval
            elif len(non_empty) == 1:
                # Single cell: try "Field: Value" parsing
                m = re.match(r"^([^:=]+?)\s*[:=]\s*(.+)$", non_empty[0])
                if m:
                    fname = m.group(1).strip()
                    fval = m.group(2).strip()
                    if fname and fval:
                        fields[fname] = fval
        return fields
    except Exception as exc:
        logger.warning("_parse_excel: failed to parse Excel: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# POST /api/v1/training/add
# ---------------------------------------------------------------------------

@training_bp.route("/api/v1/training/add", methods=["POST"])
@login_required
def add_training():
    """Save labeled training examples for a document.

    Accepts JSON body::

        {
          "document_id": 1,
          "fields": {
            "Name": "Rahul Misra",
            "City": "Asansol",
            ...
          }
        }

    Replaces any existing training examples for the document with the new
    set, then rebuilds RAG embeddings so that future extractions benefit from
    the training data.

    Returns::

        {"ok": true, "document_id": 1, "saved": [{"field_name": ..., "correct_value": ...}, ...]}
    """
    data = request.get_json(silent=True) or {}
    document_id = data.get("document_id")
    fields = data.get("fields")

    if not document_id:
        return jsonify({"ok": False, "error": "document_id is required"}), 400

    if not isinstance(fields, dict) or not fields:
        return jsonify({"ok": False, "error": "'fields' must be a non-empty object"}), 400

    # Validate document exists
    Document.query.get_or_404(document_id)

    # Replace existing examples for this document
    TrainingExample.query.filter_by(document_id=document_id).delete()

    saved: list[dict] = []
    for field_name, correct_value in fields.items():
        correct_value = str(correct_value).strip() if correct_value is not None else ""
        if not correct_value:
            continue  # skip blank values
        ex = TrainingExample(
            document_id=document_id,
            field_name=str(field_name).strip(),
            correct_value=correct_value,
        )
        db.session.add(ex)
        saved.append({"field_name": ex.field_name, "correct_value": ex.correct_value})

    _log(
        current_user.id,
        "add_training",
        "document",
        str(document_id),
        details=f"fields={list(fields.keys())}",
    )
    db.session.commit()

    # Rebuild RAG embeddings if RAGService is available
    _rebuild_rag_embeddings(document_id)

    return jsonify({"ok": True, "document_id": document_id, "saved": saved})


# ---------------------------------------------------------------------------
# GET /api/v1/training/examples
# ---------------------------------------------------------------------------

@training_bp.route("/api/v1/training/examples", methods=["GET"])
@login_required
def list_examples_json():
    """Return all training examples as JSON."""
    examples = TrainingExample.query.order_by(TrainingExample.created_at.desc()).all()
    return jsonify(
        {
            "count": len(examples),
            "examples": [ex.to_dict() for ex in examples],
        }
    )


# ---------------------------------------------------------------------------
# GET /training/examples
# ---------------------------------------------------------------------------

@training_bp.route("/training/examples")
@login_required
def examples_list():
    """HTML view — display all training examples grouped by document."""
    examples = (
        TrainingExample.query
        .order_by(TrainingExample.document_id, TrainingExample.field_name)
        .all()
    )

    # Group by document
    grouped: dict[int, dict] = {}
    for ex in examples:
        doc_id = ex.document_id
        if doc_id not in grouped:
            doc = Document.query.get(doc_id)
            grouped[doc_id] = {
                "document": doc,
                "examples": [],
            }
        grouped[doc_id]["examples"].append(ex)

    return render_template(
        "training/examples_list.html",
        grouped=grouped,
        total=len(examples),
    )


# ---------------------------------------------------------------------------
# GET /training/upload-sample   — render the upload form
# POST /training/upload-sample  — process the form submission
# ---------------------------------------------------------------------------

@training_bp.route("/training/upload-sample", methods=["GET", "POST"])
@login_required
def upload_sample():
    """Form-based UI for uploading a named training sample with field-value pairs."""
    if request.method == "POST":
        sample_name = request.form.get("sample_name", "").strip()
        document_type = request.form.get("document_type", "").strip()
        upload_mode = request.form.get("upload_mode", "manual")

        if not sample_name:
            flash("Sample name is required.", "danger")
            return render_template(
                "training/upload_sample.html",
                document_types=DOCUMENT_TYPES,
            )

        fields: dict[str, str] = {}

        if upload_mode == "file":
            # --- File upload mode ---
            uploaded_file = request.files.get("sample_file")
            if not uploaded_file or not uploaded_file.filename:
                flash("Please select a file to upload.", "danger")
                return render_template(
                    "training/upload_sample.html",
                    document_types=DOCUMENT_TYPES,
                )
            ext = os.path.splitext(uploaded_file.filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                flash(
                    f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
                    "danger",
                )
                return render_template(
                    "training/upload_sample.html",
                    document_types=DOCUMENT_TYPES,
                )
            fields = _extract_fields_from_file(uploaded_file)
            if not fields:
                # Re-read the file to show extracted raw text as a manual-entry hint
                uploaded_file.stream.seek(0)
                raw_data = uploaded_file.stream.read()
                raw_text = ""
                ext2 = os.path.splitext(uploaded_file.filename)[1].lower()
                if ext2 == ".pdf":
                    raw_text = _extract_text_from_pdf(raw_data)
                elif ext2 == ".txt":
                    raw_text = raw_data.decode("utf-8", errors="replace")
                flash(
                    "Could not automatically detect field-value pairs from the uploaded file. "
                    "The extracted text is shown below — please map the fields manually.",
                    "warning",
                )
                return render_template(
                    "training/upload_sample.html",
                    document_types=DOCUMENT_TYPES,
                    prefill_mode="manual",
                    extracted_text=raw_text,
                    form_sample_name=sample_name,
                    form_document_type=document_type,
                )
        else:
            # --- Manual entry mode ---
            field_names = request.form.getlist("field_name[]")
            field_values = request.form.getlist("field_value[]")
            for fname, fval in zip(field_names, field_values):
                fname = fname.strip()
                fval = fval.strip()
                if fname and fval:
                    fields[fname] = fval

            if not fields:
                flash("Please provide at least one field name and value.", "danger")
                return render_template(
                    "training/upload_sample.html",
                    document_types=DOCUMENT_TYPES,
                )

        # Create a placeholder Document record with status="training"
        safe_name = secure_filename(sample_name) or "sample"
        placeholder_path = os.path.join(
            current_app.config.get("UPLOAD_FOLDER", "uploads"),
            f"{safe_name}.training",
        )
        display_name = f"{sample_name} [{document_type}]" if document_type else sample_name
        doc = Document(
            filename=display_name,
            file_path=placeholder_path,
            status="training",
            uploaded_by=current_user.id,
        )
        db.session.add(doc)
        db.session.flush()  # get doc.id before committing

        # Persist field-value pairs as TrainingExample rows
        saved: list[dict] = []
        for fname, fval in fields.items():
            ex = TrainingExample(
                document_id=doc.id,
                field_name=fname,
                correct_value=fval,
                created_by=current_user.id,
            )
            db.session.add(ex)
            saved.append({"field_name": fname, "correct_value": fval})

        _log(
            current_user.id,
            "upload_sample",
            "document",
            str(doc.id),
            details=f"sample_name={sample_name!r}, document_type={document_type!r}, mode={upload_mode!r}, fields={list(fields.keys())}",
        )
        db.session.commit()

        flash(
            f"Sample '{sample_name}' uploaded successfully with {len(saved)} field(s).",
            "success",
        )
        return redirect(url_for("training.examples_list"))

    return render_template(
        "training/upload_sample.html",
        document_types=DOCUMENT_TYPES,
    )


# ---------------------------------------------------------------------------
# POST /training/examples/<doc_id>/delete — remove a sample and its examples
# ---------------------------------------------------------------------------

@training_bp.route("/training/examples/<int:doc_id>/delete", methods=["POST"])
@login_required
def delete_sample(doc_id: int):
    """Delete all training examples for a document (and the document if it is a training placeholder)."""
    doc = Document.query.get_or_404(doc_id)

    # Remove all training examples linked to this document
    deleted_count = TrainingExample.query.filter_by(document_id=doc_id).delete()

    _log(
        current_user.id,
        "delete_sample",
        "document",
        str(doc_id),
        details=f"deleted {deleted_count} training example(s) for doc '{doc.filename}'",
    )

    # Remove the document record if it was a training placeholder
    if doc.status == "training":
        db.session.delete(doc)

    db.session.commit()

    flash(f"Sample deleted ({deleted_count} field(s) removed).", "success")
    return redirect(url_for("training.examples_list"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rebuild_rag_embeddings(document_id: int) -> None:
    """Attempt to rebuild RAG embeddings for *document_id* after training data update."""
    try:
        import os
        from services.rag_service import RAGService  # type: ignore[import]

        doc = Document.query.get(document_id)
        if doc is None or not doc.file_path:
            return

        import sys
        _root = current_app.root_path
        _backend = os.path.join(_root, "backend")
        if _backend not in sys.path:
            sys.path.append(_backend)

        from services.pdf_service import PDFService  # type: ignore[import]

        pdf_svc = PDFService()
        if not os.path.exists(doc.file_path):
            return

        text, _tables, _pages = pdf_svc.extract(doc.file_path)
        rag_dir = os.path.join(_root, os.environ.get("RAG_DIR", "rag_data"))
        rag_svc = RAGService(rag_dir=rag_dir)
        rag_svc.save_rag_text(str(document_id), text)
        current_app.logger.info(
            "TrainingService: rebuilt RAG embeddings for doc %s", document_id
        )
    except Exception as exc:  # pragma: no cover
        current_app.logger.warning(
            "TrainingService: could not rebuild RAG embeddings for doc %s: %s",
            document_id,
            exc,
        )


def _log(
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: str,
    details: str = "",
) -> None:
    """Insert an AuditLog entry (caller must commit the session)."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or None,
    )
    db.session.add(entry)
