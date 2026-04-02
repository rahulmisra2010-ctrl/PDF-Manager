#!/usr/bin/env python3
"""
extract_pdf_headers.py – PDF header/metadata extractor

Extracts and prints:
  1. PDF metadata (Title, Author, Subject, Creator, Producer, etc.)
  2. PDF outline / bookmarks (if present)
  3. Top-of-page header text (top ~15% of each page)

Usage
-----
  python tools/extract_pdf_headers.py <path/to/file.pdf> [--pages N]

Examples
--------
  # Windows
  python tools\\extract_pdf_headers.py "samples\\Official_withdrawal_form.pdf"
  python tools\\extract_pdf_headers.py "C:\\Users\\RAHUL MISRA\\sample_pdfs\\Official withdrawal form.pdf"

  # macOS / Linux
  python tools/extract_pdf_headers.py samples/Official_withdrawal_form.pdf
  python tools/extract_pdf_headers.py "/home/user/my pdfs/Official withdrawal form.pdf"

  # Limit to first 3 pages
  python tools/extract_pdf_headers.py samples/Official_withdrawal_form.pdf --pages 3
"""

import argparse
import sys
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# Section helpers
# ──────────────────────────────────────────────────────────────────────────────

def _section(title: str) -> None:
    """Print a section header."""
    bar = "=" * (len(title) + 4)
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Metadata
# ──────────────────────────────────────────────────────────────────────────────

def extract_metadata(pdf_path: Path) -> dict:
    """Return raw PDF metadata dict using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError("pypdf is required: pip install pypdf") from exc

    reader = PdfReader(str(pdf_path))
    meta = reader.metadata or {}
    return dict(meta)


def print_metadata(meta: dict) -> None:
    _section("PDF METADATA")
    if not meta:
        print("  (no metadata found)")
        return

    # Pretty-print known keys first, then any extras
    known_order = [
        "/Title", "/Author", "/Subject", "/Keywords",
        "/Creator", "/Producer", "/CreationDate", "/ModDate",
    ]
    printed = set()
    for key in known_order:
        if key in meta:
            label = key.lstrip("/")
            print(f"  {label:15s}: {meta[key]}")
            printed.add(key)

    for key, value in sorted(meta.items()):
        if key not in printed:
            label = key.lstrip("/")
            print(f"  {label:15s}: {value}")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Outline / bookmarks
# ──────────────────────────────────────────────────────────────────────────────

def extract_outline(pdf_path: Path) -> list:
    """Return the PDF outline (bookmarks) as a list."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError("pypdf is required: pip install pypdf") from exc

    reader = PdfReader(str(pdf_path))
    return reader.outline or []


def _walk_outline(items, depth: int = 0) -> None:
    """Recursively print outline items."""
    for item in items:
        if isinstance(item, list):
            _walk_outline(item, depth + 1)
        else:
            title = getattr(item, "title", str(item))
            print("  " + "  " * depth + f"- {title}")


def print_outline(outline: list) -> None:
    _section("OUTLINE / BOOKMARKS")
    if not outline:
        print("  (none)")
        return
    _walk_outline(outline)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Top-of-page header text
# ──────────────────────────────────────────────────────────────────────────────

def extract_page_headers(pdf_path: Path, max_pages: int = 0) -> list:
    """
    Crop the top 15% of each page and extract its text.

    Parameters
    ----------
    pdf_path  : path to the PDF file
    max_pages : number of pages to process (0 = all pages)

    Returns
    -------
    List of (page_number, header_text) tuples (1-indexed).
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError("pdfplumber is required: pip install pdfplumber") from exc

    results = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        pages = pdf.pages if not max_pages else pdf.pages[:max_pages]
        for i, page in enumerate(pages, start=1):
            crop_height = page.height * 0.15
            top_region = page.within_bbox((0, 0, page.width, crop_height))
            text = (top_region.extract_text() or "").strip()
            results.append((i, text))
    return results


def print_page_headers(page_headers: list) -> None:
    _section("TOP-OF-PAGE HEADER TEXT (top 15% of each page)")
    for page_num, text in page_headers:
        print(f"\n  --- Page {page_num} ---")
        if text:
            for line in text.splitlines():
                print(f"  {line}")
        else:
            print("  (no text found in top region)")


# ──────────────────────────────────────────────────────────────────────────────
# Smoke-check function (importable from tests)
# ──────────────────────────────────────────────────────────────────────────────

def smoke_check(pdf_path: Path, max_pages: int = 3) -> dict:
    """
    Run all three extractors against *pdf_path* and return a results dict.

    Raises ``FileNotFoundError`` if the file does not exist.
    Suitable for use in automated tests (no stdout output).
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    return {
        "metadata": extract_metadata(pdf_path),
        "outline": extract_outline(pdf_path),
        "page_headers": extract_page_headers(pdf_path, max_pages=max_pages),
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry-point
# ──────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract and print PDF headers (metadata, outline, top-of-page text).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "pdf",
        help="Path to the PDF file (quote if it contains spaces).",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=0,
        metavar="N",
        help="Number of pages to scan for top-of-page text (default: all pages).",
    )
    args = parser.parse_args(argv)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: file not found — {pdf_path}", file=sys.stderr)
        return 1

    print(f"\nProcessing: {pdf_path.resolve()}")

    # 1) Metadata
    try:
        meta = extract_metadata(pdf_path)
        print_metadata(meta)
    except Exception as exc:
        print(f"  [metadata error] {exc}", file=sys.stderr)

    # 2) Outline / bookmarks
    try:
        outline = extract_outline(pdf_path)
        print_outline(outline)
    except Exception as exc:
        print(f"  [outline error] {exc}", file=sys.stderr)

    # 3) Top-of-page text
    try:
        page_headers = extract_page_headers(pdf_path, max_pages=args.pages)
        print_page_headers(page_headers)
    except Exception as exc:
        print(f"  [page-header error] {exc}", file=sys.stderr)

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
