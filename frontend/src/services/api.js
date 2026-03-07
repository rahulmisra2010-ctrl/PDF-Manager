/**
 * API client for the PDF-Manager backend.
 * All functions return the parsed JSON response body.
 */

const API_BASE_URL =
  process.env.REACT_APP_API_URL || 'http://localhost:5000/api/v1';

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
      message = body.detail || message;
    } catch (_) {
      // ignore parse errors
    }
    throw new Error(message);
  }

  return response.json();
}

/**
 * Upload a PDF file to the backend.
 * @param {File} file
 * @returns {Promise<{document_id: string, filename: string, status: string, message: string}>}
 */
export async function uploadPDF(file) {
  const formData = new FormData();
  formData.append('file', file);

  return apiFetch('/upload', {
    method: 'POST',
    body: formData,
  });
}

/**
 * Trigger data extraction for an uploaded document.
 * @param {string} documentId
 * @returns {Promise<ExtractionResult>}
 */
export async function extractData(documentId) {
  return apiFetch(`/extract/${encodeURIComponent(documentId)}`, {
    method: 'POST',
  });
}

/**
 * Save edited field data for a document.
 * @param {string} documentId
 * @param {Array} fields - array of ExtractedField objects
 * @returns {Promise<{document_id: string, status: string, updated_fields: number}>}
 */
export async function editData(documentId, fields) {
  return apiFetch('/edit', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_id: documentId, fields }),
  });
}

/**
 * Export a document in the specified format.
 * @param {string} documentId
 * @param {string} format - 'pdf' | 'json' | 'csv'
 * @returns {Promise<{document_id: string, download_url: string, format: string, expires_at: string}>}
 */
export async function exportDocument(documentId, format = 'pdf') {
  return apiFetch('/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_id: documentId, format }),
  });
}

/**
 * List all documents with pagination.
 * @param {number} page
 * @param {number} pageSize
 * @returns {Promise<DocumentListResponse>}
 */
export async function listDocuments(page = 1, pageSize = 20) {
  return apiFetch(`/documents?page=${page}&page_size=${pageSize}`);
}

/**
 * Get details for a single document.
 * @param {string} documentId
 * @returns {Promise<any>}
 */
export async function getDocument(documentId) {
  return apiFetch(`/documents/${encodeURIComponent(documentId)}`);
}

/**
 * Delete a document.
 * @param {string} documentId
 * @returns {Promise<{status: string, document_id: string}>}
 */
export async function deleteDocument(documentId) {
  return apiFetch(`/documents/${encodeURIComponent(documentId)}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// RAG API
// ---------------------------------------------------------------------------

/**
 * Run RAG-based field extraction for a document.
 * @param {string|number} documentId
 * @returns {Promise<{document_id: number, fields: Array, page_count: number}>}
 */
export async function ragExtract(documentId) {
  return apiFetch(`/extract/rag/${encodeURIComponent(documentId)}`, {
    method: 'POST',
  });
}

/**
 * Get all extracted fields for a document.
 * @param {string|number} documentId
 * @returns {Promise<{document_id: number, fields: Array}>}
 */
export async function getFields(documentId) {
  return apiFetch(`/fields/${encodeURIComponent(documentId)}`);
}

/**
 * Update a single extracted field value.
 * @param {number} fieldId
 * @param {string} value
 * @returns {Promise<{message: string, field: object}>}
 */
export async function updateField(fieldId, value) {
  return apiFetch(`/fields/${encodeURIComponent(fieldId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  });
}

/**
 * Get edit history for a single field.
 * @param {number} fieldId
 * @returns {Promise<{field_id: number, history: Array}>}
 */
export async function getFieldHistory(fieldId) {
  return apiFetch(`/fields/${encodeURIComponent(fieldId)}/history`);
}

/**
 * List all RAG text files stored on the server.
 * @returns {Promise<{files: Array}>}
 */
export async function listRagFiles() {
  return apiFetch('/rag/files');
}
