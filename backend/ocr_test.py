"""
OCR Test Module

Utility for testing and benchmarking the OCR / text-extraction pipeline.
Runs the PDF extraction service against one or more PDF files and reports
extracted text, detected tables, and ML-classified fields.

Usage (from the backend/ directory):

    python ocr_test.py <path/to/file.pdf> [<path/to/another.pdf> ...]

If no arguments are provided the module attempts to process every ``*.pdf``
file it finds under the configured upload directory.
"""

import sys
import time
from pathlib import Path


def _print_separator(title: str = "", width: int = 60) -> None:
    """Print a visible section separator."""
    if title:
        padding = max(0, width - len(title) - 2)
        left = padding // 2
        right = padding - left
        print(f"\n{'=' * left} {title} {'=' * right}")
    else:
        print("=" * width)


def test_ocr(pdf_path: str) -> dict:
    """
    Run the full OCR / extraction pipeline on *pdf_path*.

    Imports are deferred so that this module can be imported without
    requiring all backend dependencies to be installed (useful for CI
    environments that only run static analysis).

    Args:
        pdf_path: Absolute or relative path to a PDF file.

    Returns:
        A dict with keys ``text``, ``tables``, ``fields``, ``page_count``,
        and ``elapsed_seconds``.
    """
    # Deferred imports so the module can be imported without heavy deps
    from config import settings  # noqa: F401 - ensures env is loaded
    from services.ml_service import MLService
    from services.pdf_service import PDFService

    pdf_service = PDFService()
    ml_service = MLService()

    start = time.perf_counter()
    text, tables, page_count = pdf_service.extract(pdf_path)
    fields = ml_service.extract_fields(text, tables)
    elapsed = round(time.perf_counter() - start, 3)

    return {
        "text": text,
        "tables": tables,
        "fields": fields,
        "page_count": page_count,
        "elapsed_seconds": elapsed,
    }


def report(pdf_path: str, result: dict) -> None:
    """
    Print a human-readable summary of an OCR test result.

    Args:
        pdf_path: Path that was tested (used in the heading).
        result:   Dict returned by :func:`test_ocr`.
    """
    _print_separator(Path(pdf_path).name)
    print(f"  Pages   : {result['page_count']}")
    print(f"  Time    : {result['elapsed_seconds']} s")
    print(f"  Tables  : {len(result['tables'])}")
    print(f"  Fields  : {len(result['fields'])}")

    if result["fields"]:
        print("\n  Extracted fields:")
        for field in result["fields"]:
            # Support both ExtractedField objects and plain dicts
            if hasattr(field, "field_name"):
                name = field.field_name
                value = field.value
                confidence = field.confidence
            else:
                name = field.get("field_name", "?")
                value = field.get("value", "")
                confidence = field.get("confidence", 0.0)
            print(f"    [{confidence:.2f}] {name}: {value}")

    if result["text"]:
        preview = result["text"][:300].replace("\n", " ")
        print(f"\n  Text preview: {preview!r}")


def run_tests(pdf_paths: list[str]) -> None:
    """
    Run :func:`test_ocr` for each path in *pdf_paths* and print results.

    Args:
        pdf_paths: List of paths to PDF files to test.
    """
    if not pdf_paths:
        print("No PDF files provided or found. Exiting.")
        return

    passed = 0
    failed = 0
    for path in pdf_paths:
        try:
            result = test_ocr(path)
            report(path, result)
            passed += 1
        except Exception as exc:  # noqa: BLE001
            _print_separator(Path(path).name)
            print(f"  ERROR: {exc}")
            failed += 1

    _print_separator()
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from config import settings

    if len(sys.argv) > 1:
        paths = sys.argv[1:]
    else:
        # Fall back to all PDFs in the configured upload directory
        upload_dir = Path(settings.UPLOAD_DIR)
        paths = [str(p) for p in sorted(upload_dir.glob("*.pdf"))]

    run_tests(paths)
