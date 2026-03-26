"""
blueprints/bot.py — Form-image-to-fillable-PDF bot blueprint.

Routes
------
GET  /bot/                  — upload page
POST /bot/process           — run OCR → NLP → PDF pipeline, show preview
GET  /bot/download/<token>  — download the generated fillable PDF
"""

from __future__ import annotations

import io
import logging
import os
import re
import secrets
import tempfile
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
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

# Allowed image extensions
_ALLOWED_EXTENSIONS = frozenset(
    {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "tif", "webp"}
)

# In-memory store for generated PDFs keyed by a one-time token.
# This is intentionally simple — tokens expire when the server restarts.
_pdf_store: dict[str, bytes] = {}


def _allowed(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in _ALLOWED_EXTENSIONS
    )


def _backend_service():
    """Lazily import the bot service (keeps import errors isolated)."""
    import sys

    _here = Path(__file__).resolve().parent  # blueprints/
    _backend = (_here / ".." / "backend").resolve()
    if str(_backend) not in sys.path:
        sys.path.insert(0, str(_backend))

    from services.bot_service import image_to_fillable_pdf  # type: ignore
    return image_to_fillable_pdf


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
    Accept an uploaded form image, run the full pipeline, and show a preview
    of extracted fields plus a link to download the fillable PDF.
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
            "Unsupported file type. Please upload a PNG, JPG, TIFF, or similar image.",
            "danger",
        )
        return redirect(url_for("bot.index"))

    # Save to a temporary file for OCR
    suffix = Path(secure_filename(file.filename)).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        pipeline = _backend_service()
        pdf_bytes, structured = pipeline(tmp_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Bot pipeline failed")
        flash(f"Processing failed: {exc}", "danger")
        return redirect(url_for("bot.index"))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Store PDF under a one-time token
    token = secrets.token_urlsafe(32)
    _pdf_store[token] = pdf_bytes

    fields = structured.get("fields", [])
    withdrawal_reasons = structured.get("withdrawal_reasons", [])

    return render_template(
        "bot/result.html",
        fields=fields,
        withdrawal_reasons=withdrawal_reasons,
        token=token,
        field_count=len(fields),
    )


@bot_bp.route("/download/<token>")
@login_required
def download(token: str):
    """Stream the previously generated fillable PDF to the browser."""
    # Validate token: secrets.token_urlsafe(32) always produces 43 URL-safe chars
    _TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{43}$')
    if not token or not _TOKEN_RE.fullmatch(token):
        return Response("Invalid token.", status=400)

    pdf_bytes = _pdf_store.pop(token, None)
    if pdf_bytes is None:
        flash("Download link has expired or is invalid.", "warning")
        return redirect(url_for("bot.index"))

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="fillable_form.pdf",
    )
