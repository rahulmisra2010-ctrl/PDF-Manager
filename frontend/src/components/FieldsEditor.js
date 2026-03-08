/**
 * FieldsEditor.js — Advanced editable fields table for extracted PDF data.
 *
 * Features:
 * - Inline editing with undo/redo (via Zustand store)
 * - Batch edit mode for selecting multiple fields
 * - Confidence badges (color-coded: Green/Yellow/Red)
 * - Source tags (rule / NER / RAG / PyMuPDF)
 * - Framer Motion row animations (fade + stagger)
 * - Suggestion panel trigger per field
 * - ARIA labels and keyboard navigation
 *
 * Props:
 *   fields           {Array}    Extracted field objects from the API
 *   onFieldUpdate    {func}     Called with (fieldId, newValue) to save a field
 *   onFieldHover     {func}     Called with (bbox | null) on hover to highlight PDF
 *   loading          {boolean}  Show loading state
 *   canUndo          {boolean}  Whether undo is available
 *   canRedo          {boolean}  Whether redo is available
 *   onUndo           {func}     Trigger undo
 *   onRedo           {func}     Trigger redo
 */

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { getConfidenceLevel } from '../hooks/useConfidenceColors';
import { listContainerVariants, listItemVariants, editRowVariants } from '../hooks/useAnimations';
import { useStore } from '../services/store';
import styles from './styles/FieldsEditor.module.css';

const SOURCE_CLASS = {
  rule:    styles.sourceTagRule,
  ner:     styles.sourceTagNer,
  rag:     styles.sourceTagRag,
  pymupdf: styles.sourceTagPymupdf,
};

function ConfidenceBadge({ confidence }) {
  const level = getConfidenceLevel(confidence);
  const pct = Math.round(confidence * 100);
  return (
    <span
      className={styles.badge}
      style={{ background: level.background, color: level.color, border: `1px solid ${level.border}` }}
      title={`Confidence: ${pct}%`}
    >
      {level.badge} {pct}%
    </span>
  );
}

function FieldRow({ field, onSave, onHover, batchMode, selected, onToggleSelect }) {
  const [editing, setEditing] = useState(false);
  const [draftValue, setDraftValue] = useState(field.value || '');
  const [saving, setSaving] = useState(false);

  const openSuggestionPanel = useStore((s) => s.openSuggestionPanel);
  const activeFieldId = useStore((s) => s.activeFieldId);
  const setActiveFieldId = useStore((s) => s.setActiveFieldId);

  const isActive = activeFieldId === field.id;

  const handleEdit = () => {
    setDraftValue(field.value || '');
    setEditing(true);
    setActiveFieldId(field.id);
  };

  const handleCancel = () => {
    setEditing(false);
    setActiveFieldId(null);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(field.id, draftValue);
      setEditing(false);
      setActiveFieldId(null);
    } finally {
      setSaving(false);
    }
  };

  const handleMouseEnter = () => onHover && onHover(field.bbox || null);
  const handleMouseLeave = () => onHover && onHover(null);

  const rowClass = [
    styles.row,
    isActive ? styles.rowActive : '',
    selected ? styles.rowSelected : '',
    editing ? styles.rowEditing : '',
  ].filter(Boolean).join(' ');

  return (
    <motion.tr
      className={rowClass}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      variants={listItemVariants}
      layout
      animate={editing ? 'editing' : 'idle'}
    >
      {batchMode && (
        <td style={{ padding: '8px 10px' }}>
          <input
            type="checkbox"
            className={styles.checkbox}
            checked={selected}
            onChange={() => onToggleSelect(field.id)}
            aria-label={`Select ${field.field_name}`}
          />
        </td>
      )}
      <td className={styles.cellName}>
        <strong>{field.field_name}</strong>
        {field.is_edited && <span className={styles.editedTag}>(edited)</span>}
      </td>
      <td className={styles.cellValue}>
        {editing ? (
          <input
            className={styles.input}
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
          <span className={field.value ? '' : styles.emptyValue}>
            {field.value || '—'}
          </span>
        )}
      </td>
      <td className={styles.cellConf}>
        <ConfidenceBadge confidence={field.confidence || 0} />
      </td>
      <td className={styles.cellType}>
        <code>{field.field_type || 'text'}</code>
      </td>
      <td className={styles.cellSource}>
        <span className={`${styles.sourceTag} ${SOURCE_CLASS[field.source] || SOURCE_CLASS.rule}`}>
          {field.source || 'rule'}
        </span>
      </td>
      <td className={styles.cellActions}>
        {editing ? (
          <>
            <button
              className={styles.btnSave}
              onClick={handleSave}
              disabled={saving}
              aria-label={`Save ${field.field_name}`}
            >
              {saving ? '…' : '✓ Save'}
            </button>
            <button
              className={styles.btnCancel}
              onClick={handleCancel}
              aria-label="Cancel edit"
            >
              ✕
            </button>
          </>
        ) : (
          <>
            <button
              className={styles.btnEdit}
              onClick={handleEdit}
              aria-label={`Edit ${field.field_name}`}
            >
              ✏️ Edit
            </button>
            <button
              className={styles.btnSuggest}
              onClick={() => openSuggestionPanel(field.id)}
              aria-label={`Suggestions for ${field.field_name}`}
              title="AI Suggestions"
            >
              💡
            </button>
          </>
        )}
      </td>
    </motion.tr>
  );
}

function FieldsEditor({ fields = [], onFieldUpdate, onFieldHover, loading, canUndo, canRedo, onUndo, onRedo }) {
  const [batchMode, setBatchMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());

  const handleToggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleBatchClear = () => {
    setSelectedIds(new Set());
    setBatchMode(false);
  };

  if (loading) {
    return (
      <div className={`${styles.editor} ${styles.loading}`}>
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

  const high = fields.filter((f) => (f.confidence || 0) >= 0.85).length;
  const med  = fields.filter((f) => (f.confidence || 0) >= 0.65 && (f.confidence || 0) < 0.85).length;
  const low  = fields.length - high - med;

  return (
    <div className={styles.editor}>
      {/* Toolbar */}
      <div className={styles.toolbar}>
        <button
          className={styles.toolbarBtn}
          onClick={onUndo}
          disabled={!canUndo}
          aria-label="Undo"
          title="Undo (Ctrl+Z)"
        >
          ↩ Undo
        </button>
        <button
          className={styles.toolbarBtn}
          onClick={onRedo}
          disabled={!canRedo}
          aria-label="Redo"
          title="Redo (Ctrl+Y)"
        >
          ↪ Redo
        </button>
        <span className={styles.toolbarSep} />
        <button
          className={styles.toolbarBtn}
          onClick={() => { setBatchMode((v) => !v); setSelectedIds(new Set()); }}
          aria-pressed={batchMode}
        >
          {batchMode ? '✕ Exit Batch' : '☰ Batch Edit'}
        </button>
        {batchMode && selectedIds.size > 0 && (
          <span className={styles.batchBadge}>{selectedIds.size} selected</span>
        )}
      </div>

      {/* Summary bar */}
      <div className={styles.summary}>
        <span className={`${styles.summaryBadge} ${styles.summaryHigh}`}>✅ {high} high</span>
        <span className={`${styles.summaryBadge} ${styles.summaryMed}`}>⚠️ {med} medium</span>
        <span className={`${styles.summaryBadge} ${styles.summaryLow}`}>❌ {low} low</span>
      </div>

      {/* Table */}
      <div className={styles.tableWrapper}>
        <table className={styles.table}>
          <thead>
            <tr>
              {batchMode && <th aria-label="Select" />}
              <th>Field</th>
              <th>Value</th>
              <th>Confidence</th>
              <th>Type</th>
              <th>Source</th>
              <th>Actions</th>
            </tr>
          </thead>
          <AnimatePresence>
            <motion.tbody
              variants={listContainerVariants}
              initial="hidden"
              animate="visible"
            >
              {fields.map((field) => (
                <FieldRow
                  key={field.id || field.field_name}
                  field={field}
                  onSave={onFieldUpdate}
                  onHover={onFieldHover}
                  batchMode={batchMode}
                  selected={selectedIds.has(field.id)}
                  onToggleSelect={handleToggleSelect}
                />
              ))}
            </motion.tbody>
          </AnimatePresence>
        </table>
      </div>
    </div>
  );
}

export default FieldsEditor;
