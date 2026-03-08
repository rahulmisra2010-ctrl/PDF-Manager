/**
 * LogicRuleSection.js — Upload and manage logic/rules documents.
 *
 * Props:
 *   logicFiles   {Array}    List of uploaded logic rule files from backend
 *   onUpload     {func}     Called with File when user selects a document
 *   onDelete     {func}     Called with ruleId
 *   onExport     {func}     Called to export all rules as JSON
 *   loading      {boolean}
 *   error        {string}
 */

import React, { useCallback, useRef, useState } from 'react';

const TYPE_BADGE = {
  text:    { cls: 'rule-badge--text',    label: 'TEXT' },
  numeric: { cls: 'rule-badge--numeric', label: 'NUM' },
  date:    { cls: 'rule-badge--date',    label: 'DATE' },
};

function RulesBadge({ type }) {
  const t = TYPE_BADGE[type?.toLowerCase()] || { cls: 'rule-badge--other', label: type?.toUpperCase() || '?' };
  return <span className={`rule-badge ${t.cls}`}>{t.label}</span>;
}

function RulesTable({ rules }) {
  if (!rules || rules.length === 0) {
    return <p style={{ fontSize: '0.76rem', color: '#94a3b8', margin: '0.5rem 0' }}>No rules extracted.</p>;
  }

  return (
    <div className="rules-table__wrap">
      <table className="rules-table">
        <thead>
          <tr>
            <th>Field</th>
            <th>Type</th>
            <th>Pattern</th>
            <th>Example</th>
            <th>Required</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => (
            <tr key={rule.rule_id ?? rule.field_name}>
              <td title={rule.field_name}>{rule.field_name}</td>
              <td><RulesBadge type={rule.field_type} /></td>
              <td title={rule.pattern}>
                <code style={{ fontSize: '0.7rem', color: '#7c3aed' }}>{rule.pattern || '—'}</code>
              </td>
              <td title={rule.example}>{rule.example || '—'}</td>
              <td>{rule.required ? '✅' : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LogicFileItem({ file, onDelete }) {
  const [open, setOpen] = useState(false);
  const rules = file.extracted_rules || [];

  const fileIcon = {
    pdf: '📕',
    xlsx: '📗',
    xls: '📗',
    csv: '📊',
    docx: '📘',
    doc: '📘',
  }[file.file_type] || '📄';

  return (
    <li className="sample-item" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
        <span className="sample-item__icon">{fileIcon}</span>
        <div className="sample-item__info">
          <div className="sample-item__name" title={file.filename}>{file.filename}</div>
          <div className="sample-item__meta">
            {new Date(file.upload_date).toLocaleDateString()} · {rules.length} rule{rules.length !== 1 ? 's' : ''}
            {' · '}<span style={{ textTransform: 'uppercase', color: '#0ea5e9' }}>{file.file_type}</span>
          </div>
        </div>
        <div className="sample-item__actions">
          <span className="sample-item__badge sample-item__badge--trained">{file.training_status}</span>
          <button
            className="adv-btn adv-btn--ghost"
            style={{ padding: '0.2rem 0.55rem', fontSize: '0.72rem' }}
            onClick={() => setOpen((p) => !p)}
            title={open ? 'Hide rules' : 'Show extracted rules'}
          >
            {open ? '▲' : '▼'}
          </button>
          <button
            className="adv-btn adv-btn--danger"
            style={{ padding: '0.2rem 0.45rem', fontSize: '0.72rem' }}
            onClick={() => onDelete(file.rule_id)}
            title="Delete logic file"
          >
            🗑
          </button>
        </div>
      </div>

      {open && (
        <div style={{ marginTop: '0.5rem' }}>
          <RulesTable rules={rules} />
        </div>
      )}
    </li>
  );
}

function LogicRuleSection({ logicFiles = [], onUpload, onDelete, onExport, loading, error }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) onUpload(file);
    },
    [onUpload],
  );

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) onUpload(file);
    e.target.value = '';
  };

  const totalRules = logicFiles.reduce((acc, f) => acc + (f.extracted_rules || []).length, 0);

  const handleExportAll = () => {
    const allRules = logicFiles.flatMap((f) =>
      (f.extracted_rules || []).map((r) => ({ ...r, source_file: f.filename })),
    );
    const blob = new Blob([JSON.stringify(allRules, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'logic_rules.json';
    a.click();
    URL.revokeObjectURL(url);
    if (onExport) onExport(allRules);
  };

  return (
    <div className="advanced-section">
      <div className="advanced-section__head advanced-section__head--logic">
        <h3 className="advanced-section__title">
          📋 Logic Rules
        </h3>
        <span className="file-count-badge">{totalRules} rule{totalRules !== 1 ? 's' : ''}</span>
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
          aria-label="Upload logic/rules document"
        >
          <div className="upload-area__icon">📎</div>
          <p className="upload-area__text">
            {loading ? 'Uploading…' : 'Drag & drop or click to upload a logic document'}
          </p>
          <p className="upload-area__hint">PDF · Excel (xlsx/xls) · CSV · Word (docx/doc) · Max 50 MB</p>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.xlsx,.xls,.csv,.docx,.doc,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            style={{ display: 'none' }}
            onChange={handleFileChange}
            multiple={false}
          />
        </div>

        {error && (
          <div className="adv-error">⚠️ {error}</div>
        )}

        {/* Export all rules */}
        {totalRules > 0 && (
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              className="adv-btn adv-btn--ghost"
              onClick={handleExportAll}
              title="Export all rules as JSON"
              style={{ fontSize: '0.75rem' }}
            >
              ⬇ Export Rules JSON
            </button>
          </div>
        )}

        {/* File list */}
        {logicFiles.length === 0 && !loading ? (
          <div className="adv-empty">
            <div className="adv-empty__icon">📋</div>
            <div>No logic documents uploaded yet.</div>
            <div>Upload PDF, Excel, or Word files with field definitions and validation rules.</div>
          </div>
        ) : (
          <ul className="sample-list">
            {logicFiles.map((f) => (
              <LogicFileItem
                key={f.rule_id}
                file={f}
                onDelete={onDelete}
              />
            ))}
          </ul>
        )}

        {loading && (
          <div className="adv-loading">⏳ Processing…</div>
        )}

        {/* Example logic format hint */}
        {logicFiles.length === 0 && !loading && (
          <div style={{
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '6px',
            padding: '0.75rem',
            fontSize: '0.73rem',
            color: '#64748b',
          }}>
            <strong>💡 Excel/CSV format hint:</strong><br />
            Columns: <code>Field Name | Field Type | Pattern | Example | Description | Required</code><br />
            Example row: <code>Invoice ID | TEXT | INV-XXXXX | INV-12345 | Invoice code | Yes</code>
          </div>
        )}
      </div>
    </div>
  );
}

export default LogicRuleSection;
