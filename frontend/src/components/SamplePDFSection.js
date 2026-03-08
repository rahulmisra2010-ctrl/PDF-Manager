/**
 * SamplePDFSection.js — Upload and manage training sample PDFs.
 *
 * Props:
 *   samples         {Array}   List of training samples from the backend
 *   onUpload        {func}    Called with File when user drops/selects a PDF
 *   onMarkFields    {func}    Called with (trainingId, markedFields)
 *   onDelete        {func}    Called with trainingId
 *   loading         {boolean}
 *   error           {string}
 */

import React, { useCallback, useRef, useState } from 'react';

function FieldsPreview({ sample, onMark }) {
  const [expanded, setExpanded] = useState(false);
  const fields = sample.extracted_fields || [];

  if (fields.length === 0) {
    return <p style={{ fontSize: '0.76rem', color: '#94a3b8', marginTop: '0.3rem' }}>No fields extracted.</p>;
  }

  const preview = expanded ? fields : fields.slice(0, 5);

  const handleToggle = (fieldId, current) => {
    const markedFields = fields.map((f) => ({
      field_id: f.field_id,
      is_correct: f.field_id === fieldId ? !current : f.is_marked_correct,
      correction: null,
    }));
    onMark(sample.training_id, markedFields);
  };

  const handleBulkMark = (markAll) => {
    const markedFields = fields.map((f) => ({
      field_id: f.field_id,
      is_correct: markAll,
      correction: null,
    }));
    onMark(sample.training_id, markedFields);
  };

  return (
    <div className="fields-preview">
      <div className="fields-preview__header">
        <span>{fields.length} field{fields.length !== 1 ? 's' : ''} extracted</span>
        <div style={{ display: 'flex', gap: '0.4rem' }}>
          <button
            className="adv-btn adv-btn--success"
            style={{ padding: '0.2rem 0.55rem', fontSize: '0.7rem' }}
            onClick={() => handleBulkMark(true)}
            title="Mark all fields as correct"
          >
            ✓ All
          </button>
          <button
            className="adv-btn adv-btn--ghost"
            style={{ padding: '0.2rem 0.55rem', fontSize: '0.7rem' }}
            onClick={() => handleBulkMark(false)}
            title="Unmark all fields"
          >
            ✕ None
          </button>
        </div>
      </div>
      <table className="fields-preview__table">
        <thead>
          <tr>
            <th>✓</th>
            <th>Value</th>
            <th>Confidence</th>
            <th>Page</th>
          </tr>
        </thead>
        <tbody>
          {preview.map((f) => (
            <tr key={f.field_id}>
              <td>
                <input
                  type="checkbox"
                  checked={!!f.is_marked_correct}
                  onChange={() => handleToggle(f.field_id, f.is_marked_correct)}
                  title="Mark as correct ground truth"
                />
              </td>
              <td title={f.value}>{f.value}</td>
              <td>{f.confidence != null ? `${Math.round(f.confidence * 100)}%` : '—'}</td>
              <td>{f.page_number ?? 1}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {fields.length > 5 && (
        <div style={{ padding: '0.35rem 0.6rem', borderTop: '1px solid #f1f5f9' }}>
          <button
            className="adv-btn adv-btn--ghost"
            style={{ padding: '0.2rem 0.55rem', fontSize: '0.72rem', width: '100%' }}
            onClick={() => setExpanded((p) => !p)}
          >
            {expanded ? `▲ Show less` : `▼ Show ${fields.length - 5} more`}
          </button>
        </div>
      )}
    </div>
  );
}

function SampleItem({ sample, onMark, onDelete }) {
  const [open, setOpen] = useState(false);
  const markedCount = (sample.extracted_fields || []).filter((f) => f.is_marked_correct).length;

  const badgeClass = {
    trained: 'sample-item__badge--trained',
    pending_confirmation: 'sample-item__badge--pending',
    failed: 'sample-item__badge--failed',
  }[sample.training_status] || 'sample-item__badge--pending';

  return (
    <li className="sample-item" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
        <span className="sample-item__icon">📄</span>
        <div className="sample-item__info">
          <div className="sample-item__name" title={sample.filename}>{sample.filename}</div>
          <div className="sample-item__meta">
            {new Date(sample.upload_date).toLocaleDateString()} ·{' '}
            {markedCount}/{(sample.extracted_fields || []).length} confirmed
            {sample.confidence_avg != null && ` · avg ${Math.round(sample.confidence_avg * 100)}% conf`}
          </div>
        </div>
        <div className="sample-item__actions">
          <span className={`sample-item__badge ${badgeClass}`}>
            {sample.training_status === 'pending_confirmation' ? 'Pending' :
             sample.training_status === 'trained' ? 'Trained' : sample.training_status}
          </span>
          <button
            className="adv-btn adv-btn--ghost"
            style={{ padding: '0.2rem 0.55rem', fontSize: '0.72rem' }}
            onClick={() => setOpen((p) => !p)}
            title={open ? 'Hide fields' : 'Show extracted fields'}
          >
            {open ? '▲' : '▼'}
          </button>
          <button
            className="adv-btn adv-btn--danger"
            style={{ padding: '0.2rem 0.45rem', fontSize: '0.72rem' }}
            onClick={() => onDelete(sample.training_id)}
            title="Delete sample"
          >
            🗑
          </button>
        </div>
      </div>

      {open && (
        <FieldsPreview sample={sample} onMark={onMark} />
      )}
    </li>
  );
}

function SamplePDFSection({ samples = [], onUpload, onMarkFields, onDelete, loading, error }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file && file.type === 'application/pdf') {
        onUpload(file);
      }
    },
    [onUpload],
  );

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) onUpload(file);
    e.target.value = '';
  };

  const totalFields = samples.reduce((acc, s) => acc + (s.extracted_fields || []).length, 0);
  const confirmedFields = samples.reduce(
    (acc, s) => acc + (s.extracted_fields || []).filter((f) => f.is_marked_correct).length,
    0,
  );

  return (
    <div className="advanced-section">
      <div className="advanced-section__head">
        <h3 className="advanced-section__title">
          📄 Sample PDFs
        </h3>
        <span className="file-count-badge">{samples.length} file{samples.length !== 1 ? 's' : ''}</span>
      </div>

      <div className="advanced-section__body">
        {/* Upload area */}
        <div
          className={`upload-area ${dragging ? 'upload-area--active' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
          aria-label="Upload sample PDF"
        >
          <div className="upload-area__icon">📎</div>
          <p className="upload-area__text">
            {loading ? 'Uploading…' : 'Drag & drop or click to upload a sample PDF'}
          </p>
          <p className="upload-area__hint">PDF only · Max 50 MB</p>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,application/pdf"
            style={{ display: 'none' }}
            onChange={handleFileChange}
            multiple={false}
          />
        </div>

        {error && (
          <div className="adv-error">⚠️ {error}</div>
        )}

        {/* Stats */}
        {samples.length > 0 && (
          <p style={{ fontSize: '0.77rem', color: '#64748b', margin: 0 }}>
            📊 {confirmedFields} confirmed field{confirmedFields !== 1 ? 's' : ''} from {totalFields} extracted across {samples.length} sample{samples.length !== 1 ? 's' : ''}
          </p>
        )}

        {/* Sample list */}
        {samples.length === 0 && !loading ? (
          <div className="adv-empty">
            <div className="adv-empty__icon">📂</div>
            <div>No sample PDFs uploaded yet.</div>
            <div>Upload PDFs to start training the suggestion engine.</div>
          </div>
        ) : (
          <ul className="sample-list">
            {samples.map((s) => (
              <SampleItem
                key={s.training_id}
                sample={s}
                onMark={onMarkFields}
                onDelete={onDelete}
              />
            ))}
          </ul>
        )}

        {loading && (
          <div className="adv-loading">⏳ Processing…</div>
        )}
      </div>
    </div>
  );
}

export default SamplePDFSection;
