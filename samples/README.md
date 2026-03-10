# Sample PDF Files

This folder contains sample PDF files you can use to demonstrate and test
the PDF Manager RAG extraction system.

## Files

| File | Description |
|------|-------------|
| `address_book_001.pdf` | Address book entry for Rahul Misra (Asansol, WB) |
| `address_book_002.pdf` | Address book entry for Priya Sharma (Kolkata, WB) |
| `invoice_sample.pdf`   | Sample invoice from ABC Supplies Ltd. (Mumbai, MH) |

## How to Use

### Via the CLI

```bash
# From the repository root
python pdf_manager_app.py sample
```

You will be prompted:

```
  ➤  Folder path:
```

Press **Enter** to use this `samples/` folder automatically, or type any
absolute path containing your own PDF files.

### What to Expect

For each PDF the system will:

1. Extract text using PyMuPDF (with OCR fallback for scanned pages)
2. Split text into chunks and embed with `sentence-transformers`
3. Match field queries to the most similar chunks (cosine similarity)
4. Apply regex extraction on the top-k retrieved chunks
5. Apply intelligent post-processing:
   - **City → State inference** (e.g., Asansol → WB)
   - **Zip code pattern validation** (e.g., 7XXXXX for West Bengal)
   - **Phone number normalisation** (10-digit Indian format)
   - **Email format validation**
6. Display fields with confidence scores and intelligence indicators

### Adding Your Own Samples

Place any `.pdf` files in this folder (or any other folder) and run
`python pdf_manager_app.py sample` to process them.
