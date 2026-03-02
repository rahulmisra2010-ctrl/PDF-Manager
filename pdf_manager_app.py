"""
Root-level entry point for PDF-Manager.

This file lets users run ``python pdf_manager_app.py`` directly from the
repo root AND import ``PDFManagerApp`` from any script inside the repo
without having to ``cd backend`` first.

  ⚠️  Do NOT name your own script ``pdf_manager_app.py``.
      Call it something like ``my_script.py`` or ``run_example.py`` instead.
      Using the same name causes a circular-import error.

Usage as a module (import from a differently-named script)::

    # my_script.py  ← note: NOT pdf_manager_app.py
    from pdf_manager_app import PDFManagerApp

    app = PDFManagerApp()

    with open("invoice.pdf", "rb") as f:
        resp = app.upload("invoice.pdf", f.read())

    result = app.extract(resp.document_id)
    print(result.fields)

    path = app.export(resp.document_id, fmt="json")
    print("Saved to:", path)

Usage as a script (shows setup instructions)::

    python pdf_manager_app.py

"""

import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Load backend/pdf_manager_app.py directly by file path so there is never a
# name collision with *this* root-level wrapper file.
# ---------------------------------------------------------------------------
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_ROOT_DIR, "backend")
_IMPL_PATH = os.path.join(_BACKEND_DIR, "pdf_manager_app.py")

# backend/ must be on sys.path so that the implementation's own sibling
# imports (config, models, services.*) resolve correctly.
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_spec = importlib.util.spec_from_file_location("_pdf_manager_app_impl", _IMPL_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Re-export the public class at this module's top level.
PDFManagerApp = _mod.PDFManagerApp


def _print_usage() -> None:
    """Print a quick-start guide showing setup and usage instructions."""
    print(
        """
PDF-Manager – Quick-Start
=========================

Step 1 – Clone the full repository (if you haven't already):

    git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
    cd PDF-Manager

Step 2 – Install dependencies (run once from the repo root):

    pip install -r requirements.txt

Step 3 – Create YOUR script with a different name (e.g. my_script.py).
         ⚠️  Do NOT name it pdf_manager_app.py – that causes a circular import!

    # my_script.py
    from pdf_manager_app import PDFManagerApp

    app = PDFManagerApp()

    # Upload – replace "invoice.pdf" with the path to your PDF file
    with open("invoice.pdf", "rb") as f:
        resp = app.upload("invoice.pdf", f.read())

    # Extract text and fields
    result = app.extract(resp.document_id)
    print(result.fields)

    # Export (supports "json", "csv", or "pdf")
    path = app.export(resp.document_id, fmt="json")
    print("Saved to:", path)

Step 4 – Run your script from the repo root:

    python my_script.py

For full documentation see README.md or docs/SETUP.md.
"""
    )


if __name__ == "__main__":
    _print_usage()
