"""
tests/test_dynamic_extraction.py — Unit tests for dynamic label/value pairing
heuristics in backend/services/dynamic_extraction.py.

These tests exercise only the pure-Python pairing logic (_is_label_candidate,
_merge_label_words, _pair_labels_values) without requiring EasyOCR, PyMuPDF,
or any real files.
"""

import sys
import os

# Make backend/services importable
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_backend = os.path.join(_repo_root, "backend")
for _p in [_repo_root, _backend]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
from services.dynamic_extraction import (
    _is_label_candidate,
    _merge_label_words,
    _pair_labels_values,
)


# ---------------------------------------------------------------------------
# _is_label_candidate
# ---------------------------------------------------------------------------


class TestIsLabelCandidate:
    def test_colon_suffix(self):
        assert _is_label_candidate("Name:")
        assert _is_label_candidate("Address:")
        assert _is_label_candidate("Present Address:")
        assert _is_label_candidate("Net Payable:")
        assert _is_label_candidate("Anything:")

    def test_keyword_no_colon(self):
        assert _is_label_candidate("Name")
        assert _is_label_candidate("Email")
        assert _is_label_candidate("Phone")
        assert _is_label_candidate("Address")
        assert _is_label_candidate("Date")
        assert _is_label_candidate("Present")
        assert _is_label_candidate("Payable")

    def test_non_label(self):
        assert not _is_label_candidate("Anoop")
        assert not _is_label_candidate("layout")
        assert not _is_label_candidate("73001")
        assert not _is_label_candidate("foo bar baz")
        assert not _is_label_candidate("")


# ---------------------------------------------------------------------------
# _pair_labels_values  — right-side value pairing
# ---------------------------------------------------------------------------


def _box(text, x, y, w=60, h=12, conf=0.95):
    """Helper to create a word-box dict."""
    return {"text": text, "x": x, "y": y, "width": w, "height": h, "confidence": conf}


class TestPairLabelsValues:
    def test_simple_right_pair(self):
        """Label followed immediately by value on the right."""
        boxes = [
            _box("Name:", x=10, y=10),
            _box("John", x=80, y=10),
        ]
        pairs = _pair_labels_values(boxes)
        assert len(pairs) == 1
        assert pairs[0]["label"] == "Name"
        assert pairs[0]["value"] == "John"

    def test_colon_stripped_from_label(self):
        """Colon is stripped from label text in output."""
        boxes = [
            _box("Email:", x=10, y=10),
            _box("john@example.com", x=80, y=10, w=120),
        ]
        pairs = _pair_labels_values(boxes)
        assert pairs[0]["label"] == "Email"

    def test_value_below_label(self):
        """When nothing is to the right, value is taken from the line below."""
        boxes = [
            _box("Address:", x=10, y=10),
            _box("Anoop layout", x=10, y=30, w=100),
        ]
        pairs = _pair_labels_values(boxes)
        assert len(pairs) == 1
        assert pairs[0]["label"] == "Address"
        assert pairs[0]["value"] == "Anoop layout"

    def test_two_pairs_independent(self):
        """Two independent label/value pairs on different lines."""
        boxes = [
            _box("Name:", x=10, y=10),
            _box("Alice", x=80, y=10),
            _box("Email:", x=10, y=40),
            _box("alice@example.com", x=80, y=40, w=130),
        ]
        pairs = _pair_labels_values(boxes)
        labels = {p["label"] for p in pairs}
        assert "Name" in labels
        assert "Email" in labels
        by_label = {p["label"]: p["value"] for p in pairs}
        assert by_label["Name"] == "Alice"
        assert by_label["Email"] == "alice@example.com"

    def test_lic_form_present_address(self):
        """Reproduce the LIC-form example: Present Address → Anoop layout."""
        boxes = [
            _box("Present", x=10, y=100),
            _box("Address:", x=74, y=100),
            _box("Anoop", x=145, y=100),
            _box("layout", x=200, y=100),
        ]
        pairs = _pair_labels_values(boxes)
        assert len(pairs) >= 1
        by_label = {p["label"]: p["value"] for p in pairs}
        # "Present Address" should map to "Anoop layout"
        found = False
        for label, value in by_label.items():
            if "address" in label.lower() and "anoop" in value.lower():
                found = True
        assert found, f"Expected 'Present Address'→'Anoop layout' in {by_label}"

    def test_lic_form_net_payable(self):
        """Reproduce the LIC-form example: Net Payable → 73001."""
        boxes = [
            _box("Net", x=10, y=200),
            _box("Payable:", x=55, y=200),
            _box("73001", x=130, y=200),
        ]
        pairs = _pair_labels_values(boxes)
        by_label = {p["label"]: p["value"] for p in pairs}
        found = any("payable" in lbl.lower() and "73001" in val
                    for lbl, val in by_label.items())
        assert found, f"Expected 'Net Payable'→'73001' in {by_label}"

    def test_no_boxes(self):
        """Empty input returns empty list."""
        assert _pair_labels_values([]) == []

    def test_only_values_no_labels(self):
        """Non-label words should not produce pairs."""
        boxes = [
            _box("hello", x=10, y=10),
            _box("world", x=70, y=10),
        ]
        pairs = _pair_labels_values(boxes)
        assert pairs == []

    def test_value_not_duplicated_as_label(self):
        """A value box must not also be treated as the label of another pair."""
        boxes = [
            _box("Name:", x=10, y=10),
            _box("Alice", x=80, y=10),
        ]
        pairs = _pair_labels_values(boxes)
        # Only one pair; value "Alice" is not a label
        assert len(pairs) == 1

    def test_bbox_present_in_output(self):
        """Each pair dict must include a bbox with x/y/width/height."""
        boxes = [
            _box("Phone:", x=10, y=10),
            _box("9876543210", x=80, y=10, w=90),
        ]
        pairs = _pair_labels_values(boxes)
        assert pairs[0]["bbox"]["x"] == 10
        assert pairs[0]["bbox"]["y"] == 10
        assert "width" in pairs[0]["bbox"]
        assert "height" in pairs[0]["bbox"]

    def test_confidence_preserved(self):
        """Confidence from the label box is propagated to the pair."""
        boxes = [
            _box("Email:", x=10, y=10, conf=0.72),
            _box("test@example.com", x=80, y=10, conf=0.99),
        ]
        pairs = _pair_labels_values(boxes)
        assert abs(pairs[0]["confidence"] - 0.72) < 0.01


# ---------------------------------------------------------------------------
# _merge_label_words
# ---------------------------------------------------------------------------


class TestMergeLabelWords:
    def test_single_word_unchanged(self):
        words = [_box("Name:", x=10, y=10)]
        merged = _merge_label_words(words)
        assert len(merged) == 1
        assert merged[0]["text"] == "Name:"

    def test_two_word_label_merged(self):
        words = [
            _box("Present", x=10, y=10),
            _box("Address:", x=74, y=10),
        ]
        merged = _merge_label_words(words)
        assert len(merged) == 1
        assert "Present" in merged[0]["text"]
        assert "Address" in merged[0]["text"]

    def test_words_on_different_lines_not_merged(self):
        words = [
            _box("Name:", x=10, y=10),
            _box("Email:", x=10, y=50),
        ]
        merged = _merge_label_words(words)
        assert len(merged) == 2

    def test_three_word_label(self):
        """'Net Payable Amount' should merge into one label."""
        words = [
            _box("Net", x=10, y=10, w=30),
            _box("Payable", x=45, y=10, w=50),
            _box("Amount:", x=100, y=10, w=55),
        ]
        merged = _merge_label_words(words)
        assert len(merged) == 1
        text = merged[0]["text"]
        assert "Net" in text and "Payable" in text and "Amount" in text


# ---------------------------------------------------------------------------
# Import schema helpers
# ---------------------------------------------------------------------------

from services.dynamic_extraction import (
    create_schema_from_pairs,
    map_pairs_to_schema,
)


# ---------------------------------------------------------------------------
# create_schema_from_pairs
# ---------------------------------------------------------------------------


def _pair(label: str, value: str = "", confidence: float = 0.95) -> dict:
    """Helper: build a minimal pair dict."""
    return {"label": label, "value": value, "confidence": confidence, "bbox": None, "page_number": 1}


class TestCreateSchemaFromPairs:
    def test_basic_ordering(self):
        """Labels appear in the same order as the input pairs."""
        pairs = [_pair("Name"), _pair("Email"), _pair("Phone")]
        schema = create_schema_from_pairs(pairs)
        assert schema == ["Name", "Email", "Phone"]

    def test_duplicates_deduplicated(self):
        """Duplicate labels are included only once (first occurrence)."""
        pairs = [_pair("Name"), _pair("Email"), _pair("Name")]
        schema = create_schema_from_pairs(pairs)
        assert schema == ["Name", "Email"]
        assert schema.count("Name") == 1

    def test_empty_pairs(self):
        """Empty input produces an empty schema."""
        assert create_schema_from_pairs([]) == []

    def test_lic_form_labels(self):
        """LIC form labels are preserved in document order."""
        pairs = [
            _pair("Present Address"),
            _pair("Net Payable"),
            _pair("Policy Number"),
        ]
        schema = create_schema_from_pairs(pairs)
        assert schema == ["Present Address", "Net Payable", "Policy Number"]

    def test_label_strings_preserved(self):
        """Label strings are not normalised or modified."""
        pairs = [_pair("Date of Birth"), _pair("IFSC Code")]
        schema = create_schema_from_pairs(pairs)
        assert "Date of Birth" in schema
        assert "IFSC Code" in schema


# ---------------------------------------------------------------------------
# map_pairs_to_schema
# ---------------------------------------------------------------------------


class TestMapPairsToSchema:
    def test_exact_match(self):
        """Discovered pair matches schema label exactly."""
        schema = ["Name", "Email"]
        pairs = [_pair("Name", "Alice"), _pair("Email", "alice@example.com")]
        result = map_pairs_to_schema(pairs, schema)
        by_label = {r["label"]: r for r in result}
        assert by_label["Name"]["value"] == "Alice"
        assert by_label["Email"]["value"] == "alice@example.com"

    def test_case_insensitive_exact_match(self):
        """Matching is case-insensitive for exact comparison."""
        schema = ["Name"]
        pairs = [_pair("name", "Bob")]
        result = map_pairs_to_schema(pairs, schema)
        assert result[0]["value"] == "Bob"
        assert result[0]["matched"] is True

    def test_normalised_match_strips_colon(self):
        """'Name:' in discovered pair matches schema label 'Name'."""
        schema = ["Name"]
        pairs = [_pair("Name:", "Carol")]
        result = map_pairs_to_schema(pairs, schema)
        assert result[0]["value"] == "Carol"
        assert result[0]["matched"] is True

    def test_fuzzy_match_ocr_variation(self):
        """Minor OCR variation in label (extra character glitch) is fuzzy-matched."""
        schema = ["Name"]
        # Simulate OCR glitch: extra 'a' inserted → 'Naame' instead of 'Name'
        pairs = [_pair("Naame", "Dave")]
        result = map_pairs_to_schema(pairs, schema, fuzzy_threshold=0.70)
        assert result[0]["value"] == "Dave"
        assert result[0]["matched"] is True

    def test_unmatched_schema_label_gets_empty_value(self):
        """Schema labels with no matching pair get empty value and zero confidence."""
        schema = ["Name", "Phone"]
        pairs = [_pair("Name", "Eve")]
        result = map_pairs_to_schema(pairs, schema)
        by_label = {r["label"]: r for r in result}
        assert by_label["Name"]["value"] == "Eve"
        assert by_label["Phone"]["value"] == ""
        assert by_label["Phone"]["confidence"] == 0.0
        assert by_label["Phone"]["matched"] is False

    def test_schema_order_preserved(self):
        """Output list follows schema label order, not discovered-pair order."""
        schema = ["Phone", "Name", "Email"]
        pairs = [_pair("Name", "Frank"), _pair("Email", "f@example.com"), _pair("Phone", "555")]
        result = map_pairs_to_schema(pairs, schema)
        assert [r["label"] for r in result] == ["Phone", "Name", "Email"]

    def test_each_pair_used_at_most_once(self):
        """A discovered pair is not matched to two different schema labels."""
        schema = ["Name", "FullName"]
        pairs = [_pair("Name", "Grace")]
        result = map_pairs_to_schema(pairs, schema)
        matched = [r for r in result if r["matched"]]
        assert len(matched) == 1  # only one pair available

    def test_empty_schema(self):
        """Empty schema produces an empty result."""
        pairs = [_pair("Name", "Heidi")]
        result = map_pairs_to_schema(pairs, [])
        assert result == []

    def test_empty_pairs_all_unmatched(self):
        """No discovered pairs → all schema labels are unmatched."""
        schema = ["Name", "Email"]
        result = map_pairs_to_schema([], schema)
        assert all(r["matched"] is False for r in result)
        assert all(r["value"] == "" for r in result)

    def test_lic_form_present_address_fuzzy(self):
        """'Present  Address' (double space OCR) fuzzy-matches schema 'Present Address'."""
        schema = ["Present Address", "Net Payable"]
        pairs = [
            _pair("Present  Address", "Anoop layout"),  # double space OCR glitch
            _pair("Net Payable", "73001"),
        ]
        result = map_pairs_to_schema(pairs, schema)
        by_label = {r["label"]: r for r in result}
        assert "Anoop layout" in by_label["Present Address"]["value"]
        assert by_label["Net Payable"]["value"] == "73001"
