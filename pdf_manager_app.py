#!/usr/bin/env python3
"""
pdf_manager_app.py — Root-level PDF Manager entry point.

Detects whether the full repository is present, warns about unsupported Python
versions, and delegates to the backend application module.

Usage
-----
    # Start the application (auto-detects backend)
    python pdf_manager_app.py

    # Run a quick OCR demo on a PDF file
    python pdf_manager_app.py demo path/to/file.pdf

    # Interactively upload and process sample PDF files with RAG extraction
    python pdf_manager_app.py sample
"""

import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Python version check
# ---------------------------------------------------------------------------
_PY = sys.version_info
if _PY < (3, 11) or _PY >= (3, 14):
    print(
        f"Warning: Python {_PY.major}.{_PY.minor} is outside the recommended "
        "range 3.11–3.13.  Some dependencies may not have pre-built wheels for "
        "this version.",
        file=sys.stderr,
    )

# ---------------------------------------------------------------------------
# Repository / backend detection
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_SCRIPT_DIR, "backend")

if not os.path.isdir(_BACKEND_DIR):
    print(
        "Error: backend/ directory not found.\n\n"
        "Setup instructions:\n"
        "  1. Clone the full repository:\n"
        "       git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git\n"
        "       cd PDF-Manager\n"
        "  2. Install Python dependencies:\n"
        "       pip install -r backend/requirements.txt\n"
        "  3. (Optional) Install Tesseract OCR for scanned PDFs:\n"
        "       https://github.com/tesseract-ocr/tesseract\n"
        "  4. Start the application:\n"
        "       python pdf_manager_app.py\n",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------
print("=" * 60)
print("  PDF Manager")
print("=" * 60)
print()
print("Docker Compose (recommended):")
print("  docker compose up --build")
print()
print("Manual startup:")
print("  cd backend")
print("  pip install -r requirements.txt")
print("  python pdf_manager_app.py")
print()
print("Sub-commands:")
print("  demo <pdf_path>  —  run OCR extraction on a single PDF and")
print("                       print the mapped address-book fields.")
print("  sample           —  interactively upload and process PDF files")
print("                       using the full RAG extraction pipeline.")
print()

# ---------------------------------------------------------------------------
# 'demo' sub-command
# ---------------------------------------------------------------------------
if len(sys.argv) >= 2 and sys.argv[1] == "demo":
    if len(sys.argv) < 3:
        print("Usage: python pdf_manager_app.py demo <path/to/file.pdf>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[2]
    if not os.path.isfile(pdf_path):
        print(f"Error: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Add backend to sys.path so services can be imported
    if _BACKEND_DIR not in sys.path:
        sys.path.insert(0, _BACKEND_DIR)

    try:
        from services.pdf_service import PDFService  # type: ignore[import]
        import json

        svc = PDFService()
        text, tables, pages = svc.extract(pdf_path)
        mapped = svc.map_address_book_fields(text)
        print(f"Extracted {pages} page(s) from: {pdf_path}\n")
        print("Mapped address-book fields:")
        print(json.dumps(mapped, indent=2, ensure_ascii=False))
    except (ImportError, ModuleNotFoundError) as exc:
        print(
            f"Error: Could not import PDF service — {exc}\n"
            "Run:  pip install -r backend/requirements.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(0)

# ---------------------------------------------------------------------------
# 'sample' sub-command — interactive batch PDF upload with RAG extraction
# ---------------------------------------------------------------------------
if len(sys.argv) >= 2 and sys.argv[1] == "sample":
    # Add backend to sys.path so the CLI module and services can be imported
    if _BACKEND_DIR not in sys.path:
        sys.path.insert(0, _BACKEND_DIR)

    try:
        from cli.sample_uploader import SampleUploader  # type: ignore[import]
    except (ImportError, ModuleNotFoundError) as exc:
        print(
            f"Error: Could not import SampleUploader — {exc}\n"
            "Run:  pip install -r backend/requirements.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    uploader = SampleUploader(backend_dir=_BACKEND_DIR)
    uploader.run()
    sys.exit(0)

# ---------------------------------------------------------------------------
# Load and run the backend application
# ---------------------------------------------------------------------------
_BACKEND_APP = os.path.join(_BACKEND_DIR, "pdf_manager_app.py")
_FALLBACK_APP = os.path.join(_SCRIPT_DIR, "app.py")

_target = _BACKEND_APP if os.path.isfile(_BACKEND_APP) else _FALLBACK_APP

try:
    spec = importlib.util.spec_from_file_location("_pdf_manager_app_impl", _target)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {_target}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    if hasattr(module, "main"):
        module.main()
    elif hasattr(module, "app"):
        # Flask app — run directly
        port = int(os.environ.get("PORT", 5000))
        debug = os.environ.get("DEBUG", "false").lower() == "true"
        module.app.run(host="0.0.0.0", port=port, debug=debug)

except (ImportError, ModuleNotFoundError) as exc:
    print(
        f"Error: Failed to load application — {exc}\n\n"
        "Please ensure all dependencies are installed:\n"
        "  pip install -r backend/requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1) 
