"""
Smoke tests for tools/extract_pdf_headers.py

These tests verify the four extraction functions work correctly against the
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
    extract_headings_with_bbox,
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
# Heading lines with bounding boxes tests
# ──────────────────────────────────────────────────────────────────────────────

def test_headings_with_bbox_returns_list(sample_pdf):
    results = extract_headings_with_bbox(sample_pdf, max_pages=1)
    assert isinstance(results, list)
    assert len(results) == 1


def test_headings_with_bbox_tuple_structure(sample_pdf):
    results = extract_headings_with_bbox(sample_pdf, max_pages=1)
    page_num, headings = results[0]
    assert page_num == 1
    assert isinstance(headings, list)


def test_headings_with_bbox_non_empty(sample_pdf):
    """The sample PDF should have at least one heading in the top 15%."""
    results = extract_headings_with_bbox(sample_pdf, max_pages=1)
    _, headings = results[0]
    assert len(headings) >= 1


def test_headings_with_bbox_dict_keys(sample_pdf):
    """Each heading entry must have 'text', 'bbox', and 'page' keys."""
    results = extract_headings_with_bbox(sample_pdf, max_pages=1)
    _, headings = results[0]
    for h in headings:
        assert "text" in h
        assert "bbox" in h
        assert "page" in h
        assert set(h["bbox"].keys()) == {"x0", "y0", "x1", "y1"}


def test_headings_with_bbox_coordinates_sane(sample_pdf):
    """Bounding box coordinates must be non-negative and well-ordered."""
    results = extract_headings_with_bbox(sample_pdf, max_pages=1)
    _, headings = results[0]
    for h in headings:
        bb = h["bbox"]
        assert bb["x0"] >= 0
        assert bb["y0"] >= 0
        assert bb["x1"] > bb["x0"], f"x1 ({bb['x1']}) must be > x0 ({bb['x0']})"
        assert bb["y1"] > bb["y0"], f"y1 ({bb['y1']}) must be > y0 ({bb['y0']})"


def test_headings_with_bbox_contains_expected_text(sample_pdf):
    """The sample PDF heading should contain 'Withdrawal' or 'Official'."""
    results = extract_headings_with_bbox(sample_pdf, max_pages=1)
    _, headings = results[0]
    all_text = " ".join(h["text"] for h in headings)
    assert "Withdrawal" in all_text or "Official" in all_text, (
        f"Expected heading text not found; got: {all_text!r}"
    )


def test_headings_with_bbox_page_numbers(sample_pdf):
    """Each heading entry's 'page' field must match the tuple's page number."""
    results = extract_headings_with_bbox(sample_pdf, max_pages=1)
    page_num, headings = results[0]
    for h in headings:
        assert h["page"] == page_num


def test_headings_with_bbox_all_pages(sample_pdf):
    """When max_pages=0 all pages are processed."""
    results_all = extract_headings_with_bbox(sample_pdf, max_pages=0)
    results_one = extract_headings_with_bbox(sample_pdf, max_pages=1)
    assert len(results_all) >= len(results_one)


def test_headings_with_bbox_custom_fraction(sample_pdf):
    """A larger header_fraction should capture at least as many headings."""
    results_small = extract_headings_with_bbox(sample_pdf, max_pages=1, header_fraction=0.05)
    results_large = extract_headings_with_bbox(sample_pdf, max_pages=1, header_fraction=0.30)
    _, headings_small = results_small[0]
    _, headings_large = results_large[0]
    assert len(headings_large) >= len(headings_small)


# ──────────────────────────────────────────────────────────────────────────────
# Smoke-check integration test
# ──────────────────────────────────────────────────────────────────────────────

def test_smoke_check_returns_all_keys(sample_pdf):
    result = smoke_check(sample_pdf, max_pages=1)
    assert set(result.keys()) == {"metadata", "outline", "page_headers", "headings_with_bbox"}


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
    assert "BOUNDING BOXES" in captured.out

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
