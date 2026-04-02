# Extract PDF Headers

`tools/extract_pdf_headers.py` is a command-line utility that extracts and
prints three kinds of "header" information from any PDF file:

| Section | What it shows |
|---------|---------------|
| **PDF Metadata** | Title, Author, Subject, Keywords, Creator, Producer, CreationDate, ModDate |
| **Outline / Bookmarks** | Document outline tree (if the PDF contains bookmarks) |
| **Top-of-Page Text** | Text found in the top 15 % of every page (the visible page header) |

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python ≥ 3.8 | `python --version` |
| `pypdf` ≥ 3.0 | PDF metadata & outline extraction |
| `pdfplumber` ≥ 0.9 | Layout-aware text extraction |

Both packages are listed in [`requirements.txt`](../requirements.txt).

---

## Step-by-Step Setup

### 1. Clone the repository

```bash
# using HTTPS
git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
cd PDF-Manager
```

### 2. Create and activate a virtual environment

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Or install only the tools needed for this script:

```bash
pip install pypdf pdfplumber
```

---

## Place your PDF

You can use the bundled sample or your own file.

### Option A – Use the bundled sample

```
samples/Official_withdrawal_form.pdf   ← already in the repo
```

### Option B – Use your own PDF

Copy your file into the `samples/` folder (or anywhere on disk):

```
samples/Official_withdrawal_form.pdf
```

> **Tip – filenames with spaces** \
> Simply wrap the path in quotes; the script handles any file name.

---

## Run the Script

### Windows (PowerShell / cmd)

```powershell
# Bundled sample
python tools\extract_pdf_headers.py samples\Official_withdrawal_form.pdf

# Your own file (path with spaces)
python tools\extract_pdf_headers.py "C:\Users\RAHUL MISRA\sample_pdfs\Official withdrawal form.pdf"

# Limit to the first 3 pages
python tools\extract_pdf_headers.py samples\Official_withdrawal_form.pdf --pages 3
```

### macOS / Linux

```bash
# Bundled sample
python tools/extract_pdf_headers.py samples/Official_withdrawal_form.pdf

# Your own file (path with spaces)
python tools/extract_pdf_headers.py "/home/user/my pdfs/Official withdrawal form.pdf"

# Limit to the first 3 pages
python tools/extract_pdf_headers.py samples/Official_withdrawal_form.pdf --pages 3
```

---

## Example Output

```
Processing: /path/to/PDF-Manager/samples/Official_withdrawal_form.pdf

============================
  PDF METADATA
============================
  Title          : Official Withdrawal Form
  Author         : PDF Manager
  Subject        : Student Withdrawal
  Creator        : PDF Manager – tools/extract_pdf_headers.py demo
  Producer       : ReportLab

==============================
  OUTLINE / BOOKMARKS
==============================
  (none)

=======================================================
  TOP-OF-PAGE HEADER TEXT  (top 15 % of each page)
=======================================================

  --- Page 1 ---
  Official Withdrawal Form
  Academic Affairs Office – Student Services
```

---

## Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `pdf` (positional) | — | Path to the PDF file (required) |
| `--pages N` | `0` (all) | Scan only the first *N* pages for top-of-page text |

---

## Running the Tests

```bash
pytest test_extract_pdf_headers.py -v
```

The test suite runs against `samples/Official_withdrawal_form.pdf` and
validates metadata extraction, outline extraction, page-header text, and the
CLI entry-point (including paths that contain spaces).

---

## Importing as a Library

The three extractor functions are importable for use in other scripts or tests:

```python
from pathlib import Path
from tools.extract_pdf_headers import smoke_check

result = smoke_check(Path("samples/Official_withdrawal_form.pdf"), max_pages=3)
print(result["metadata"])      # dict
print(result["outline"])       # list
print(result["page_headers"])  # [(page_num, text), ...]
```
