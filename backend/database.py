"""
backend/database.py — SQLAlchemy database helper.

Provides a thin wrapper around the shared ``db`` object from ``models.py``.
Import ``db`` and ``init_db`` here when working in the backend package context.
"""

from __future__ import annotations

import os
import sys

# Ensure root package is importable
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from models import db  # noqa: E402


def init_db(app) -> None:
    """
    Initialise the database with the given Flask application.

    Creates all tables defined in models.py.  Call this inside an
    app context when setting up a standalone backend process.
    """
    db.init_app(app)
    with app.app_context():
        db.create_all()


__all__ = ["db", "init_db"]
