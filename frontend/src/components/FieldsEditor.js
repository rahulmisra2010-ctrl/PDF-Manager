/**
 * FieldsEditor.js — Editable fields table with advanced UX.
 *
 * Features:
 * - Inline editing (click to edit, Enter/Escape to confirm/cancel)
 * - Undo/Redo for field edits (via Zustand store)
 * - Batch edit mode: select multiple rows, apply value to all
 * - Confidence badges (Green ≥85% / Yellow ≥65% / Red <65%)
 * - Hover-to-highlight PDF region (calls onFieldHover with bbox)
 * - Click field → focusField to highlight in PDF
 * - Framer Motion: scale + glow on edit mode entry
 * - SuggestionPanel trigger per field
 * - ARIA labels and keyboard navigation
 *
 * Props:
 *   fields           {Array}    Extracted field objects from the API
 *   onFieldUpdate    {func}     Called with (fieldId, newValue) to save
 *   onFieldHover     {func}     Called with (bbox | null) on hover
 *   onSuggest        {func}     Called with (field) to open suggestion panel
 *   activeFieldId    {string}   Currently active field (PDF sync)
 *   loading          {boolean}  Show loading state
 */

import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import useStore from '../services/store';
import useConfidenceColors from '../hooks/useConfidenceColors';
import { editRowVariants, listContainerVariants, listItemVariants } from '../hooks/useAnimations';
import styles from './styles/FieldsEditor.module.css';

function ConfidenceBadge({ confidence }) {
  const { getColors } = useConfidenceColors();
  const pct = Math.round(confidence * 100);
  const { badge, text, icon } = getColors(confidence);
  return (
    <span
      className={styles.badge}
      style={{ background: badge, color: text }}
      title={`Confidence: ${pct}%`}
      aria-label={`${pct}% confidence`}
    >
      {icon} {pct}%
    </span>
  );
}

function SourceTag({ source }) {
  // Normalize source string: remove underscores/hyphens, capitalize → 'sourcePymupdf'
  const normalized = (source || 'rule').replace(/[-_]/g, '');
  const key = `source${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}`;
  const cls = styles[key] || styles.sourceRule;
  return (
    <span className={`${styles.sourceTag} ${cls}`}>
      {source || 'rule'}
    </span>
  );
}

function FieldRow({ field, onSave, onHover, onSuggest, isActive, batchMode, isSelected, onToggleSelect }) {
  const [editing, setEditing] = useState(false);
  const [draftValue, setDraftValue] = useState(field.value || '');
  const [saving, setSaving] = useState(false);

  const handleEdit = () => {
    setDraftValue(field.value || '');
    setEditing(true);
  };

  const handleCancel = () => setEditing(false);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await onSave(field.id, draftValue);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }, [onSave, field.id, draftValue]);

  const handleMouseEnter = () => onHover && onHover(field.bbox || null);
  const handleMouseLeave = () => onHover && onHover(null);

  const rowClass = [
    styles.row,
    isActive ? styles.rowActive : '',
    editing ? styles.rowEditing : '',
    isSelected ? styles.rowBatchSelected : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <motion.tr
      className={rowClass}
      variants={listItemVariants}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      layout
    >
      {/* Batch select checkbox */}
      {batchMode && (
        <td>
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => onToggleSelect(field.id || field.field_name)}
            aria-label={`Select ${field.field_name}`}
          />
        </td>
      )}

      {/* Field name */}
      <td className={styles.fieldName}>
        <strong>{field.field_name}</strong>
        {field.is_edited && (
          <span className={styles.editedTag}>(edited)</span>
        )}
      </td>

      {/* Value cell */}
      <motion.td
        className={styles.valueCell}
        variants={editRowVariants}
        animate={editing ? 'editing' : 'normal'}
      >
        {editing ? (
          <input
            className={styles.editInput}
            value={draftValue}
            onChange={(e) => setDraftValue(e.target.value)}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSave();
              if (e.key === 'Escape') handleCancel();
            }}
            aria-label={`Edit value for ${field.field_name}`}
          />
        ) : (
          <span className={field.value ? '' : styles.valueEmpty}>
            {field.value || '—'}
          </span>
        )}
      </motion.td>

      {/* Confidence */}
      <td className={styles.confidenceCell}>
        <ConfidenceBadge confidence={field.confidence || 0} />
      </td>

      {/* Type */}
      <td>
        <code style={{ fontSize: '11px', color: '#6b7280' }}>
          {field.field_type || 'text'}
        </code>
      </td>

      {/* Source */}
      <td>
        <SourceTag source={field.source} />
      </td>

      {/* Actions */}
      <td className={styles.actionsCell}>
        {editing ? (
          <>
            <button
              className={styles.saveBtn}
              onClick={handleSave}
              disabled={saving}
              aria-label={`Save ${field.field_name}`}
            >
              {saving ? '…' : '✓ Save'}
            </button>
            <button
              className={styles.cancelBtn}
              onClick={handleCancel}
              aria-label="Cancel edit"
            >
              ✕
            </button>
          </>
        ) : (
          <>
            <button
              className={styles.editBtn}
              onClick={handleEdit}
              aria-label={`Edit ${field.field_name}`}
            >
              ✏️ Edit
            </button>
            {onSuggest && (
              <button
                className={styles.editBtn}
                onClick={() => onSuggest(field)}
                aria-label={`Get suggestions for ${field.field_name}`}
                title="AI Suggestions"
                style={{ marginLeft: 4 }}
              >
                💡
              </button>
            )}
          </>
        )}
      </td>
    </motion.tr>
  );
}

function FieldsEditor({ fields = [], onFieldUpdate, onFieldHover, onSuggest, activeFieldId, loading }) {
  const [batchMode, setBatchMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [batchValue, setBatchValue] = useState('');

  const { undo, redo, canUndo, canRedo } = useStore();

  const toggleSelect = useCallback((id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleBatchApply = useCallback(async () => {
    if (!batchValue || selectedIds.size === 0 || !onFieldUpdate) return;
    for (const id of selectedIds) {
      await onFieldUpdate(id, batchValue);
    }
    setSelectedIds(new Set());
    setBatchValue('');
    setBatchMode(false);
  }, [batchValue, selectedIds, onFieldUpdate]);

  if (loading) {
    return (
      <div className={`${styles.editor} ${styles.loadingState}`} aria-live="polite">
        <p>Loading extracted fields…</p>
      </div>
    );
  }

  if (!fields.length) {
    return (
      <div className={`${styles.editor} ${styles.empty}`}>
        <p>No fields extracted yet. Run OCR or AI extraction first.</p>
      </div>
    );
  }

  const highConf = fields.filter((f) => (f.confidence || 0) >= 0.85).length;
  const medConf = fields.filter(
    (f) => (f.confidence || 0) >= 0.65 && (f.confidence || 0) < 0.85
  ).length;
  const lowConf = fields.length - highConf - medConf;

  const undoEnabled = canUndo();
  const redoEnabled = canRedo();

  return (
    <div className={styles.editor}>
      {/* ── Toolbar: undo/redo + batch ── */}
      <div className={styles.toolbar} role="toolbar" aria-label="Fields editor controls">
        <button
          className={styles.undoBtn}
          onClick={undo}
          disabled={!undoEnabled}
          aria-label="Undo last change"
          title="Undo (Ctrl+Z)"
        >
          ↩ Undo
        </button>
        <button
          className={styles.redoBtn}
          onClick={redo}
          disabled={!redoEnabled}
          aria-label="Redo last change"
          title="Redo (Ctrl+Y)"
        >
          ↪ Redo
        </button>
        <span className={styles.spacer} />
        <button
          className={`${styles.batchBtn} ${batchMode ? styles.active : ''}`}
          onClick={() => {
            setBatchMode((v) => !v);
            setSelectedIds(new Set());
          }}
          aria-pressed={batchMode}
          aria-label="Toggle batch edit mode"
        >
          ☑ Batch Edit
        </button>
      </div>

      {/* ── Batch action bar ── */}
      <AnimatePresence>
        {batchMode && selectedIds.size > 0 && (
          <motion.div
            className={styles.batchBar}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <span>{selectedIds.size} selected</span>
            <input
              type="text"
              placeholder="New value…"
              value={batchValue}
              onChange={(e) => setBatchValue(e.target.value)}
              aria-label="Batch value to apply"
              style={{
                flex: 1,
                padding: '4px 8px',
                borderRadius: 4,
                border: '1px solid #c4b5fd',
                fontSize: 13,
              }}
            />
            <button
              className={styles.batchApplyBtn}
              onClick={handleBatchApply}
              disabled={!batchValue}
              aria-label="Apply value to selected fields"
            >
              Apply to all
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Summary ── */}
      <div className={styles.summary} aria-label="Confidence summary">
        <span className={styles.summaryHigh}>✅ {highConf} high</span>
        <span className={styles.summaryMed}>⚠️ {medConf} medium</span>
        <span className={styles.summaryLow}>❌ {lowConf} low</span>
      </div>

      {/* ── Table ── */}
      <div className={styles.tableWrapper}>
        <table className={styles.table} role="grid" aria-label="Extracted fields">
          <thead>
            <tr>
              {batchMode && <th style={{ width: 32 }} aria-label="Select" />}
              <th scope="col">Field</th>
              <th scope="col">Value</th>
              <th scope="col">Confidence</th>
              <th scope="col">Type</th>
              <th scope="col">Source</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <motion.tbody variants={listContainerVariants} initial="hidden" animate="visible">
            {fields.map((field) => (
              <FieldRow
                key={field.id || field.field_name}
                field={field}
                onSave={onFieldUpdate}
                onHover={onFieldHover}
                onSuggest={onSuggest}
                isActive={activeFieldId === (field.id || field.field_name)}
                batchMode={batchMode}
                isSelected={selectedIds.has(field.id || field.field_name)}
                onToggleSelect={toggleSelect}
              />
            ))}
          </motion.tbody>
        </table>
      </div>
    </div>
  );
}

export default FieldsEditor;

