"""
logging_config.py — Centralized logging configuration for PDF-Manager.

Sets up structured logging with timestamps, writing to both the console
and a rotating file at ``logs/app.log``.  Import and call
``setup_logging()`` once at application startup.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# Default log level; can be overridden via the LOG_LEVEL env var
_DEFAULT_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger with console and rotating-file handlers.

    Args:
        level: Optional log level string (e.g. ``"DEBUG"``).  Defaults to
               the ``LOG_LEVEL`` environment variable, or ``"INFO"``.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    log_level = getattr(logging, (level or _DEFAULT_LEVEL), logging.INFO)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # --- Console handler ---------------------------------------------------
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # --- Rotating file handler (10 MB, keep 5 backups) --------------------
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called more than once
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
