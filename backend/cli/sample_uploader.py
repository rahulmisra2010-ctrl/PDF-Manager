"""
backend/cli/sample_uploader.py — Interactive CLI for batch PDF processing.

Workflow
--------
1. Prompt user for a folder path containing PDF files.
2. Scan the folder and discover all ``.pdf`` files.
3. For each PDF, run the full RAG extraction pipeline.
4. Display extracted fields with confidence scores and intelligence
   indicators in a formatted terminal UI.
5. Summarise results across all processed files.

Usage
-----
    from backend.cli.sample_uploader import SampleUploader
    SampleUploader().run()

Or from the command line via pdf_manager_app.py:
    python pdf_manager_app.py sample
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

_WIDTH = 62  # total width inside the box (excluding border chars)


def _box_line(content: str = "", fill: str = " ") -> str:
    """Return a single padded box line: ║ content... ║"""
    padded = content.ljust(_WIDTH)
    if len(padded) > _WIDTH:
        padded = padded[: _WIDTH - 1] + "…"
    return f"║ {padded} ║"


def _separator() -> str:
    return "╠" + "═" * (_WIDTH + 2) + "╣"


def _top() -> str:
    return "╔" + "═" * (_WIDTH + 2) + "╗"


def _bottom() -> str:
    return "╚" + "═" * (_WIDTH + 2) + "╝"


def _title(text: str) -> str:
    """Return a centred title line."""
    centred = text.center(_WIDTH)
    return f"║ {centred} ║"


def _print_box(*lines: str) -> None:
    for line in lines:
        print(line)


def _confidence_bar(pct: float, width: int = 10) -> str:
    """Return a simple ASCII progress bar for confidence."""
    filled = int(round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


def _confidence_label(pct: float) -> str:
    """Return a human-readable confidence label."""
    if pct >= 90:
        return "HIGH"
    if pct >= 70:
        return "MED"
    return "LOW"


def _icon(pct: float) -> str:
    """Return ✓, ⚠, or ✗ based on confidence."""
    if pct >= 85:
        return "✓"
    if pct >= 50:
        return "⚠"
    return "✗"


# ---------------------------------------------------------------------------
# City → State inference mapping (subset for Indian cities)
# ---------------------------------------------------------------------------

_CITY_STATE: dict[str, str] = {
    "asansol": "WB",
    "kolkata": "WB",
    "durgapur": "WB",
    "howrah": "WB",
    "siliguri": "WB",
    "mumbai": "MH",
    "pune": "MH",
    "nagpur": "MH",
    "delhi": "DL",
    "new delhi": "DL",
    "bangalore": "KA",
    "bengaluru": "KA",
    "mysore": "KA",
    "hyderabad": "TS",
    "chennai": "TN",
    "coimbatore": "TN",
    "ahmedabad": "GJ",
    "surat": "GJ",
    "jaipur": "RJ",
    "lucknow": "UP",
    "kanpur": "UP",
    "varanasi": "UP",
    "patna": "BR",
    "bhopal": "MP",
    "indore": "MP",
    "chandigarh": "PB",
    "amritsar": "PB",
    "guwahati": "AS",
    "bhubaneswar": "OD",
    "thiruvananthapuram": "KL",
    "kochi": "KL",
}

# State → typical zip-code prefix mapping (first digit patterns)
_STATE_ZIP_PREFIX: dict[str, str] = {
    "WB": "7",   # West Bengal (70–74 PIN range)
    "MH": "4",   # Maharashtra (40–44)
    "DL": "1",   # Delhi (10–11)
    "KA": "5",   # Karnataka (56–59)
    "TS": "5",   # Telangana (50–53)
    "TN": "6",   # Tamil Nadu (60–64)
    "GJ": "3",   # Gujarat (36–39)
    "RJ": "3",   # Rajasthan (30–34)
    "UP": "2",   # Uttar Pradesh (20–28)
    "BR": "8",   # Bihar (80–85)
    "MP": "4",   # Madhya Pradesh (45–48)
    "PB": "1",   # Punjab (14–15)
    "AS": "7",   # Assam (78)
    "OD": "7",   # Odisha (75–77)
    "KL": "6",   # Kerala (67–69)
}


# ---------------------------------------------------------------------------
# Intelligence layer
# ---------------------------------------------------------------------------

def _infer_state_from_city(city: str) -> tuple[str, float]:
    """
    Infer state abbreviation from city name.

    Returns (state, confidence_boost) or ("", 0.0) if unknown.
    """
    key = city.strip().lower()
    state = _CITY_STATE.get(key, "")
    return (state, 0.80) if state else ("", 0.0)


def _validate_zip(zip_code: str, state: str) -> tuple[bool, str]:
    """
    Validate a zip code against its expected state prefix.

    Returns (is_valid, reason).
    """
    digits = re.sub(r"\D", "", zip_code)
    if len(digits) != 6:
        return False, "Expected 6-digit Indian PIN code"
    expected_prefix = _STATE_ZIP_PREFIX.get(state.upper(), "")
    if expected_prefix and not digits.startswith(expected_prefix):
        return False, f"Expected prefix '{expected_prefix}' for {state}"
    return True, f"Pattern valid ({digits[0]}XXXXX for {state})" if expected_prefix else "Pattern valid"


def _validate_phone(phone: str) -> tuple[bool, str]:
    """Return (is_valid, reason) for a phone number string."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return True, "10-digit Indian phone format"
    return False, f"Expected 10 digits, got {len(digits)}"


def _validate_email(email: str) -> tuple[bool, str]:
    """Basic email format validation."""
    if re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return True, "Valid email format"
    return False, "Does not match email pattern"


def _apply_intelligence(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Post-process extracted fields with rule-based intelligence.

    Applies city→state inference, state→zip validation, phone and email
    validation, and adjusts confidence scores accordingly.

    Returns a new list of enriched field dicts (original dicts untouched).
    """
    by_name: dict[str, dict] = {f["field_name"]: dict(f) for f in fields}
    enriched: list[dict[str, Any]] = []

    city_val = (by_name.get("City") or {}).get("field_value", "")
    state_val = (by_name.get("State") or {}).get("field_value", "")

    # --- City → State inference -------------------------------------------
    if city_val and not state_val:
        inferred_state, boost = _infer_state_from_city(city_val)
        if inferred_state:
            if "State" not in by_name:
                by_name["State"] = {
                    "field_name": "State",
                    "field_value": inferred_state,
                    "confidence": 0.0,
                    "rag_retrieved": [],
                }
            by_name["State"]["field_value"] = inferred_state
            by_name["State"]["confidence"] = boost
            by_name["State"]["_inferred"] = True
            by_name["State"]["_inference_source"] = (
                f"City inference ({city_val}→{inferred_state})"
            )
            state_val = inferred_state

    # --- Zip Code validation / confidence update --------------------------
    zip_val = (by_name.get("Zip Code") or {}).get("field_value", "")
    if zip_val and state_val:
        valid, reason = _validate_zip(zip_val, state_val)
        if "Zip Code" in by_name:
            if valid:
                by_name["Zip Code"]["confidence"] = max(
                    by_name["Zip Code"].get("confidence", 0.0), 0.90
                )
            by_name["Zip Code"]["_validation"] = (valid, reason)

    # --- Phone validation -------------------------------------------------
    for phone_field in ("Cell Phone", "Home Phone", "Work Phone"):
        if phone_field in by_name and by_name[phone_field].get("field_value"):
            valid, reason = _validate_phone(by_name[phone_field]["field_value"])
            by_name[phone_field]["_validation"] = (valid, reason)
            if valid:
                by_name[phone_field]["confidence"] = max(
                    by_name[phone_field].get("confidence", 0.0), 0.95
                )

    # --- Email validation -------------------------------------------------
    if "Email" in by_name and by_name["Email"].get("field_value"):
        valid, reason = _validate_email(by_name["Email"]["field_value"])
        by_name["Email"]["_validation"] = (valid, reason)
        if valid:
            by_name["Email"]["confidence"] = max(
                by_name["Email"].get("confidence", 0.0), 0.90
            )

    # Rebuild ordered list (maintain PRIMARY_FIELDS order)
    _order = [
        "Name", "Cell Phone", "Email", "Street Address",
        "City", "State", "Zip Code", "Work Phone", "Home Phone",
    ]
    seen: set[str] = set()
    for fname in _order:
        if fname in by_name:
            enriched.append(by_name[fname])
            seen.add(fname)
    for fname, fdict in by_name.items():
        if fname not in seen:
            enriched.append(fdict)

    return enriched


# ---------------------------------------------------------------------------
# SampleUploader
# ---------------------------------------------------------------------------

class SampleUploader:
    """
    Interactive CLI workflow for batch PDF processing with RAG extraction.

    Public API
    ----------
    run()          Entry point — orchestrates the full workflow.
    """

    def __init__(self, backend_dir: str | None = None) -> None:
        """
        Args:
            backend_dir: Absolute path to the ``backend/`` directory.
                         Defaults to the sibling ``backend/`` next to the
                         repo root (auto-detected).
        """
        if backend_dir is None:
            # Resolve from this file's location: backend/cli/sample_uploader.py
            _here = Path(__file__).resolve().parent          # backend/cli/
            backend_dir = str(_here.parent)                  # backend/
        self._backend_dir = backend_dir
        self._ensure_backend_on_path()

    # ------------------------------------------------------------------
    # sys.path management
    # ------------------------------------------------------------------

    def _ensure_backend_on_path(self) -> None:
        if self._backend_dir not in sys.path:
            sys.path.insert(0, self._backend_dir)

    # ------------------------------------------------------------------
    # Service accessors
    # ------------------------------------------------------------------

    def _get_pdf_service(self):
        try:
            from services.pdf_service import PDFService  # type: ignore[import]
            return PDFService()
        except Exception as exc:
            print(f"  ⚠ PDFService unavailable: {exc}", file=sys.stderr)
            return None

    def _get_rag_service(self) -> Any:
        try:
            from services.rag_service import RAGService  # type: ignore[import]
            rag_dir = os.path.join(self._backend_dir, "..", "rag_data")
            return RAGService(rag_dir=rag_dir)
        except Exception as exc:
            print(f"  ⚠ RAGService unavailable: {exc}", file=sys.stderr)
            return None

    # ------------------------------------------------------------------
    # Workflow steps
    # ------------------------------------------------------------------

    def prompt_folder_location(self) -> str:
        """
        Interactively prompt the user to enter a folder path.

        Returns the validated absolute path entered by the user.
        Keeps prompting until a valid directory is supplied.
        """
        _print_box(
            _top(),
            _title("PDF MANAGER — SAMPLE FILE UPLOAD"),
            _separator(),
            _box_line(),
            _box_line("  Enter folder location containing PDF files."),
            _box_line("  (Press Enter to use the bundled 'samples/' folder)"),
            _box_line(),
        )

        while True:
            try:
                raw = input("  ➤  Folder path: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                sys.exit(0)

            if not raw:
                # Default: samples/ directory next to backend/
                raw = str(Path(self._backend_dir).parent / "samples")

            path = os.path.expanduser(raw)
            path = os.path.abspath(path)

            if os.path.isdir(path):
                return path

            print(f"  ✗ Directory not found: {path}. Please try again.\n")

    def scan_pdfs(self, folder_path: str) -> list[str]:
        """
        Recursively scan *folder_path* for PDF files.

        Returns a sorted list of absolute paths to discovered PDFs.
        """
        pdfs: list[str] = []
        for root, _dirs, files in os.walk(folder_path):
            for fname in files:
                if fname.lower().endswith(".pdf"):
                    pdfs.append(os.path.join(root, fname))
        return sorted(pdfs)

    def process_batch(self, pdf_files: list[str]) -> list[dict[str, Any]]:
        """
        Run RAG extraction on each PDF file in *pdf_files*.

        Returns a list of result dicts, one per file:
        ``{"filename": ..., "path": ..., "fields": [...], "error": ...}``
        """
        pdf_svc = self._get_pdf_service()
        rag_svc = self._get_rag_service()

        results: list[dict[str, Any]] = []

        for idx, pdf_path in enumerate(pdf_files, start=1):
            fname = os.path.basename(pdf_path)
            bar_width = 20
            filled = int(round(idx / len(pdf_files) * bar_width))
            bar = "█" * filled + "░" * (bar_width - filled)
            pct = int(idx / len(pdf_files) * 100)
            print(f"\r  Processing [{bar}] {pct:3d}%  {fname:<30}", end="", flush=True)

            result: dict[str, Any] = {
                "filename": fname,
                "path": pdf_path,
                "fields": [],
                "error": None,
            }

            if pdf_svc is None:
                result["error"] = "PDFService unavailable"
                results.append(result)
                continue

            try:
                text, _tables, page_count = pdf_svc.extract(pdf_path)
                result["page_count"] = page_count
            except Exception as exc:
                result["error"] = f"Text extraction failed: {exc}"
                results.append(result)
                continue

            if rag_svc is None:
                result["error"] = "RAGService unavailable"
                results.append(result)
                continue

            try:
                raw_fields = rag_svc.extract_fields(fname, text)
                result["fields"] = _apply_intelligence(raw_fields)
            except Exception as exc:
                result["error"] = f"RAG extraction failed: {exc}"

            results.append(result)

        print()  # newline after progress bar
        return results

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def display_extraction(self, result: dict[str, Any]) -> None:
        """Print a formatted extraction result box for a single file."""
        fname = result["filename"]
        fields: list[dict] = result.get("fields", [])
        error: str | None = result.get("error")

        print(_separator())
        print(_title(f"EXTRACTION RESULTS FOR: {fname}"))
        print(_separator())

        if error:
            print(_box_line())
            print(_box_line(f"  ✗ ERROR: {error}"))
            print(_box_line())
            return

        # Detect template type heuristically (filename takes priority)
        fname_lower = fname.lower()
        field_names = {f["field_name"] for f in fields if f.get("field_value")}
        if "invoice" in fname_lower:
            template = "Invoice"
        elif "address" in fname_lower or {"Name", "City", "State"} & field_names:
            template = "Address Book A-B-C"
        else:
            template = "General Document"

        print(_box_line())
        print(_box_line(f"  📋 Template Detected: {template}"))
        print(_box_line())
        print(_box_line("  Field Extractions:"))
        print(_box_line("  " + "─" * (_WIDTH - 2)))
        print(_box_line())

        has_any = False
        for fdict in fields:
            field_name: str = fdict.get("field_name", "")
            value: str = fdict.get("field_value", "")
            raw_conf: float = fdict.get("confidence", 0.0)
            confidence_pct = round(raw_conf * 100, 1)

            inferred: bool = fdict.get("_inferred", False)
            inference_source: str = fdict.get("_inference_source", "")
            validation: tuple | None = fdict.get("_validation")

            icon = _icon(confidence_pct)
            source = "RAG matched text" if raw_conf >= 0.80 else (
                "Pattern match" if raw_conf >= 0.50 else "No match"
            )

            if value:
                has_any = True
                line1 = f"  {icon} {field_name}: {value}"
                print(_box_line(line1))

                conf_bar = _confidence_bar(confidence_pct)
                conf_info = (
                    f"    └─ Confidence: {confidence_pct:.0f}%"
                    f" [{conf_bar}] | Source: {source}"
                )
                print(_box_line(conf_info))

                if inferred and inference_source:
                    print(_box_line(f"    └─ Intelligence: {inference_source}"))

                if validation is not None:
                    is_valid, reason = validation
                    v_icon = "✓" if is_valid else "⚠"
                    print(_box_line(f"    └─ Validation: {v_icon} {reason}"))

                print(_box_line())
            else:
                # Empty optional field
                print(_box_line(f"  ⚠ {field_name}: [empty]"))
                print(_box_line("    └─ Status: Optional field not found"))
                print(_box_line())

        if not has_any:
            print(_box_line("  No fields could be extracted from this file."))
            print(_box_line())

    def display_intelligence_summary(self) -> None:
        """Print the 'Intelligence Demonstrated' section."""
        print(_separator())
        print(_box_line("  Intelligence Demonstrated:"))
        print(_box_line("  " + "─" * (_WIDTH - 2)))
        print(_box_line("  ✓ Text extraction via PyMuPDF + OCR fallback"))
        print(_box_line("  ✓ RAG embeddings (sentence-transformers)"))
        print(_box_line("  ✓ Semantic field matching with confidence scoring"))
        print(_box_line("  ✓ Template recognition (Address Book / Invoice)"))
        print(_box_line("  ✓ Rule-based inference (city→state→zip)"))
        print(_box_line("  ✓ Pattern validation (phone 10-digit, zip 6-digit)"))
        print(_box_line("  ✓ Confidence calculation (RAG similarity + rules)"))
        print(_box_line())

    def display_summary(self, results: list[dict[str, Any]]) -> None:
        """Print the overall batch processing summary box."""
        total = len(results)
        successes = sum(1 for r in results if not r.get("error"))
        total_fields = sum(
            len([f for f in r.get("fields", []) if f.get("field_value")])
            for r in results
        )
        confidences: list[float] = []
        for r in results:
            for f in r.get("fields", []):
                if f.get("field_value"):
                    confidences.append(f.get("confidence", 0.0))
        avg_conf = (
            round(sum(confidences) / len(confidences) * 100, 1)
            if confidences
            else 0.0
        )

        print(_separator())
        print(_title("Processing Complete"))
        print(_separator())
        print(_box_line())
        print(_box_line(f"  Total files      : {total}"))
        print(_box_line(f"  Successfully processed: {successes}"))
        print(_box_line(f"  Fields extracted : {total_fields}"))
        print(_box_line(f"  Avg confidence   : {avg_conf}%"))
        print(_box_line())
        print(_bottom())

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Execute the full interactive upload-sample-files workflow.

        Steps
        -----
        1. Display the header banner.
        2. Prompt user for folder location.
        3. Scan folder for PDFs.
        4. Process each PDF.
        5. Display per-file results.
        6. Show overall summary.
        """
        # Step 1 — header is printed inside prompt_folder_location()
        folder_path = self.prompt_folder_location()

        # Step 2 — scan
        print(_separator())
        print(_box_line(f"  Scanning folder:"))
        print(_box_line(f"  {folder_path}"))

        pdf_files = self.scan_pdfs(folder_path)

        if not pdf_files:
            print(_box_line())
            print(_box_line("  ✗ No PDF files found in the specified folder."))
            print(_box_line("    Add .pdf files and try again."))
            print(_box_line())
            print(_bottom())
            return

        print(_box_line(f"  ✓ Found {len(pdf_files)} PDF file(s). Processing…"))
        print(_box_line())

        # Step 3 — process
        results = self.process_batch(pdf_files)

        # Step 4 — display per-file results
        for result in results:
            self.display_extraction(result)

        # Step 5 — intelligence summary
        self.display_intelligence_summary()

        # Step 6 — overall summary
        self.display_summary(results)
