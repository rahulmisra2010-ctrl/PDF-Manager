/**
 * SuggestionPanel.js — AI-powered field value suggestions.
 *
 * Features:
 * - "Did you mean…?" style list of alternative values
 * - Confidence score per suggestion (High/Medium/Low badge)
 * - One-click apply with Framer Motion pulse + success toast
 * - Suggestion history / undo last apply
 * - Slides in from the right
 *
 * Props:
 *   fieldId       {string|number}  Active field's ID
 *   fieldName     {string}         Field display name
 *   currentValue  {string}         Current field value
 *   suggestions   {Array}          [{ value, score, source }]
 *   onApply       {func}           Called with (fieldId, newValue)
 *   onClose       {func}           Close the panel
 *   loading       {boolean}
 */

import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import toast from 'react-hot-toast';
import { slideFromRightVariants, pulseVariants } from '../hooks/useAnimations';
import useConfidenceColors from '../hooks/useConfidenceColors';
import styles from './styles/SuggestionPanel.module.css';

const MAX_HISTORY = 10;

const DEFAULT_SUGGESTION_SCORE = 1.0;

function SuggestionItem({ suggestion, onApply }) {
  const [applying, setApplying] = useState(false);
  const { getColors, getKey } = useConfidenceColors();
  const score = suggestion.score ?? DEFAULT_SUGGESTION_SCORE;
  const key = getKey(score);
  const colors = getColors(score);
  const pct = Math.round(score * 100);

  const handleApply = useCallback(async () => {
    setApplying(true);
    await onApply(suggestion.value);
    setApplying(false);
  }, [suggestion.value, onApply]);

  const scoreClass =
    key === 'high' ? styles.scoreHigh : key === 'medium' ? styles.scoreMedium : styles.scoreLow;

  return (
    <motion.li
      className={`${styles.suggestionItem} ${applying ? styles.applying : ''}`}
      variants={pulseVariants}
      animate={applying ? 'pulse' : 'idle'}
      layout
    >
      <span
        className={styles.suggestionValue}
        aria-label={`Suggestion: ${suggestion.value}`}
      >
        {suggestion.value || <em style={{ color: '#9ca3af' }}>— empty —</em>}
      </span>
      <div className={styles.suggestionMeta}>
        <span
          className={`${styles.suggestionScore} ${scoreClass}`}
          style={{ background: colors.badge, color: colors.text }}
        >
          {pct}%
        </span>
        {suggestion.source && (
          <span className={styles.suggestionSource}>{suggestion.source}</span>
        )}
      </div>
      <motion.button
        className={styles.applyBtn}
        onClick={handleApply}
        whileTap={{ scale: 0.93 }}
        aria-label={`Apply suggestion: ${suggestion.value}`}
      >
        ✓ Apply
      </motion.button>
    </motion.li>
  );
}

function SuggestionPanel({
  fieldId,
  fieldName,
  currentValue,
  suggestions = [],
  onApply,
  onClose,
  loading = false,
}) {
  const [history, setHistory] = useState([]); // [{fieldName, from, to}]
  const [lastApplied, setLastApplied] = useState(null);

  const handleApply = useCallback(
    async (newValue) => {
      if (!onApply) return;
      const entry = { fieldId, fieldName, from: currentValue, to: newValue };
      setLastApplied(entry);
      setHistory((h) => [entry, ...h].slice(0, MAX_HISTORY));
      await onApply(fieldId, newValue);
      toast.success(`Applied: "${newValue}"`, { icon: '✅', duration: 2500 });
    },
    [fieldId, fieldName, currentValue, onApply]
  );

  const handleUndo = useCallback(() => {
    if (!lastApplied || !onApply) return;
    onApply(lastApplied.fieldId, lastApplied.from);
    toast.success(`Reverted to: "${lastApplied.from}"`, { icon: '↩', duration: 2000 });
    setLastApplied(null);
  }, [lastApplied, onApply]);

  return (
    <motion.aside
      className={styles.panel}
      variants={slideFromRightVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      role="complementary"
      aria-label="AI suggestions panel"
    >
      {/* Header */}
      <div className={styles.header}>
        <h3 className={styles.title}>
          <span aria-hidden>🤖</span> AI Suggestions
        </h3>
        {onClose && (
          <button
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close suggestions panel"
          >
            ✕
          </button>
        )}
      </div>

      {/* Field context */}
      {fieldName && (
        <div className={styles.fieldContext}>
          <div className={styles.fieldContextLabel}>Editing field</div>
          <div className={styles.fieldContextName}>{fieldName}</div>
          {currentValue && (
            <div className={styles.fieldContextValue}>
              Current: <em>"{currentValue}"</em>
            </div>
          )}
        </div>
      )}

      {/* Undo last apply */}
      <AnimatePresence>
        {lastApplied && (
          <motion.div
            className={styles.undoBar}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >
            <span>Applied: "{lastApplied.to}"</span>
            <button className={styles.undoBarBtn} onClick={handleUndo} aria-label="Undo last apply">
              ↩ Undo
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Suggestions list */}
      {loading ? (
        <div className={styles.loading} aria-live="polite">
          <span>⏳</span> Fetching suggestions…
        </div>
      ) : suggestions.length === 0 ? (
        <div className={styles.empty} aria-live="polite">
          <span aria-hidden>💡</span>
          <p>No suggestions available.</p>
          <small>Run AI extraction to get suggestions.</small>
        </div>
      ) : (
        <>
          <p className={styles.didYouMean} aria-label="Did you mean one of these?">
            Did you mean…?
          </p>
          <ul className={styles.suggestionList} aria-label="Suggestion list">
            <AnimatePresence>
              {suggestions.map((s, i) => (
                <SuggestionItem
                  key={`${s.value}-${i}`}
                  suggestion={s}
                  onApply={handleApply}
                />
              ))}
            </AnimatePresence>
          </ul>
        </>
      )}

      {/* History */}
      {history.length > 0 && (
        <div className={styles.historySection}>
          <h4 className={styles.historyTitle}>Recent changes</h4>
          {history.map((h, i) => (
            <div key={i} className={styles.historyItem}>
              <span className={styles.historyField}>{h.fieldName}</span>
              <span className={styles.historyArrow}>→</span>
              <span className={styles.historyValue}>{h.to || '—'}</span>
            </div>
          ))}
        </div>
      )}
    </motion.aside>
  );
}

export default SuggestionPanel;
