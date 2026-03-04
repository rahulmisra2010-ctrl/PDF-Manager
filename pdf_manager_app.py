"""
pdf_manager_app.py – PDF-Manager standalone helper.

Run this file directly to check your setup, view usage instructions, or run a
quick extraction demo on a local PDF file.

Usage
-----
    python pdf_manager_app.py                       # show status / help
    python pdf_manager_app.py demo path/to/file.pdf # quick extraction demo
"""

import os
import sys

_SEPARATOR = "=" * 64
_REPO_URL = "https://github.com/rahulmisra2010-ctrl/PDF-Manager.git"
_MIN_PYTHON = (3, 11)
_MAX_PYTHON = (3, 13)  # highest tested; newer versions may work but are untested


# ---------------------------------------------------------------------------
# Environment checks
# ---------------------------------------------------------------------------


def _check_python_version() -> bool:
    """Print a warning / error if the Python version is unsuitable."""
    ver = sys.version_info
    if ver < _MIN_PYTHON:
        print(_SEPARATOR)
        print("  PDF-Manager – Python version too old")
        print(_SEPARATOR)
        print()
        print(
            f"This project requires Python {_MIN_PYTHON[0]}.{_MIN_PYTHON[1]} "
            f"or later."
        )
        print(f"You are running Python {ver.major}.{ver.minor}.{ver.micro}.")
        print()
        print(
            "Please install Python 3.11 or later from "
            "https://www.python.org/downloads/"
        )
        print(_SEPARATOR)
        return False

    if ver > _MAX_PYTHON:
        print(
            f"Warning: Python {ver.major}.{ver.minor} has not been tested with "
            f"this project. Python {_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}–"
            f"{_MAX_PYTHON[0]}.{_MAX_PYTHON[1]} is recommended."
        )
        print(
            "Some dependencies (e.g. numpy, torch) may not yet supply "
            "pre-built wheels for your Python version."
        )
        print()

    return True


def _check_repo_present() -> bool:
    """Return True if the full repository structure is present."""
    here = os.path.dirname(os.path.abspath(__file__))
    required = ["backend", "frontend", "database", "docs", "docker-compose.yml"]
    return all(os.path.exists(os.path.join(here, name)) for name in required)


def _check_dependencies() -> list:
    """Return a list of pip package names that are not importable."""
    packages = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "fitz": "PyMuPDF",
        "cv2": "opencv-python-headless",
        "torch": "torch",
        "pydantic": "pydantic",
    }
    missing = []
    for module, pip_name in packages.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(pip_name)
    return missing


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_setup_instructions() -> None:
    print(_SEPARATOR)
    print("  PDF-Manager – setup required")
    print(_SEPARATOR)
    print()
    print("It looks like you only have this single file.")
    print("You need the FULL repository to run PDF-Manager.")
    print()
    print(
        "Step 1 – Clone the full repository in a terminal / command prompt:"
    )
    print()
    print(f"    git clone {_REPO_URL}")
    print( "    cd PDF-Manager")
    print()
    print("Step 2 – Install dependencies (run once):")
    print()
    print( "    pip install -r requirements.txt")
    print()
    print("Step 3 – Run this file again from inside the cloned folder:")
    print()
    print( "    python pdf_manager_app.py")
    print()
    print("  You will then see usage instructions and a working example.")
    print()
    print("For full documentation see README.md or docs/SETUP.md.")
    print(_SEPARATOR)
    print()


def _print_usage(missing: list) -> None:
    print(_SEPARATOR)
    print("  PDF-Manager – ready to use")
    print(_SEPARATOR)
    print()
    print("Quick start with Docker Compose (recommended):")
    print()
    print("    docker compose up --build")
    print()
    print("Services:")
    print("    Frontend  →  http://localhost:3000")
    print("    Backend   →  http://localhost:8000")
    print("    Swagger   →  http://localhost:8000/docs")
    print()
    print("Manual startup:")
    print()
    print("    # Terminal 1 – backend")
    print("    cd backend")
    print("    uvicorn app:app --reload --port 8000")
    print()
    print("    # Terminal 2 – frontend")
    print("    cd frontend")
    print("    npm install && npm start")
    print()
    print("Quick extraction demo:")
    print()
    print("    python pdf_manager_app.py demo path/to/file.pdf")
    print()
    print("For step-by-step instructions see docs/SETUP.md")
    print(_SEPARATOR)

    if missing:
        print()
        print("Note: the following packages are not yet installed:")
        for pkg in missing:
            print(f"  - {pkg}")
        print()
        print("Install them with:  pip install -r requirements.txt")


# ---------------------------------------------------------------------------
# Demo extraction
# ---------------------------------------------------------------------------


def _run_demo(pdf_path: str) -> None:
    """Run a quick extraction demo on a local PDF file."""
    if not os.path.isfile(pdf_path):
        print(f"Error: file not found – {pdf_path}")
        sys.exit(1)

    try:
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, os.path.join(here, "backend"))
        from services.pdf_service import PDFService  # noqa: PLC0415
        from services.ml_service import MLService    # noqa: PLC0415
    except ImportError as exc:
        print(f"Cannot import backend services: {exc}")
        print(
            "Make sure all dependencies are installed: "
            "pip install -r requirements.txt"
        )
        sys.exit(1)

    print(f"Extracting data from: {pdf_path}")
    print()

    pdf_svc = PDFService()
    ml_svc = MLService()

    text, tables, pages = pdf_svc.extract(pdf_path)
    fields = ml_svc.extract_fields(text, tables)

    print(f"Pages : {pages}")
    print(f"Fields: {len(fields)} extracted")
    for field in fields:
        print(
            f"  [{field.field_name}] {field.value!r}"
            f"  (confidence={field.confidence:.2f}, page={field.page_number})"
        )

    print()
    print(f"Tables detected: {len(tables)}")
    for i, table in enumerate(tables[:3], 1):
        print(f"  Table {i}: {len(table)} row(s)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    if not _check_python_version():
        sys.exit(1)

    if not _check_repo_present():
        _print_setup_instructions()
        sys.exit(0)

    args = sys.argv[1:]
    if args and args[0] == "demo":
        if len(args) < 2:
            print("Usage: python pdf_manager_app.py demo path/to/file.pdf")
            sys.exit(1)
        missing = _check_dependencies()
        if missing:
            print("Missing packages:", ", ".join(missing))
            print("Run:  pip install -r requirements.txt")
            sys.exit(1)
        _run_demo(args[1])
        return

    missing = _check_dependencies()
    _print_usage(missing)


if __name__ == "__main__":
    main()
