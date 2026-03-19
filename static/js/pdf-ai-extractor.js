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
let viewer   = null;   // InteractivePDFViewer instance
let fields   = [];     // current extracted fields array
let mode     = 'view'; // 'view' | 'select' | 'detect'
let selStart = null;   // {x, y} drag start in canvas coords

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
      // Re-draw fields for the new page
      const pageFields = fields.filter(f => f.page === pageNum || f.page === undefined);
      viewer.drawFields(pageFields);
      // Update active page highlight in fields panel
      _filterFieldsPanel(pageNum);
    },
  });

  // Render first page
  viewer.renderCurrentPage();

  // ---- Toolbar button wiring ----
  _wire('btn-prev',      () => viewer.prevPage());
  _wire('btn-next',      () => viewer.nextPage());
  _wire('btn-zoom-in',   () => viewer.setZoom(viewer.zoom + 0.25));
  _wire('btn-zoom-out',  () => viewer.setZoom(Math.max(0.5, viewer.zoom - 0.25)));
  _wire('btn-detect',    () => detectAllFields());
  _wire('btn-clear',     () => clearFields());
  _wire('btn-save',      () => saveFields());
  _wire('btn-mode-view', () => setMode('view'));
  _wire('btn-mode-select',() => setMode('select'));

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

    // Merge into global fields, replacing same-page entries
    fields = fields.filter(f => f.page !== viewer.currentPage);
    fields = fields.concat(data.fields || []);

    viewer.drawFields(fields.filter(f => f.page === viewer.currentPage));
    _renderFieldsPanel(fields);
    _setStatus(`Detected ${(data.fields || []).length} field(s) on page ${viewer.currentPage}`, 'success');
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
    };

    // Remove previous field with same label on this page
    fields = fields.filter(f => (f.label || f.field_name) !== fieldName || f.page !== viewer.currentPage);
    fields.push(newField);

    viewer.drawFields(fields.filter(f => f.page === viewer.currentPage));
    _renderFieldsPanel(fields);
    _setStatus(`Extracted "${data.text}" as ${fieldName}`, 'success');
  } catch (err) {
    _setStatus(`Error: ${err.message}`, 'danger');
  }
}

async function saveFields() {
  const cfg = window.AI_CONFIG;
  if (fields.length === 0) { _setStatus('No fields to save.', 'warning'); return; }

  // Collect current values from the input fields
  const toSave = fields.map(f => {
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

  // Highlight bounding boxes on card hover: label in pink, value in green
  card.addEventListener('mouseenter', () => {
    if (field.page && field.page !== viewer.currentPage) return;
    viewer.clearOverlay();
    // Highlight label bbox in pink
    if (field.label_bbox) {
      const { x0, y0, x1, y1 } = field.label_bbox;
      if (x0 !== undefined) {
        viewer.drawHighlight(x0, y0, x1, y1, 'rgba(255,99,132,0.35)', '#e0497a');
      }
    }
    // Highlight value bbox in green/orange
    if (field.bbox) {
      const { x0, y0, x1, y1 } = field.bbox;
      if (x0 !== undefined) {
        viewer.drawHighlight(x0, y0, x1, y1, 'rgba(40,167,69,0.30)', '#28a745');
      }
    }
  });
  card.addEventListener('mouseleave', () => {
    const pageFields = fields.filter(f => f.page === viewer.currentPage || !f.page);
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
    _renderFieldsPanel(fields);
    const pageFields = fields.filter(f => f.page === viewer.currentPage || !f.page);
    viewer.drawFields(pageFields);
  });
  card.querySelector('.field-header').prepend(removeBtn);

  return card;
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

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
