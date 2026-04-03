#!/usr/bin/env python3
"""
extract_pdf_headers.py – PDF header/metadata extractor

Extracts and prints:
  1. PDF metadata (Title, Author, Subject, Creator, Producer, etc.)
  2. PDF outline / bookmarks (if present)
  3. Top-of-page header text (top ~15% of each page)
  4. Top-of-page heading lines with bounding boxes (for overlay rendering)

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
# 4. Heading lines with bounding boxes
# ──────────────────────────────────────────────────────────────────────────────

def extract_headings_with_bbox(
    pdf_path: Path,
    max_pages: int = 0,
    header_fraction: float = 0.15,
) -> list:
    """
    Extract heading lines from the top of each page with per-line bounding boxes.

    Words on the same text line (same ``top`` y-coordinate within a tolerance)
    are merged into a single heading entry so that multi-word titles such as
    ``"Official Withdrawal Form"`` are returned as one item rather than
    three separate words.

    Parameters
    ----------
    pdf_path         : path to the PDF file
    max_pages        : number of pages to process (0 = all pages)
    header_fraction  : fraction of the page height that defines the header
                       region (default 0.15 → top 15 % of each page)

    Returns
    -------
    List of (page_number, headings) tuples (1-indexed).
    ``headings`` is a list of dicts, one per text line found in the header
    region::

        {
            "text": str,           # full text of the heading line
            "bbox": {              # bounding box in PDF points (origin top-left)
                "x0": float,
                "y0": float,       # top edge of the line
                "x1": float,
                "y1": float,       # bottom edge of the line
            },
            "page": int,           # 1-based page number
        }

    An empty list of headings is returned for pages where no text is found in
    the header region.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError("pdfplumber is required: pip install pdfplumber") from exc

    # Vertical tolerance (in points) to group words into the same text line.
    # 4 pt handles minor baseline variations within a single line.
    _LINE_Y_TOL: float = 4.0

    results = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        pages = pdf.pages if not max_pages else pdf.pages[:max_pages]
        for page_num, page in enumerate(pages, start=1):
            crop_height = page.height * header_fraction
            top_region = page.within_bbox((0, 0, page.width, crop_height))
            words = top_region.extract_words() or []

            # Group words into lines by their ``top`` y-coordinate
            lines: list[list[dict]] = []
            for word in words:
                placed = False
                for line in lines:
                    rep = line[0]
                    if abs(word["top"] - rep["top"]) <= _LINE_Y_TOL:
                        line.append(word)
                        placed = True
                        break
                if not placed:
                    lines.append([word])

            # Sort lines top-to-bottom, words within each line left-to-right
            lines.sort(key=lambda ln: ln[0]["top"])
            headings = []
            for line in lines:
                line.sort(key=lambda w: w["x0"])
                text = " ".join(w["text"] for w in line).strip()
                if not text:
                    continue
                x0 = min(w["x0"] for w in line)
                y0 = min(w["top"] for w in line)
                x1 = max(w["x1"] for w in line)
                y1 = max(w["bottom"] for w in line)
                headings.append({
                    "text": text,
                    "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                    "page": page_num,
                })

            results.append((page_num, headings))

    return results


def print_headings_with_bbox(heading_results: list) -> None:
    _section("HEADING LINES WITH BOUNDING BOXES (top 15% of each page)")
    for page_num, headings in heading_results:
        print(f"\n  --- Page {page_num} ---")
        if headings:
            for h in headings:
                bb = h["bbox"]
                print(
                    f"  [{bb['x0']:.1f},{bb['y0']:.1f} → {bb['x1']:.1f},{bb['y1']:.1f}]"
                    f"  {h['text']}"
                )
        else:
            print("  (no heading text found in top region)")


# ──────────────────────────────────────────────────────────────────────────────
# Smoke-check function (importable from tests)
# ──────────────────────────────────────────────────────────────────────────────

def smoke_check(pdf_path: Path, max_pages: int = 3) -> dict:
    """
    Run all four extractors against *pdf_path* and return a results dict.

    Raises ``FileNotFoundError`` if the file does not exist.
    Suitable for use in automated tests (no stdout output).
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    return {
        "metadata": extract_metadata(pdf_path),
        "outline": extract_outline(pdf_path),
        "page_headers": extract_page_headers(pdf_path, max_pages=max_pages),
        "headings_with_bbox": extract_headings_with_bbox(pdf_path, max_pages=max_pages),
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

    # 4) Heading lines with bounding boxes
    try:
        headings_bbox = extract_headings_with_bbox(pdf_path, max_pages=args.pages)
        print_headings_with_bbox(headings_bbox)
    except Exception as exc:
        print(f"  [headings-bbox error] {exc}", file=sys.stderr)

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
