"""
blueprints/bot.py — Form-image/PDF-to-fillable-PDF bot blueprint.

Routes
------
GET  /bot/                     — upload page (accepts images and PDFs)
POST /bot/process              — run OCR → NLP → PDF pipeline, redirect to viewer
GET  /bot/viewer/<token>       — interactive PDF viewer with editable fields
GET  /bot/serve-pdf/<token>    — serve raw PDF for PDF.js viewer
POST /bot/save/<token>         — save edited fields and regenerate PDF
GET  /bot/download/<token>     — download the generated fillable PDF
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import login_required
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

bot_bp = Blueprint("bot", __name__, template_folder="../templates/bot")

# Allowed image extensions
_ALLOWED_IMAGE_EXTENSIONS = frozenset(
    {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "tif", "webp"}
)

# Allowed PDF extension
_ALLOWED_PDF_EXTENSION = "pdf"

# All allowed extensions
_ALLOWED_EXTENSIONS = _ALLOWED_IMAGE_EXTENSIONS | {_ALLOWED_PDF_EXTENSION}

# In-memory store for generated PDFs keyed by a one-time token.
# Each entry stores: {"pdf_bytes": bytes, "fields": list, "structured": dict}
_pdf_store: dict[str, dict[str, Any]] = {}

# Precompiled token validation regex
_TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{43}$')


def _allowed(filename: str) -> bool:
    """Check if the filename has an allowed extension."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in _ALLOWED_EXTENSIONS
    )


def _is_pdf(filename: str) -> bool:
    """Check if the filename is a PDF."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() == _ALLOWED_PDF_EXTENSION
    )


def _is_image(filename: str) -> bool:
    """Check if the filename is an image."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in _ALLOWED_IMAGE_EXTENSIONS
    )


def _backend_service():
    """Lazily import the bot service (keeps import errors isolated)."""
    import sys

    _here = Path(__file__).resolve().parent  # blueprints/
    _backend = (_here / ".." / "backend").resolve()
    if str(_backend) not in sys.path:
        sys.path.insert(0, str(_backend))

    from services.bot_service import (  # type: ignore
        image_to_fillable_pdf,
        pdf_to_fillable_pdf,
        generate_fillable_pdf,
        structure_text,
    )
    return {
        "image_to_fillable_pdf": image_to_fillable_pdf,
        "pdf_to_fillable_pdf": pdf_to_fillable_pdf,
        "generate_fillable_pdf": generate_fillable_pdf,
        "structure_text": structure_text,
    }


def _validate_token(token: str) -> bool:
    """Validate that the token matches expected format."""
    return bool(token and _TOKEN_RE.fullmatch(token))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bot_bp.route("/", methods=["GET"])
@login_required
def index():
    """Render the bot upload page."""
    return render_template("bot/index.html")


@bot_bp.route("/process", methods=["POST"])
@login_required
def process():
    """
    Accept an uploaded form image or PDF, run the processing pipeline,
    and redirect to the interactive viewer.
    """
    if "form_image" not in request.files:
        flash("No file part in the request.", "danger")
        return redirect(url_for("bot.index"))

    file = request.files["form_image"]
    if file.filename == "":
        flash("No file selected.", "danger")
        return redirect(url_for("bot.index"))

    if not _allowed(file.filename):
        flash(
            "Unsupported file type. Please upload a PNG, JPG, TIFF, PDF, or similar file.",
            "danger",
        )
        return redirect(url_for("bot.index"))

    # Save to a temporary file for processing
    suffix = Path(secure_filename(file.filename)).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        services = _backend_service()
        
        if _is_pdf(file.filename):
            # Process PDF file
            pdf_bytes, structured = services["pdf_to_fillable_pdf"](tmp_path)
        else:
            # Process image file
            pdf_bytes, structured = services["image_to_fillable_pdf"](tmp_path)
            
    except Exception as exc:  # noqa: BLE001
        logger.exception("Bot pipeline failed")
        flash(f"Processing failed: {exc}", "danger")
        return redirect(url_for("bot.index"))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Store PDF and field data under a token
    token = secrets.token_urlsafe(32)
    fields = structured.get("fields", [])
    _pdf_store[token] = {
        "pdf_bytes": pdf_bytes,
        "fields": fields,
        "structured": structured,
    }

    # Redirect to the interactive viewer
    return redirect(url_for("bot.viewer", token=token))


@bot_bp.route("/viewer/<token>")
@login_required
def viewer(token: str):
    """
    Render the interactive PDF viewer with editable fields.
    
    The viewer displays the PDF with form field overlays and a side panel
    for editing field values. Users can edit fields directly on the PDF
    or in the side panel, and save/export the result.
    """
    if not _validate_token(token):
        flash("Invalid viewer link.", "danger")
        return redirect(url_for("bot.index"))

    data = _pdf_store.get(token)
    if data is None:
        flash("Viewer link has expired or is invalid.", "warning")
        return redirect(url_for("bot.index"))

    fields = data.get("fields", [])
    pdf_url = url_for("bot.serve_pdf", token=token)

    return render_template(
        "bot/viewer.html",
        fields=fields,
        field_count=len(fields),
        token=token,
        pdf_url=pdf_url,
    )


@bot_bp.route("/serve-pdf/<token>")
@login_required
def serve_pdf(token: str):
    """Serve the raw PDF for the PDF.js viewer."""
    if not _validate_token(token):
        return Response("Invalid token.", status=400)

    data = _pdf_store.get(token)
    if data is None:
        return Response("PDF not found or expired.", status=404)

    pdf_bytes = data.get("pdf_bytes")
    if not pdf_bytes:
        return Response("PDF data not available.", status=404)

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name="form.pdf",
    )


@bot_bp.route("/save/<token>", methods=["POST"])
@login_required
def save_edited(token: str):
    """
    Save edited field values and regenerate the fillable PDF.
    
    Accepts JSON field data from the viewer, regenerates the PDF with
    updated values, and redirects to download the new PDF.
    """
    if not _validate_token(token):
        flash("Invalid save link.", "danger")
        return redirect(url_for("bot.index"))

    data = _pdf_store.get(token)
    if data is None:
        flash("Session has expired. Please upload the form again.", "warning")
        return redirect(url_for("bot.index"))

    # Parse the updated fields from the form
    fields_json = request.form.get("fields_json", "[]")
    try:
        updated_fields = json.loads(fields_json)
    except json.JSONDecodeError:
        flash("Invalid field data received.", "danger")
        return redirect(url_for("bot.viewer", token=token))

    # Validate and sanitize field data
    sanitized_fields = []
    for f in updated_fields:
        if not isinstance(f, dict):
            continue
        sanitized_fields.append({
            "label": str(f.get("label", ""))[:200],
            "value": str(f.get("value", ""))[:2000],
            "type": str(f.get("type", "text"))[:20],
        })

    # Regenerate the PDF with updated field values
    try:
        services = _backend_service()
        structured = {"fields": sanitized_fields}
        new_pdf_bytes = services["generate_fillable_pdf"](structured)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to regenerate PDF")
        flash(f"Failed to save: {exc}", "danger")
        return redirect(url_for("bot.viewer", token=token))

    # Create a new token for the updated PDF download
    new_token = secrets.token_urlsafe(32)
    _pdf_store[new_token] = {
        "pdf_bytes": new_pdf_bytes,
        "fields": sanitized_fields,
        "structured": structured,
    }

    # Clean up old token to prevent memory bloat
    _pdf_store.pop(token, None)

    flash("PDF saved successfully! Your download should start automatically.", "success")
    return redirect(url_for("bot.download", token=new_token))


@bot_bp.route("/download/<token>")
@login_required
def download(token: str):
    """Stream the generated fillable PDF to the browser for download."""
    if not _validate_token(token):
        return Response("Invalid token.", status=400)

    data = _pdf_store.get(token)
    if data is None:
        flash("Download link has expired or is invalid.", "warning")
        return redirect(url_for("bot.index"))

    pdf_bytes = data.get("pdf_bytes")
    if not pdf_bytes:
        flash("PDF data not available.", "danger")
        return redirect(url_for("bot.index"))

    # Don't pop the data yet — allow multiple downloads and continued viewing
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="fillable_form.pdf",
    )
