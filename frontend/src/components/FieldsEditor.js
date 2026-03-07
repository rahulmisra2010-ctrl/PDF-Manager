/**
 * FieldsEditor.js — Editable fields table for extracted PDF data.
 *
 * Features:
 * - Inline editing for each field value
 * - Confidence badges (Green / Yellow / Red)
 * - Highlights corresponding PDF region on hover
 * - Save / Cancel per field
 * - Displays field type, source (rule / ner / rag), and bounding box
 *
 * Props:
 *   fields           {Array}    Extracted field objects from the API
 *   onFieldUpdate    {func}     Called with (fieldId, newValue) to save a field
 *   onFieldHover     {func}     Called with (bbox | null) on hover to highlight PDF
 *   loading          {boolean}  Show loading skeleton
 */

import React, { useState } from 'react';

const BADGE_COLORS = {
  green:  { background: '#d1fae5', color: '#065f46', label: '✅' },
  yellow: { background: '#fef3c7', color: '#92400e', label: '⚠️' },
  red:    { background: '#fee2e2', color: '#991b1b', label: '❌' },
};

function confidenceBadge(confidence) {
  const pct = Math.round(confidence * 100);
  let key = 'red';
  if (confidence >= 0.85) key = 'green';
  else if (confidence >= 0.65) key = 'yellow';
  const { background, color, label } = BADGE_COLORS[key];
  return (
    <span
      className="fields-editor__badge"
      style={{ background, color }}
      title={`Confidence: ${pct}%`}
    >
      {label} {pct}%
    </span>
  );
}

function FieldRow({ field, onSave, onHover }) {
  const [editing, setEditing] = useState(false);
  const [draftValue, setDraftValue] = useState(field.value || '');
  const [saving, setSaving] = useState(false);

  const handleEdit = () => {
    setDraftValue(field.value || '');
    setEditing(true);
  };

  const handleCancel = () => setEditing(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(field.id, draftValue);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const handleMouseEnter = () => onHover && onHover(field.bbox || null);
  const handleMouseLeave = () => onHover && onHover(null);

  return (
    <tr
      className="fields-editor__row"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <td className="fields-editor__field-name">
        <strong>{field.field_name}</strong>
        {field.is_edited && <span className="fields-editor__edited-tag"> (edited)</span>}
      </td>
      <td className="fields-editor__value">
        {editing ? (
          <input
            className="fields-editor__input"
            value={draftValue}
            onChange={(e) => setDraftValue(e.target.value)}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSave();
              if (e.key === 'Escape') handleCancel();
            }}
            aria-label={`Edit ${field.field_name}`}
          />
        ) : (
          <span className={field.value ? '' : 'fields-editor__empty'}>
            {field.value || '—'}
          </span>
        )}
      </td>
      <td className="fields-editor__confidence">
        {confidenceBadge(field.confidence || 0)}
      </td>
      <td className="fields-editor__type">
        <code>{field.field_type || 'text'}</code>
      </td>
      <td className="fields-editor__source">
        <span className={`fields-editor__source-tag fields-editor__source-tag--${field.source || 'rule'}`}>
          {field.source || 'rule'}
        </span>
      </td>
      <td className="fields-editor__actions">
        {editing ? (
          <>
            <button
              className="fields-editor__btn fields-editor__btn--save"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? '…' : '✓ Save'}
            </button>
            <button
              className="fields-editor__btn fields-editor__btn--cancel"
              onClick={handleCancel}
            >
              ✕
            </button>
          </>
        ) : (
          <button
            className="fields-editor__btn fields-editor__btn--edit"
            onClick={handleEdit}
          >
            ✏️ Edit
          </button>
        )}
      </td>
    </tr>
  );
}

function FieldsEditor({ fields = [], onFieldUpdate, onFieldHover, loading }) {
  if (loading) {
    return (
      <div className="fields-editor fields-editor--loading">
        <p>Loading extracted fields…</p>
      </div>
    );
  }

  if (!fields.length) {
    return (
      <div className="fields-editor fields-editor--empty">
        <p>No fields extracted yet. Run OCR or AI extraction first.</p>
      </div>
    );
  }

  const highConf = fields.filter((f) => (f.confidence || 0) >= 0.85).length;
  const medConf  = fields.filter((f) => (f.confidence || 0) >= 0.65 && (f.confidence || 0) < 0.85).length;
  const lowConf  = fields.length - highConf - medConf;

  return (
    <div className="fields-editor">
      {/* Summary bar */}
      <div className="fields-editor__summary">
        <span className="fields-editor__summary-item fields-editor__summary-item--green">
          ✅ {highConf} high confidence
        </span>
        <span className="fields-editor__summary-item fields-editor__summary-item--yellow">
          ⚠️ {medConf} medium
        </span>
        <span className="fields-editor__summary-item fields-editor__summary-item--red">
          ❌ {lowConf} low
        </span>
      </div>

      <div className="fields-editor__table-wrapper">
        <table className="fields-editor__table">
          <thead>
            <tr>
              <th>Field</th>
              <th>Value</th>
              <th>Confidence</th>
              <th>Type</th>
              <th>Source</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((field) => (
              <FieldRow
                key={field.id || field.field_name}
                field={field}
                onSave={onFieldUpdate}
                onHover={onFieldHover}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default FieldsEditor;
