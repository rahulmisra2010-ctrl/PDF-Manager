"""
backend/pdf_manager_app.py — Backend application entry point.

Thin wrapper that imports and runs the root Flask application.  This file
exists so that ``python backend/pdf_manager_app.py`` and the root-level
``pdf_manager_app.py`` both work correctly.
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Make the repository root importable so that ``import app`` finds root/app.py
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_BACKEND_DIR)

# Ensure backend/ is on sys.path for services/config etc.
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Ensure root is on sys.path for models, blueprints, app etc.
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)


def main() -> None:
    """Start the Flask application."""
    try:
        from app import app  # type: ignore[import]  # root app.py

        port = int(os.environ.get("PORT", 5000))
        debug = os.environ.get("DEBUG", "false").lower() == "true"
        app.run(host="0.0.0.0", port=port, debug=debug)
    except (ImportError, ModuleNotFoundError) as exc:
        print(
            f"Error: Could not start the application — {exc}\n"
            "Please install dependencies:\n"
            "  pip install -r backend/requirements.txt",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
