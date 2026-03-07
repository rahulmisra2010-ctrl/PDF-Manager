/**
 * RAGExtractionPage.js — Split-layout RAG extraction page.
 *
 * Left panel : embedded PDF viewer (react-pdf / iframe fallback)
 * Right panel: editable address-book fields with confidence badges
 *              and per-field edit history.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  ragExtract,
  getFields,
  updateField,
  getFieldHistory,
} from '../services/api';

// ---------------------------------------------------------------------------
// Confidence badge
// ---------------------------------------------------------------------------
function ConfidenceBadge({ confidence }) {
  const pct = Math.round((confidence || 0) * 100);
  let cls = 'badge ';
  if (pct >= 80) cls += 'bg-success';
  else if (pct >= 50) cls += 'bg-warning text-dark';
  else if (pct > 0) cls += 'bg-danger';
  else cls += 'bg-secondary';
  return (
    <span className={cls} style={{ fontSize: '0.7rem', minWidth: 38 }} title={`Confidence: ${pct}%`}>
      {pct}%
    </span>
  );
}

// ---------------------------------------------------------------------------
// FieldHistoryPanel
// ---------------------------------------------------------------------------
function FieldHistoryPanel({ fieldId, open }) {
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || history !== null) return;
    setLoading(true);
    getFieldHistory(fieldId)
      .then(data => setHistory(data.history || []))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [open, fieldId, history]);

  if (!open) return null;

  if (loading) return <div className="text-muted small ps-2 py-1">Loading…</div>;
  if (error)   return <div className="text-danger small ps-2 py-1">Error: {error}</div>;
  if (!history || history.length === 0)
    return <div className="text-muted small ps-2 py-1 fst-italic">No edits recorded yet.</div>;

  return (
    <div className="ps-2 mt-1" style={{ borderLeft: '3px solid #dee2e6' }}>
      {history.map(h => (
        <div key={h.id} className="small text-muted py-1">
          <span className="text-danger">{h.old_value ?? '(empty)'}</span>
          {' → '}
          <span className="text-success">{h.new_value ?? '(empty)'}</span>
          {' '}
          <span className="fst-italic">
            by {h.edited_by || 'unknown'} on {h.edited_at ? h.edited_at.slice(0, 16) : ''}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FieldRow
// ---------------------------------------------------------------------------
function FieldRow({ field, onSave }) {
  const [value, setValue] = useState(field.value || '');
  const [saving, setSaving] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const isEdited = value !== (field.value || '');

  const handleSave = async () => {
    if (!isEdited) return;
    setSaving(true);
    try {
      await onSave(field.id, value);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mb-3">
      <div className="d-flex justify-content-between align-items-center mb-1">
        <label
          className="form-label mb-0 fw-semibold text-uppercase"
          style={{ fontSize: '0.75rem', letterSpacing: '0.04em', color: '#6c757d' }}
        >
          {field.field_name}
        </label>
        <div className="d-flex gap-1 align-items-center">
          <ConfidenceBadge confidence={field.confidence} />
          <button
            className="btn btn-sm btn-outline-secondary py-0 px-1"
            style={{ fontSize: '0.7rem' }}
            onClick={() => setShowHistory(h => !h)}
            title="Toggle history"
          >
            ⏱
          </button>
        </div>
      </div>

      <div className="input-group input-group-sm">
        <input
          type="text"
          className={`form-control ${isEdited ? 'border-warning bg-warning bg-opacity-10' : ''}`}
          value={value}
          onChange={e => setValue(e.target.value)}
          placeholder="(empty)"
        />
        {isEdited && (
          <button
            className="btn btn-outline-primary"
            onClick={handleSave}
            disabled={saving}
            title="Save this field"
          >
            {saving ? '…' : '✓'}
          </button>
        )}
      </div>

      <FieldHistoryPanel fieldId={field.id} open={showHistory} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// RAGExtractionPage
// ---------------------------------------------------------------------------
export default function RAGExtractionPage({ document: doc }) {
  const [fields, setFields] = useState([]);
  const [status, setStatus] = useState(null);  // { message, type }
  const [extracting, setExtracting] = useState(false);
  const [pdfSrc, setPdfSrc] = useState(null);

  // Build the PDF URL for the iframe
  useEffect(() => {
    if (doc?.documentId) {
      setPdfSrc(`/api/v1/documents/${doc.documentId}/pdf`);
      // Load existing fields
      getFields(doc.documentId)
        .then(data => setFields(data.fields || []))
        .catch(() => setFields([]));
    }
  }, [doc]);

  const showStatus = (message, type = 'info') => {
    setStatus({ message, type });
    if (type === 'success') setTimeout(() => setStatus(null), 4000);
  };

  const handleExtract = useCallback(async () => {
    if (!doc?.documentId) return;
    setExtracting(true);
    showStatus('Running RAG extraction…', 'info');
    try {
      const result = await ragExtract(doc.documentId);
      setFields(result.fields || []);
      showStatus(`Extraction complete — ${(result.fields || []).length} fields found.`, 'success');
    } catch (err) {
      showStatus(`Extraction failed: ${err.message}`, 'danger');
    } finally {
      setExtracting(false);
    }
  }, [doc]);

  const handleSaveField = useCallback(async (fieldId, value) => {
    try {
      const result = await updateField(fieldId, value);
      setFields(prev =>
        prev.map(f => f.id === fieldId ? { ...f, value: result.field.value, is_edited: true } : f)
      );
      showStatus('Field saved.', 'success');
    } catch (err) {
      showStatus(`Save failed: ${err.message}`, 'danger');
    }
  }, []);

  if (!doc) {
    return (
      <div className="alert alert-warning">
        No document selected. Upload a PDF first.
      </div>
    );
  }

  return (
    <div className="container-fluid p-0">
      {/* Status bar */}
      {status && (
        <div className={`alert alert-${status.type} py-2 px-3 mb-2 small`}>
          {status.message}
        </div>
      )}

      <div className="d-flex gap-2" style={{ height: 'calc(100vh - 140px)' }}>

        {/* ── Left: PDF Viewer ── */}
        <div
          style={{
            flex: '0 0 55%',
            background: '#525659',
            borderRadius: 8,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            style={{
              background: '#1a1a1a',
              padding: '0.5rem 0.75rem',
              color: '#ccc',
              fontSize: '0.82rem',
              fontWeight: 600,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>📄 PDF Viewer — {doc.filename}</span>
          </div>
          <iframe
            src={pdfSrc}
            title="PDF Viewer"
            style={{ flex: 1, border: 'none', width: '100%' }}
          />
        </div>

        {/* ── Right: Fields Editor ── */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            border: '1px solid #dee2e6',
            borderRadius: 8,
            overflow: 'hidden',
            background: '#fff',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '0.6rem 1rem',
              background: '#f8f9fa',
              borderBottom: '1px solid #dee2e6',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <strong style={{ fontSize: '0.9rem' }}>✏️ Extracted Fields</strong>
            <button
              className="btn btn-primary btn-sm"
              onClick={handleExtract}
              disabled={extracting}
            >
              {extracting ? '⏳ Extracting…' : '🤖 RAG Extract'}
            </button>
          </div>

          {/* Fields list */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '1rem' }}>
            {fields.length === 0 ? (
              <div className="text-center text-muted py-4">
                <div style={{ fontSize: '2rem' }}>📭</div>
                <div>No fields extracted yet.</div>
                <div className="small">Click <strong>RAG Extract</strong> to run extraction.</div>
              </div>
            ) : (
              fields.map(f => (
                <FieldRow key={f.id} field={f} onSave={handleSaveField} />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
