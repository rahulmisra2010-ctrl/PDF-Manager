"""
blueprints/bot.py — Form-image/PDF-to-fillable-PDF bot blueprint.

Routes
------
GET  /bot/                      — upload page
POST /bot/process               — run OCR → NLP → PDF pipeline, show preview
GET  /bot/viewer/<token>        — interactive PDF viewer with editable fields
POST /bot/save/<token>          — save edited field values and regenerate PDF
GET  /bot/serve-pdf/<token>     — serve the raw PDF for PDF.js
GET  /bot/download/<token>      — download the generated fillable PDF
"""

from __future__ import annotations

import csv
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
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import login_required
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

bot_bp = Blueprint("bot", __name__, template_folder="../templates/bot")

# Allowed file extensions (images + PDF)
_ALLOWED_IMAGE_EXTENSIONS = frozenset(
    {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "tif", "webp"}
)
_ALLOWED_PDF_EXTENSION = "pdf"
_ALLOWED_EXTENSIONS = _ALLOWED_IMAGE_EXTENSIONS | {_ALLOWED_PDF_EXTENSION}

# In-memory store for generated PDFs and field data keyed by a one-time token.
# This is intentionally simple — tokens expire when the server restarts.
# Structure: {token: {"pdf_bytes": bytes, "fields": list, "withdrawal_reasons": list}}
_pdf_store: dict[str, dict[str, Any]] = {}


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


def _backend_service():
    """Lazily import the bot service (keeps import errors isolated)."""
    import sys

    _here = Path(__file__).resolve().parent  # blueprints/
    _backend = (_here / ".." / "backend").resolve()
    if str(_backend) not in sys.path:
        sys.path.insert(0, str(_backend))

    from services.bot_service import file_to_fillable_pdf, generate_fillable_pdf
    return file_to_fillable_pdf, generate_fillable_pdf


def _validate_token(token: str) -> bool:
    """Validate that the token matches the expected format."""
    _TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{43}$')
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
    Accept an uploaded form image or PDF, run the full pipeline, and show
    a preview of extracted fields plus links to view/edit and download.
    """
    if "form_file" not in request.files:
        flash("No file part in the request.", "danger")
        return redirect(url_for("bot.index"))

    file = request.files["form_file"]
    if file.filename == "":
        flash("No file selected.", "danger")
        return redirect(url_for("bot.index"))

    if not _allowed(file.filename):
        flash(
            "Unsupported file type. Please upload a PDF, PNG, JPG, TIFF, or similar image.",
            "danger",
        )
        return redirect(url_for("bot.index"))

    # Save to a temporary file for processing
    suffix = Path(secure_filename(file.filename)).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        file_to_fillable_pdf, _ = _backend_service()
        pdf_bytes, structured = file_to_fillable_pdf(tmp_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Bot pipeline failed")
        flash(f"Processing failed: {exc}", "danger")
        return redirect(url_for("bot.index"))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Store PDF and field data under a one-time token
    token = secrets.token_urlsafe(32)
    _pdf_store[token] = {
        "pdf_bytes": pdf_bytes,
        "fields": structured.get("fields", []),
        "withdrawal_reasons": structured.get("withdrawal_reasons", []),
    }

    fields = structured.get("fields", [])
    withdrawal_reasons = structured.get("withdrawal_reasons", [])

    return render_template(
        "bot/result.html",
        fields=fields,
        withdrawal_reasons=withdrawal_reasons,
        token=token,
        field_count=len(fields),
    )


@bot_bp.route("/viewer/<token>")
@login_required
def viewer(token: str):
    """
    Render the interactive PDF viewer with editable fields.
    
    All fields can be edited directly in the viewer overlay or in the
    side panel form. Changes can be saved and exported.
    """
    if not _validate_token(token):
        flash("Invalid token.", "danger")
        return redirect(url_for("bot.index"))

    data = _pdf_store.get(token)
    if data is None:
        flash("Session has expired. Please upload a new file.", "warning")
        return redirect(url_for("bot.index"))

    fields = data.get("fields", [])
    pdf_url = url_for("bot.serve_pdf", token=token)

    return render_template(
        "bot/viewer.html",
        token=token,
        fields=fields,
        fields_json=json.dumps(fields),
        pdf_url=pdf_url,
        field_count=len(fields),
    )


@bot_bp.route("/serve-pdf/<token>")
@login_required
def serve_pdf(token: str):
    """Serve the raw PDF file so PDF.js can load it in the browser."""
    if not _validate_token(token):
        return Response("Invalid token.", status=400)

    data = _pdf_store.get(token)
    if data is None:
        return Response("PDF not found or session expired.", status=404)

    return send_file(
        io.BytesIO(data["pdf_bytes"]),
        mimetype="application/pdf",
    )


@bot_bp.route("/save/<token>", methods=["POST"])
@login_required
def save_fields(token: str):
    """
    Save edited field values and regenerate the fillable PDF.
    
    Accepts JSON: {"fields": [...]}
    Returns JSON: {"success": true, "message": "..."}
    """
    if not _validate_token(token):
        return jsonify({"success": False, "error": "Invalid token."}), 400

    data = _pdf_store.get(token)
    if data is None:
        return jsonify({"success": False, "error": "Session expired."}), 404

    try:
        payload = request.get_json()
        if not payload or "fields" not in payload:
            return jsonify({"success": False, "error": "Missing fields data."}), 400

        new_fields = payload["fields"]
        
        # Update stored fields
        data["fields"] = new_fields
        
        # Regenerate PDF with updated values
        _, generate_fillable_pdf = _backend_service()
        structured = {
            "fields": new_fields,
            "withdrawal_reasons": data.get("withdrawal_reasons", []),
        }
        data["pdf_bytes"] = generate_fillable_pdf(structured)
        
        return jsonify({
            "success": True,
            "message": f"Saved {len(new_fields)} field(s) successfully.",
        })

    except Exception:
        logger.exception("Failed to save fields")
        return jsonify({"success": False, "error": "An error occurred while saving fields."}), 500


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

    return send_file(
        io.BytesIO(data["pdf_bytes"]),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="fillable_form.pdf",
    )


@bot_bp.route("/export/<token>/<fmt>")
@login_required
def export_fields(token: str, fmt: str):
    """Export field data in various formats (json, csv)."""
    if not _validate_token(token):
        return Response("Invalid token.", status=400)

    data = _pdf_store.get(token)
    if data is None:
        return Response("Session expired.", status=404)

    fields = data.get("fields", [])

    if fmt == "json":
        return Response(
            json.dumps(fields, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=fields.json"},
        )
    elif fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Label", "Value", "Type"])
        for field in fields:
            writer.writerow([
                field.get("label", ""),
                field.get("value", ""),
                field.get("type", "text"),
            ])
        
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=fields.csv"},
        )
    else:
        return Response("Unsupported format. Use 'json' or 'csv'.", status=400)
