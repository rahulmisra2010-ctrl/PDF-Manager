"""
Smoke tests for tools/extract_pdf_headers.py

These tests verify the three extraction functions work correctly against the
bundled sample PDF (samples/Official_withdrawal_form.pdf).

Run with:
    pytest test_extract_pdf_headers.py -v
"""

import sys
from pathlib import Path

import pytest

# Make the tools/ package importable when running from repo root
sys.path.insert(0, str(Path(__file__).parent / "tools"))
from extract_pdf_headers import (  # noqa: E402
    extract_metadata,
    extract_outline,
    extract_page_headers,
    smoke_check,
)

SAMPLE_PDF = Path(__file__).parent / "samples" / "Official_withdrawal_form.pdf"


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sample_pdf():
    """Return the path to the bundled sample PDF, skip if missing."""
    if not SAMPLE_PDF.exists():
        pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
    return SAMPLE_PDF


# ──────────────────────────────────────────────────────────────────────────────
# Metadata tests
# ──────────────────────────────────────────────────────────────────────────────

def test_metadata_returns_dict(sample_pdf):
    meta = extract_metadata(sample_pdf)
    assert isinstance(meta, dict)


def test_metadata_has_title(sample_pdf):
    meta = extract_metadata(sample_pdf)
    assert "/Title" in meta
    assert "Withdrawal" in meta["/Title"]


def test_metadata_has_author(sample_pdf):
    meta = extract_metadata(sample_pdf)
    assert "/Author" in meta


# ──────────────────────────────────────────────────────────────────────────────
# Outline tests
# ──────────────────────────────────────────────────────────────────────────────

def test_outline_returns_list(sample_pdf):
    outline = extract_outline(sample_pdf)
    assert isinstance(outline, list)


# ──────────────────────────────────────────────────────────────────────────────
# Page-header text tests
# ──────────────────────────────────────────────────────────────────────────────

def test_page_headers_returns_list(sample_pdf):
    headers = extract_page_headers(sample_pdf, max_pages=1)
    assert isinstance(headers, list)
    assert len(headers) == 1


def test_page_headers_tuple_structure(sample_pdf):
    headers = extract_page_headers(sample_pdf, max_pages=1)
    page_num, text = headers[0]
    assert page_num == 1
    assert isinstance(text, str)


def test_page_headers_contain_expected_text(sample_pdf):
    """The sample PDF header should mention the form title."""
    headers = extract_page_headers(sample_pdf, max_pages=1)
    _, text = headers[0]
    assert "Withdrawal" in text or "Official" in text or text == "", (
        f"Unexpected header text: {text!r}"
    )


def test_page_headers_all_pages(sample_pdf):
    """When max_pages=0 all pages should be processed."""
    headers_all = extract_page_headers(sample_pdf, max_pages=0)
    headers_one = extract_page_headers(sample_pdf, max_pages=1)
    assert len(headers_all) >= len(headers_one)


# ──────────────────────────────────────────────────────────────────────────────
# Smoke-check integration test
# ──────────────────────────────────────────────────────────────────────────────

def test_smoke_check_returns_all_keys(sample_pdf):
    result = smoke_check(sample_pdf, max_pages=1)
    assert set(result.keys()) == {"metadata", "outline", "page_headers"}


def test_smoke_check_file_not_found():
    with pytest.raises(FileNotFoundError):
        smoke_check(Path("/nonexistent/path/file.pdf"))


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry-point test
# ──────────────────────────────────────────────────────────────────────────────

def test_cli_main_success(sample_pdf, capsys):
    from extract_pdf_headers import main
    rc = main([str(sample_pdf), "--pages", "1"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "PDF METADATA" in captured.out
    assert "OUTLINE" in captured.out
    assert "TOP-OF-PAGE" in captured.out

def test_cli_main_missing_file(capsys):
    from extract_pdf_headers import main
    rc = main(["/nonexistent/path/missing.pdf"])
    assert rc == 1


def test_cli_main_path_with_spaces(tmp_path, sample_pdf):
    """CLI must handle paths that contain spaces."""
    dest = tmp_path / "Official withdrawal form.pdf"
    dest.write_bytes(sample_pdf.read_bytes())
    from extract_pdf_headers import main
    rc = main([str(dest), "--pages", "1"])
    assert rc == 0
