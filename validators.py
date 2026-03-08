"""
validators.py — Custom input validators for PDF-Manager.

Provides WTForms-compatible validators and standalone helper functions for:
* PDF file type checking
* File size limits (default 50 MB)
* Field name / value format checks
"""

from __future__ import annotations

import os
import re

from wtforms import ValidationError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_MB: int = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf"})
MAX_FIELD_NAME_LENGTH: int = 100
MAX_FIELD_VALUE_LENGTH: int = 10_000


# ---------------------------------------------------------------------------
# Standalone helper functions
# ---------------------------------------------------------------------------

def allowed_file(filename: str) -> bool:
    """Return *True* if *filename* has a permitted extension."""
    if not filename:
        return False
    _, ext = os.path.splitext(filename)
    return ext.lower().lstrip(".") in ALLOWED_EXTENSIONS


def validate_file_size(file_size: int) -> None:
    """Raise :class:`ValueError` if *file_size* exceeds the configured limit.

    Args:
        file_size: Size of the uploaded file in bytes.

    Raises:
        ValueError: When the file is too large.
    """
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File size ({file_size / (1024 * 1024):.1f} MB) exceeds the "
            f"{MAX_FILE_SIZE_MB} MB limit."
        )


def validate_field_name(name: str) -> None:
    """Raise :class:`ValueError` for invalid field names.

    A valid field name must:
    * be non-empty
    * not exceed :data:`MAX_FIELD_NAME_LENGTH` characters
    * contain only letters, digits, spaces, underscores, or hyphens

    Args:
        name: The field name string to validate.

    Raises:
        ValueError: When the name fails validation.
    """
    if not name or not name.strip():
        raise ValueError("Field name must not be empty.")
    if len(name) > MAX_FIELD_NAME_LENGTH:
        raise ValueError(
            f"Field name must not exceed {MAX_FIELD_NAME_LENGTH} characters."
        )
    if not re.match(r"^[\w\s\-]+$", name):
        raise ValueError(
            "Field name may only contain letters, digits, spaces, "
            "underscores, or hyphens."
        )


def validate_field_value(value: str | None) -> None:
    """Raise :class:`ValueError` when *value* is too long.

    Args:
        value: The field value string to validate (may be ``None``).

    Raises:
        ValueError: When the value exceeds :data:`MAX_FIELD_VALUE_LENGTH`.
    """
    if value is not None and len(value) > MAX_FIELD_VALUE_LENGTH:
        raise ValueError(
            f"Field value must not exceed {MAX_FIELD_VALUE_LENGTH} characters."
        )


# ---------------------------------------------------------------------------
# WTForms validators
# ---------------------------------------------------------------------------

class FileSizeLimit:
    """WTForms field validator that rejects files larger than *max_mb* MB."""

    def __init__(self, max_mb: int = MAX_FILE_SIZE_MB) -> None:
        self.max_mb = max_mb
        self.max_bytes = max_mb * 1024 * 1024

    def __call__(self, form, field) -> None:  # noqa: ANN001
        uploaded = getattr(field, "data", None)
        if uploaded is None:
            return
        # Seek to end to determine size without reading entire file
        uploaded.seek(0, 2)
        size = uploaded.tell()
        uploaded.seek(0)
        if size > self.max_bytes:
            raise ValidationError(
                f"File size ({size / (1024 * 1024):.1f} MB) exceeds the "
                f"{self.max_mb} MB limit."
            )


class PDFFileType:
    """WTForms field validator that ensures the uploaded file is a PDF."""

    def __call__(self, form, field) -> None:  # noqa: ANN001
        uploaded = getattr(field, "data", None)
        if uploaded is None:
            return
        filename = getattr(uploaded, "filename", "") or ""
        if not allowed_file(filename):
            raise ValidationError("Only PDF files are accepted.")


class FieldNameValidator:
    """WTForms field validator for extracted-field names."""

    def __call__(self, form, field) -> None:  # noqa: ANN001
        try:
            validate_field_name(field.data or "")
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class FieldValueValidator:
    """WTForms field validator for extracted-field values."""

    def __call__(self, form, field) -> None:  # noqa: ANN001
        try:
            validate_field_value(field.data)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
