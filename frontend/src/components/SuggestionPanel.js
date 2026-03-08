/**
 * SuggestionPanel.js — AI-powered field value suggestions.
 *
 * Features:
 * - "Did you mean?" style suggestion list
 * - Confidence score badges per suggestion
 * - One-click apply with pulse animation
 * - Suggestion history and undo last apply
 * - Slides in from right with Framer Motion
 *
 * Props:
 *   fieldId       {string|number}  Target field id
 *   fieldName     {string}         Display name for the field
 *   suggestions   {Array}          [{ value, confidence, source }]
 *   onApply       {func}           Called with (fieldId, value) when applied
 *   onUndoLast    {func}           Called to undo the last applied suggestion
 *   onClose       {func}           Called to close the panel
 *   canUndo       {boolean}        Whether undo is available
 */

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { slideFromRightVariants, pulseVariants } from '../hooks/useAnimations';
import { getConfidenceLevel } from '../hooks/useConfidenceColors';
import styles from './styles/SuggestionPanel.module.css';

function SuggestionItem({ suggestion, onApply }) {
  const level = getConfidenceLevel(suggestion.confidence || 0);
  const [pulse, setPulse] = useState(false);

  const handleApply = () => {
    setPulse(true);
    onApply(suggestion.value);
    setTimeout(() => setPulse(false), 400);
  };

  return (
    <motion.li
      className={styles.item}
      layout
    >
      <div className={styles.itemContent}>
        <span className={styles.itemValue}>{suggestion.value}</span>
        {suggestion.source && (
          <span className={styles.itemSource}>{suggestion.source}</span>
        )}
      </div>
      <div className={styles.itemRight}>
        <span
          className={styles.badge}
          style={{ background: level.background, color: level.color, border: `1px solid ${level.border}` }}
        >
          {level.badge} {Math.round((suggestion.confidence || 0) * 100)}%
        </span>
        <motion.button
          className={styles.applyBtn}
          onClick={handleApply}
          variants={pulseVariants}
          animate={pulse ? 'pulse' : 'idle'}
          aria-label={`Apply suggestion: ${suggestion.value}`}
        >
          Apply
        </motion.button>
      </div>
    </motion.li>
  );
}

function SuggestionPanel({ fieldId, fieldName, suggestions = [], onApply, onUndoLast, onClose, canUndo }) {
  const handleApply = (value) => {
    onApply && onApply(fieldId, value);
  };

  return (
    <AnimatePresence>
      <motion.aside
        className={styles.panel}
        variants={slideFromRightVariants}
        initial="hidden"
        animate="visible"
        exit="exit"
        role="complementary"
        aria-label={`Suggestions for ${fieldName}`}
      >
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <span className={styles.headerIcon}>💡</span>
            <div>
              <div className={styles.headerTitle}>Did you mean?</div>
              <div className={styles.headerSub}>{fieldName}</div>
            </div>
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close suggestions">
            ✕
          </button>
        </div>

        {/* Suggestion list */}
        {suggestions.length === 0 ? (
          <p className={styles.empty}>No suggestions available.</p>
        ) : (
          <motion.ul className={styles.list} layout>
            {suggestions.map((s, idx) => (
              <SuggestionItem
                key={`${s.value}-${idx}`}
                suggestion={s}
                onApply={handleApply}
              />
            ))}
          </motion.ul>
        )}

        {/* Undo last apply */}
        {canUndo && (
          <div className={styles.footer}>
            <button className={styles.undoBtn} onClick={onUndoLast}>
              ↩ Undo last apply
            </button>
          </div>
        )}
      </motion.aside>
    </AnimatePresence>
  );
}

export default SuggestionPanel;
