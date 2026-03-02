"""
Root-level entry point for PDF-Manager.

Run this file from the repo root to see setup instructions::

    python pdf_manager_app.py

To use PDFManagerApp in your own script, create a file with a DIFFERENT name
(e.g. ``my_script.py``) inside the cloned repo and write::

    from pdf_manager_app import PDFManagerApp

    app = PDFManagerApp()

    with open("invoice.pdf", "rb") as f:
        resp = app.upload("invoice.pdf", f.read())

    result = app.extract(resp.document_id)
    print(result.fields)

    path = app.export(resp.document_id, fmt="json")
    print("Saved to:", path)

NOTE: Do NOT name your script ``pdf_manager_app.py`` – it has the same name
as this file and will cause a circular-import error.
"""

import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Locate the backend implementation.
# ---------------------------------------------------------------------------
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_ROOT_DIR, "backend")
_IMPL_PATH = os.path.join(_BACKEND_DIR, "pdf_manager_app.py")

_SETUP_MESSAGE = """\
================================================================
  PDF-Manager – setup required
================================================================

It looks like you only have this single file.
You need the FULL repository to run PDF-Manager.

Step 1 – Clone the full repository in a terminal / command prompt:

    git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
    cd PDF-Manager

Step 2 – Install dependencies (run once):

    pip install -r requirements.txt

Step 3 – Run this file again from inside the cloned folder:

    python pdf_manager_app.py

  You will then see usage instructions and a working example.

For full documentation see README.md or docs/SETUP.md.
================================================================
"""

_USAGE_MESSAGE = """\
================================================================
  PDF-Manager – Quick-Start
================================================================

The PDF-Manager library is ready to use.

Create a script with a DIFFERENT name (e.g. my_script.py) and
write the following – do NOT name it pdf_manager_app.py:

    from pdf_manager_app import PDFManagerApp

    app = PDFManagerApp()

    # Upload a PDF file
    with open("invoice.pdf", "rb") as f:
        resp = app.upload("invoice.pdf", f.read())

    # Extract text and fields
    result = app.extract(resp.document_id)
    print(result.fields)

    # Export (supports "json", "csv", or "pdf")
    path = app.export(resp.document_id, fmt="json")
    print("Saved to:", path)

Then run from this directory:

    python my_script.py

For full documentation see README.md or docs/SETUP.md.
================================================================
"""


def _load_backend():
    """Load backend/pdf_manager_app.py by file path and return the module."""
    if not os.path.isfile(_IMPL_PATH):
        return None
    # Put backend/ on sys.path so sibling imports (config, models, services.*)
    # resolve correctly inside the implementation module.
    if _BACKEND_DIR not in sys.path:
        sys.path.insert(0, _BACKEND_DIR)
    spec = importlib.util.spec_from_file_location("_pdf_manager_app_impl", _IMPL_PATH)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except (ImportError, ModuleNotFoundError):
        return None
    return mod


# ---------------------------------------------------------------------------
# Try to load the backend at import time so that
#   from pdf_manager_app import PDFManagerApp
# works when the full repo is present.  If it isn't, fall back to a stub
# that gives a clear error message instead of a confusing traceback.
# ---------------------------------------------------------------------------
_backend = _load_backend()

if _backend is not None:
    PDFManagerApp = _backend.PDFManagerApp
else:
    class PDFManagerApp:  # type: ignore[no-redef]
        """Stub raised when the backend directory is not present.

        Instantiating this class raises a ``RuntimeError`` with instructions
        on how to clone the full repository.
        """

        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "PDFManagerApp is not available because the backend/ directory "
                "was not found.\n\n"
                + _SETUP_MESSAGE
            )


if __name__ == "__main__":
    if _backend is None:
        print(_SETUP_MESSAGE)
        sys.exit(1)
    print(_USAGE_MESSAGE)
