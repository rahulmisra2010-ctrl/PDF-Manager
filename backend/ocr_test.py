#!/usr/bin/env python3
"""
backend/ocr_test.py — OCR testing and debugging module.

Wraps PyMuPDF and pytesseract to test extraction on a given PDF file path.
Prints raw extracted text, then the mapped address-book fields (if any).

Usage
-----
    python backend/ocr_test.py path/to/file.pdf
    python ocr_test.py path/to/file.pdf   # when run from backend/
"""

from __future__ import annotations

import json
import os
import sys


def _setup_path() -> None:
    """Ensure backend/ is on sys.path for relative imports."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    if this_dir not in sys.path:
        sys.path.insert(0, this_dir)


def test_ocr(pdf_path: str) -> dict:
    """
    Run OCR extraction and address-book field mapping on *pdf_path*.

    Args:
        pdf_path: Absolute or relative path to a PDF file.

    Returns:
        Dictionary with keys ``text``, ``page_count``, and ``mapped_fields``.

    Raises:
        FileNotFoundError: If *pdf_path* does not exist.
        ImportError: If required libraries are not installed.
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    _setup_path()

    try:
        from services.pdf_service import PDFService  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "Could not import PDFService. "
            "Install dependencies: pip install -r backend/requirements.txt"
        ) from exc

    svc = PDFService()
    text, tables, page_count = svc.extract(pdf_path)
    mapped_fields = svc.map_address_book_fields(text)

    return {
        "text": text,
        "page_count": page_count,
        "table_count": len(tables),
        "mapped_fields": mapped_fields,
    }


def main() -> None:
    """Command-line entry point."""
    if len(sys.argv) < 2:
        print(f"Usage: python {os.path.basename(__file__)} <path/to/file.pdf>",
              file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]

    print(f"Testing OCR extraction on: {pdf_path}\n")

    try:
        result = test_ocr(pdf_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Pages    : {result['page_count']}")
    print(f"Tables   : {result['table_count']}")
    print()
    print("--- Raw extracted text ---")
    print(result["text"] or "(empty)")
    print()
    print("--- Mapped address-book fields ---")
    if result["mapped_fields"]:
        print(json.dumps(result["mapped_fields"], indent=2, ensure_ascii=False))
    else:
        print("(no fields mapped)")


if __name__ == "__main__":
    main()
