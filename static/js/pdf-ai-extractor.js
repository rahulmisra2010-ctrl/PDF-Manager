/**
 * static/js/pdf-ai-extractor.js
 *
 * AI-powered PDF field extractor.
 *
 * Wires together:
 *  - InteractivePDFViewer for rendering
 *  - Drag-to-select for region extraction
 *  - Auto-detect for whole-page field detection
 *  - Fields panel for editing and saving
 *
 * Expects these globals/data attributes on the page:
 *   window.AI_CONFIG = {
 *     docId:           <int>,
 *     totalPages:      <int>,
 *     pageImageUrl:    '/ai-pdf/{docId}/page/{page}?zoom={zoom}',
 *     detectFieldsUrl: '/ai-pdf/{docId}/detect-fields',
 *     extractRegionUrl:'/ai-pdf/{docId}/extract-region',
 *     saveFieldsUrl:   '/ai-pdf/{docId}/save-fields',
 *     csrfToken:       '<token>',
 *   };
 */

/* global InteractivePDFViewer, AI_CONFIG */
/* exported initAIExtractor */

'use strict';

// ---------------------------------------------------------------------------
// Field type → Bootstrap colour class mapping
// ---------------------------------------------------------------------------
const FIELD_TYPE_CLASSES = {
  email:    'field-type-email',
  phone:    'field-type-phone',
  date:     'field-type-date',
  number:   'field-type-number',
  address:  'field-type-address',
  name:     'field-type-name',
  url:      'field-type-url',
  currency: 'field-type-currency',
  zip_code: 'field-type-zip_code',
  text:     'field-type-text',
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let viewer           = null;   // InteractivePDFViewer instance
let fields           = [];     // current extracted fields array (always tagged with doc_id)
let mode             = 'view'; // 'view' | 'select'
let selStart         = null;   // {x, y} drag start in canvas coords
let filterLabelOnly  = true;   // when true: hide label-only (empty-value) detections

// ---------------------------------------------------------------------------
// Initialise
// ---------------------------------------------------------------------------

function initAIExtractor() {
  const cfg = window.AI_CONFIG;
  if (!cfg) { console.error('AI_CONFIG not set'); return; }

  const selCanvas = document.getElementById('selection-canvas');

  viewer = new InteractivePDFViewer({
    canvasId:        'pdf-canvas',
    overlayCanvasId: 'overlay-canvas',
    pageInputId:     'page-input',
    pageCountId:     'page-count',
    zoomSelectId:    'zoom-select',
    pageImageUrl:    cfg.pageImageUrl,
    initialPage:     1,
    totalPages:      cfg.totalPages,
    onPageRendered(pageNum) {
      // Re-draw only fields that belong to this document and this page
      const pageFields = _visibleFields().filter(
        f => f.page === pageNum || f.page === undefined
      );
      viewer.drawFields(pageFields);
      // Update active page highlight in fields panel
      _filterFieldsPanel(pageNum);
    },
  });

  // ---- Initialise fields from server-provided DB data (scoped to this doc) ----
  if (Array.isArray(cfg.initialFields) && cfg.initialFields.length) {
    // Ensure every entry is tagged with the current document id
    fields = cfg.initialFields
      .filter(f => f.doc_id === cfg.docId)
      .map(f => ({ ...f, doc_id: cfg.docId }));
    _renderFieldsPanel(fields);
  }

  // Render first page (triggers onPageRendered which draws overlays)
  viewer.renderCurrentPage();

  // ---- Toolbar button wiring ----
  _wire('btn-prev',        () => viewer.prevPage());
  _wire('btn-next',        () => viewer.nextPage());
  _wire('btn-zoom-in',     () => viewer.setZoom(viewer.zoom + 0.25));
  _wire('btn-zoom-out',    () => viewer.setZoom(Math.max(0.5, viewer.zoom - 0.25)));
  _wire('btn-detect',      () => detectAllFields());
  _wire('btn-clear',       () => clearFields());
  _wire('btn-save',        () => saveFields());
  _wire('btn-save-sample', () => saveSample());
  _wire('btn-mode-view',   () => setMode('view'));
  _wire('btn-mode-select', () => setMode('select'));

  // ---- Filter toggle ----
  _wire('btn-filter-labels', () => {
    filterLabelOnly = !filterLabelOnly;
    const btn = document.getElementById('btn-filter-labels');
    if (btn) {
      btn.classList.toggle('active', filterLabelOnly);
      btn.title = filterLabelOnly
        ? 'Toggle: hide label-only detections (active — labels hidden)'
        : 'Toggle: hide label-only detections (inactive — all fields shown)';
    }
    // Refresh overlay and sidebar with the new filter state
    const pageFields = _visibleFields().filter(
      f => f.page === viewer.currentPage || f.page === undefined
    );
    viewer.drawFields(pageFields);
    _renderFieldsPanel(_visibleFields());
    _filterFieldsPanel(viewer.currentPage);
  });

  // ---- Drag-to-select on the selection canvas ----
  if (selCanvas) {
    selCanvas.addEventListener('mousedown', onSelMouseDown);
    selCanvas.addEventListener('mousemove', onSelMouseMove);
    selCanvas.addEventListener('mouseup',   onSelMouseUp);
    selCanvas.addEventListener('mouseleave',() => { selStart = null; _clearSelRect(); });
  }

  // ---- Mode display ----
  setMode('view');
}

// ---------------------------------------------------------------------------
// Mode management
// ---------------------------------------------------------------------------

function setMode(newMode) {
  mode = newMode;
  const selCanvas = document.getElementById('selection-canvas');
  const modeLabel = document.getElementById('mode-label');
  const btnView   = document.getElementById('btn-mode-view');
  const btnSelect = document.getElementById('btn-mode-select');

  if (selCanvas) selCanvas.style.pointerEvents = (mode === 'select') ? 'auto' : 'none';
  if (modeLabel) modeLabel.textContent = mode === 'select' ? 'Selection' : 'View';
  if (btnView)   btnView.classList.toggle('active',   mode === 'view');
  if (btnSelect) btnSelect.classList.toggle('active', mode === 'select');
}

// ---------------------------------------------------------------------------
// Drag-to-select handlers
// ---------------------------------------------------------------------------

function onSelMouseDown(e) {
  if (mode !== 'select') return;
  const rect = e.target.getBoundingClientRect();
  selStart = { x: e.clientX - rect.left, y: e.clientY - rect.top };
}

function onSelMouseMove(e) {
  if (!selStart || mode !== 'select') return;
  const rect = e.target.getBoundingClientRect();
  const cur  = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  _drawSelRect(selStart, cur);
}

async function onSelMouseUp(e) {
  if (!selStart || mode !== 'select') return;
  const rect = e.target.getBoundingClientRect();
  const end  = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  _clearSelRect();

  const x0 = Math.min(selStart.x, end.x);
  const y0 = Math.min(selStart.y, end.y);
  const x1 = Math.max(selStart.x, end.x);
  const y1 = Math.max(selStart.y, end.y);
  selStart = null;

  if ((x1 - x0) < 5 || (y1 - y0) < 5) return; // too small

  await extractRegion(x0, y0, x1, y1);
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

async function detectAllFields() {
  const cfg = window.AI_CONFIG;
  _setStatus('Detecting fields…', 'info');
  try {
    const res = await _post(cfg.detectFieldsUrl, {
      page: viewer.currentPage,
      zoom: viewer.zoom,
    });
    const data = await res.json();
    if (!res.ok) { _setStatus(data.error || 'Detection failed', 'danger'); return; }

    // Validate that the response belongs to the current document.
    // The server always returns doc_id; if it doesn't match, discard the result.
    if (data.doc_id !== undefined && data.doc_id !== cfg.docId) {
      _setStatus('Ignored detection result: response belongs to a different document.', 'warning');
      return;
    }

    // Tag every incoming field with the current document id so we can always
    // distinguish this document's fields from any stale/cached entries.
    const incoming = (data.fields || []).map(f => ({ ...f, doc_id: cfg.docId }));

    // Merge: keep fields from OTHER pages that belong to THIS document only,
    // then append the freshly detected fields for the current page.
    fields = fields
      .filter(f => f.doc_id === cfg.docId && f.page !== viewer.currentPage)
      .concat(incoming);

    const visiblePageFields = _visibleFields().filter(
      f => f.page === viewer.currentPage || f.page === undefined
    );
    viewer.drawFields(visiblePageFields);
    _renderFieldsPanel(_visibleFields());

    const total   = incoming.length;
    const paired  = total - (data.unpaired_labels_count || 0);
    const blank   = data.unpaired_labels_count || 0;
    const hidden  = total - _visibleFields().filter(f => f.page === viewer.currentPage).length;
    let msg = blank > 0
      ? `Detected ${total} field(s) on page ${viewer.currentPage}: ${paired} with values, ${blank} label-only`
      : `Detected ${total} label/value pair(s) on page ${viewer.currentPage}`;
    if (hidden > 0) msg += ` (${hidden} hidden by filter)`;
    _setStatus(msg, 'success');
  } catch (err) {
    _setStatus(`Error: ${err.message}`, 'danger');
  }
}

async function extractRegion(x0, y0, x1, y1) {
  const cfg = window.AI_CONFIG;
  _setStatus('Extracting region…', 'info');
  try {
    const res = await _post(cfg.extractRegionUrl, {
      page: viewer.currentPage,
      x0, y0, x1, y1,
      zoom: viewer.zoom,
    });
    const data = await res.json();
    if (!res.ok) { _setStatus(data.error || 'Extraction failed', 'danger'); return; }

    // Prompt user for a field name then add the result
    const fieldName = prompt('Field name for extracted text:', data.field_type || 'field');
    if (!fieldName) return;

    const newField = {
      field_name:  fieldName,
      label:       fieldName,
      text:        data.text,
      value:       data.text,
      confidence:  data.confidence,
      bbox:        data.bbox,
      page:        viewer.currentPage,
      doc_id:      cfg.docId,
    };

    // Remove the previous field with same label on this page.
    // Keeps: fields from other documents OR fields with a different label OR fields on a different page.
    fields = fields.filter(
      f => f.doc_id !== cfg.docId
        || (f.label || f.field_name) !== fieldName
        || f.page !== viewer.currentPage
    );
    fields.push(newField);

    const visiblePageFields = _visibleFields().filter(
      f => f.page === viewer.currentPage || f.page === undefined
    );
    viewer.drawFields(visiblePageFields);
    _renderFieldsPanel(_visibleFields());
    _setStatus(`Extracted "${data.text}" as ${fieldName}`, 'success');
  } catch (err) {
    _setStatus(`Error: ${err.message}`, 'danger');
  }
}

async function saveFields() {
  const cfg = window.AI_CONFIG;
  if (fields.length === 0) { _setStatus('No fields to save.', 'warning'); return; }

  // Only save fields that belong to the currently open document
  const docFields = fields.filter(f => f.doc_id === cfg.docId || f.doc_id === undefined);

  // Collect current values from the input fields
  const toSave = docFields.map(f => {
    const label = f.label || f.field_name || '';
    return {
      field_name: label,
      value:      _getFieldInputValue(label) || f.value || f.text || '',
      confidence: f.confidence || 0.8,
    };
  });

  _setStatus('Saving…', 'info');
  try {
    const res = await _post(cfg.saveFieldsUrl, { fields: toSave });
    const data = await res.json();
    if (!res.ok) { _setStatus(data.error || 'Save failed', 'danger'); return; }
    _setStatus(`Saved ${data.saved} field(s) successfully.`, 'success');
  } catch (err) {
    _setStatus(`Error: ${err.message}`, 'danger');
  }
}

function clearFields() {
  fields = [];
  viewer.clearOverlay();
  _renderFieldsPanel([]);
  _setStatus('Fields cleared.', 'secondary');
}

/**
 * Export all current fields (including blank label-only ones) as a JSON file.
 * Values are taken from the live UI inputs so any manual edits are captured.
 */
function saveSample() {
  if (fields.length === 0) {
    _setStatus('No fields to export. Run Auto-Detect first.', 'warning');
    return;
  }

  const cfg = window.AI_CONFIG;
  // Only export fields belonging to the currently open document
  const docFields = fields.filter(f => f.doc_id === cfg.docId || f.doc_id === undefined);

  // Build { label: value } object — read current input values from the panel
  const sample = {};
  for (const f of docFields) {
    const label = f.label || f.field_name || '';
    if (!label) continue;
    // Prefer the live input value (user may have edited it) over the original value
    const liveValue = _getFieldInputValue(label);
    sample[label] = (liveValue !== null) ? liveValue : (f.value || f.text || '');
  }

  const json    = JSON.stringify(sample, null, 2);
  const blob    = new Blob([json], { type: 'application/json' });
  const url     = URL.createObjectURL(blob);
  const anchor  = document.createElement('a');
  const docId   = window.AI_CONFIG ? window.AI_CONFIG.docId : 'doc';
  anchor.href     = url;
  anchor.download = `sample_doc_${docId}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);

  _setStatus(`Exported ${Object.keys(sample).length} field(s) as JSON sample.`, 'success');
}

// ---------------------------------------------------------------------------
// Fields panel rendering
// ---------------------------------------------------------------------------

function _renderFieldsPanel(allFields) {
  const container = document.getElementById('fields-list');
  if (!container) return;

  if (allFields.length === 0) {
    container.innerHTML = '<p class="text-muted small p-2">No fields extracted yet. '
      + 'Use <strong>Auto-Detect</strong> or switch to <strong>Selection</strong> mode '
      + 'and drag to select regions.</p>';
    return;
  }

  container.innerHTML = '';
  for (const f of allFields) {
    container.appendChild(_makeFieldCard(f));
  }
}

function _filterFieldsPanel(pageNum) {
  // Dim cards not on current page
  const cards = document.querySelectorAll('.field-card');
  cards.forEach(card => {
    const cardPage = parseInt(card.dataset.page || '1', 10);
    card.style.opacity = (cardPage === pageNum || isNaN(cardPage)) ? '1' : '0.4';
  });
}

function _makeFieldCard(field) {
  const card = document.createElement('div');
  card.className = 'field-card';
  // Use label as the stable identifier; fall back to field_name for legacy entries
  const label = field.label || field.field_name || '';
  card.dataset.fieldName = label;
  card.dataset.page      = field.page || '';

  const conf    = Math.round((field.confidence || 0.5) * 100);
  const confStr = `${conf}%`;
  // Display value: prefer explicit 'value', fall back to 'text' for legacy raw entries
  const displayValue = (field.value !== undefined) ? field.value : (field.text || '');

  card.innerHTML = `
    <div class="field-header">
      <span class="field-label-tag">${_esc(label)}</span>
      <span class="field-arrow">→</span>
      ${field.page ? `<span class="badge bg-secondary" style="font-size:0.6rem">p${field.page}</span>` : ''}
    </div>
    <input class="field-value-input"
           type="text"
           placeholder="(no value)"
           data-field-name="${_esc(label)}"
           value="${_esc(displayValue)}">
    <div class="confidence-bar" style="--pct: ${confStr}"></div>
    <div class="confidence-label">Confidence: ${confStr}</div>
  `;

  // Highlight bounding boxes on card hover: use brown labeled highlights
  card.addEventListener('mouseenter', () => {
    if (field.page && field.page !== viewer.currentPage) return;
    viewer.clearOverlay();

    const fieldLabel = field.label || field.field_name || '';
    const fieldValue = (field.value !== undefined) ? field.value : (field.text || '');

    // If field has both label_bbox and bbox, draw combined highlighted section
    if (field.label_bbox && field.bbox) {
      const lbox = field.label_bbox;
      const vbox = field.bbox;
      const combinedX0 = Math.min(lbox.x0 || 0, vbox.x0 || 0);
      const combinedY0 = Math.min(lbox.y0 || 0, vbox.y0 || 0);
      const combinedX1 = Math.max(lbox.x1 || 0, vbox.x1 || 0);
      const combinedY1 = Math.max(lbox.y1 || 0, vbox.y1 || 0);

      if (combinedX0 !== undefined && combinedX0 < combinedX1) {
        viewer.drawLabeledHighlight(
          combinedX0, combinedY0, combinedX1, combinedY1,
          fieldLabel, fieldValue,
          { fillColor: 'rgba(255, 220, 0, 0.35)', strokeColor: '#e6a000' }
        );
      }
    }
    // Draw value bbox with yellow highlight
    else if (field.bbox) {
      const { x0, y0, x1, y1 } = field.bbox;
      if (x0 !== undefined) {
        viewer.drawLabeledHighlight(x0, y0, x1, y1, fieldLabel, fieldValue,
          { fillColor: 'rgba(255, 220, 0, 0.35)', strokeColor: '#e6a000' }
        );
      }
    }
    // Draw label bbox with yellow highlight (label-only)
    else if (field.label_bbox) {
      const { x0, y0, x1, y1 } = field.label_bbox;
      if (x0 !== undefined) {
        viewer.drawLabeledHighlight(x0, y0, x1, y1, fieldLabel, '',
          { fillColor: 'rgba(255, 220, 0, 0.35)', strokeColor: '#e6a000' }
        );
      }
    }
  });
  card.addEventListener('mouseleave', () => {
    const pageFields = _visibleFields().filter(f => f.page === viewer.currentPage || !f.page);
    viewer.drawFields(pageFields);
  });

  // Remove field button
  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.className = 'btn btn-sm btn-link text-danger p-0 float-end';
  removeBtn.style.fontSize = '0.7rem';
  removeBtn.title = 'Remove field';
  removeBtn.textContent = '✕';
  removeBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fields = fields.filter(f => (f.label || f.field_name) !== label || f.page !== field.page);
    _renderFieldsPanel(_visibleFields());
    const pageFields = _visibleFields().filter(f => f.page === viewer.currentPage || !f.page);
    viewer.drawFields(pageFields);
  });
  card.querySelector('.field-header').prepend(removeBtn);

  return card;
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

/**
 * Return the subset of `fields` that should be displayed given the current
 * filter state and document scope.
 *
 * Rules applied (in order):
 *  1. Only fields whose `doc_id` matches the currently open document are kept.
 *     Every field in the array is always tagged with the current doc_id (set
 *     at initialisation and on every detect/extract call), so this check
 *     strictly prevents any stale or cross-document entries from appearing.
 *  2. When `filterLabelOnly` is true, fields with an empty value string are
 *     hidden — these are printed form labels with no user-entered data.
 */
function _visibleFields() {
  const cfg = window.AI_CONFIG;
  return fields.filter(f => {
    // 1. Document scope: reject any field that does not belong to this doc.
    //    All entries in the array must carry doc_id (set at init and detection
    //    time), so we can enforce a strict equality check here.
    if (f.doc_id !== cfg.docId) return false;
    // 2. Label-only filter: hide fields with no extracted value
    if (filterLabelOnly && !f.value && !f.text) return false;
    return true;
  });
}

function _post(url, body) {
  const cfg = window.AI_CONFIG;
  return fetch(url, {
    method:  'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken':  cfg.csrfToken,
    },
    body: JSON.stringify(body),
  });
}

function _wire(id, handler) {
  const el = document.getElementById(id);
  if (el) el.addEventListener('click', handler);
}

function _esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _setStatus(msg, type) {
  const el = document.getElementById('status-bar');
  if (!el) return;
  el.textContent = msg;
  el.className   = `alert alert-${type} py-1 px-2 mb-0 small`;
  el.style.display = 'block';
}

function _getFieldInputValue(fieldName) {
  const input = document.querySelector(`input.field-value-input[data-field-name="${CSS.escape(fieldName)}"]`);
  return input ? input.value : null;
}

// Selection rectangle overlay drawn during drag
function _drawSelRect(start, end) {
  const selCtx = _getSelCtx();
  if (!selCtx) return;
  const canvas = document.getElementById('selection-canvas');
  selCtx.clearRect(0, 0, canvas.width, canvas.height);
  selCtx.save();
  selCtx.strokeStyle = '#0d6efd';
  selCtx.lineWidth   = 2;
  selCtx.setLineDash([6, 3]);
  selCtx.fillStyle   = 'rgba(13,110,253,0.08)';
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  const w = Math.abs(end.x - start.x);
  const h = Math.abs(end.y - start.y);
  selCtx.fillRect(x, y, w, h);
  selCtx.strokeRect(x, y, w, h);
  selCtx.restore();
}

function _clearSelRect() {
  const selCtx = _getSelCtx();
  if (!selCtx) return;
  const canvas = document.getElementById('selection-canvas');
  selCtx.clearRect(0, 0, canvas.width, canvas.height);
}

function _getSelCtx() {
  const canvas = document.getElementById('selection-canvas');
  return canvas ? canvas.getContext('2d') : null;
}

// Keep selection canvas sized to match pdf-canvas
function _syncSelectionCanvas() {
  const src = document.getElementById('pdf-canvas');
  const sel = document.getElementById('selection-canvas');
  if (src && sel) {
    sel.width  = src.width;
    sel.height = src.height;
  }
}

// Re-sync on every page render
document.addEventListener('DOMContentLoaded', () => {
  const pdfCanvas = document.getElementById('pdf-canvas');
  if (pdfCanvas) {
    const observer = new MutationObserver(_syncSelectionCanvas);
    observer.observe(pdfCanvas, { attributes: true, attributeFilter: ['width', 'height'] });
  }
});
