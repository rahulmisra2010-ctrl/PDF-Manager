/**
 * API client for the PDF-Manager backend.
 * All functions return the parsed JSON response body.
 */

const API_BASE_URL =
  process.env.REACT_APP_API_URL
    ? `${process.env.REACT_APP_API_URL}/api/v1`
    : '/api/v1';

/**
 * Generic fetch wrapper with error handling.
 * @param {string} path    - API path (e.g. '/upload')
 * @param {RequestInit} options - fetch options
 * @returns {Promise<any>} - parsed JSON response
 */
async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      message = body.error || body.detail || message;
    } catch (_) {
      // ignore parse errors
    }
    throw new Error(message);
  }

  return response.json();
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

/**
 * Upload a PDF file to the backend.
 * @param {File} file
 * @returns {Promise<{document_id: string|number, filename: string, status: string, message: string}>}
 */
export async function uploadPDF(file) {
  const formData = new FormData();
  formData.append('file', file);

  return apiFetch('/upload', {
    method: 'POST',
    body: formData,
  });
}

// ---------------------------------------------------------------------------
// OCR Extraction
// ---------------------------------------------------------------------------

/**
 * Run OCR extraction on an uploaded document.
 * @param {string|number} documentId
 * @returns {Promise<any>}
 */
export async function runOCRExtraction(documentId) {
  return apiFetch(`/extract/ocr/${encodeURIComponent(documentId)}`, {
    method: 'POST',
  });
}

// ---------------------------------------------------------------------------
// AI / RAG Extraction
// ---------------------------------------------------------------------------

/**
 * Run AI + RAG extraction on an uploaded document.
 * @param {string|number} documentId
 * @param {boolean} [runRag=true]
 * @returns {Promise<any>}
 */
export async function runAIExtraction(documentId, runRag = true) {
  return apiFetch(`/extract/ai/${encodeURIComponent(documentId)}?include_images=true`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_rag: runRag }),
  });
}

// ---------------------------------------------------------------------------
// RAG Extraction
// ---------------------------------------------------------------------------

/**
 * Run RAG-based field extraction on a document.
 * @param {string|number} documentId
 * @returns {Promise<{document_id: number, fields: Array, page_count: number}>}
 */
export async function ragExtract(documentId) {
  return apiFetch(`/extract/rag/${encodeURIComponent(documentId)}`, {
    method: 'POST',
  });
}

// ---------------------------------------------------------------------------
// Fields
// ---------------------------------------------------------------------------

/**
 * Get all extracted fields for a document.
 * @param {string|number} documentId
 * @returns {Promise<Array>}
 */
export async function getFields(documentId) {
  return apiFetch(`/fields/${encodeURIComponent(documentId)}`);
}

/**
 * Update a single extracted field.
 * @param {number} fieldId
 * @param {string} newValue
 * @returns {Promise<any>}
 */
export async function updateField(fieldId, newValue) {
  return apiFetch(`/fields/${encodeURIComponent(fieldId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value: newValue }),
  });
}

/**
 * Get field edit history.
 * @param {number} fieldId
 * @returns {Promise<Array>}
 */
export async function getFieldHistory(fieldId) {
  return apiFetch(`/fields/${encodeURIComponent(fieldId)}/history`);
}

// ---------------------------------------------------------------------------
// OCR Confidence & Heatmap
// ---------------------------------------------------------------------------

/**
 * Get OCR confidence data for a document.
 * @param {string|number} documentId
 * @returns {Promise<any>}
 */
export async function getOCRConfidence(documentId) {
  return apiFetch(`/ocr/${encodeURIComponent(documentId)}/confidence`);
}

/**
 * Get the confidence heatmap for a document page.
 * @param {string|number} documentId
 * @param {number} [page=1]
 * @param {boolean} [includeImage=false]
 * @returns {Promise<any>}
 */
export async function getHeatmap(documentId, page = 1, includeImage = false) {
  const params = new URLSearchParams({ page, image: includeImage ? 'true' : 'false' });
  return apiFetch(`/documents/${encodeURIComponent(documentId)}/heatmap?${params}`);
}

// ---------------------------------------------------------------------------
// PDF Serving
// ---------------------------------------------------------------------------

/**
 * Build the URL to serve the original PDF for a document.
 * @param {string|number} documentId
 * @returns {string}
 */
export function getPDFUrl(documentId) {
  return `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/pdf`;
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

/**
 * List all documents with pagination.
 * @param {number} page
 * @param {number} perPage
 * @returns {Promise<any>}
 */
export async function listDocuments(page = 1, perPage = 20) {
  return apiFetch(`/documents?page=${page}&per_page=${perPage}`);
}

/**
 * Get details for a single document.
 * @param {string|number} documentId
 * @returns {Promise<any>}
 */
export async function getDocument(documentId) {
  return apiFetch(`/documents/${encodeURIComponent(documentId)}`);
}

/**
 * Delete a document.
 * @param {string|number} documentId
 * @returns {Promise<{status: string, document_id: string}>}
 */
export async function deleteDocument(documentId) {
  return apiFetch(`/documents/${encodeURIComponent(documentId)}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// Legacy helpers (kept for backward compatibility with older components)
// ---------------------------------------------------------------------------

/** @deprecated Use runOCRExtraction or runAIExtraction */
export async function extractData(documentId) {
  return runOCRExtraction(documentId);
}

/** @deprecated Use updateField */
export async function editData(documentId, fields) {
  // Best-effort: update each field individually
  const results = [];
  for (const f of fields) {
    if (f.id) {
      results.push(await updateField(f.id, f.value));
    }
  }
  return { status: 'updated', updated_fields: results.length };
}

/** @deprecated Use getPDFUrl + fetch */
export async function exportDocument(documentId, format = 'json') {
  // Fallback: export as JSON by downloading fields
  const fields = await getFields(documentId);
  return { fields, format, document_id: documentId };
}

