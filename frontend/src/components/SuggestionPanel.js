/**
 * SuggestionPanel.js — AI-powered field value suggestion panel.
 *
 * Slides in from the right side and shows alternative values for a field
 * with confidence scores. Users can accept or dismiss suggestions.
 *
 * Props:
 *   field        {object|null}  The field being suggested (has .field_name, .value)
 *   suggestions  {Array}        [{ value, confidence, source }]
 *   onAccept     {func}         Called with (fieldId, value) when user accepts
 *   onDismiss    {func}         Called when panel is closed
 */

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useConfidenceColors } from '../hooks/useConfidenceColors';
import { slideInRight } from '../hooks/useAnimations';

function SuggestionPanel({ field, suggestions = [], onAccept, onDismiss }) {
  const { getConfidenceColor, getConfidenceLabel, getConfidenceHex } = useConfidenceColors();

  const isOpen = !!field;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.aside
          className="suggestion-panel"
          variants={slideInRight}
          initial="hidden"
          animate="visible"
          exit="exit"
          aria-label="AI Suggestions panel"
          role="complementary"
        >
          {/* Header */}
          <div className="suggestion-panel__header">
            <div className="suggestion-panel__title">
              <span className="suggestion-panel__icon">🤖</span>
              <span>AI Suggestions</span>
            </div>
            <button
              className="suggestion-panel__close"
              onClick={onDismiss}
              aria-label="Close suggestions panel"
            >
              ✕
            </button>
          </div>

          {/* Field name */}
          <div className="suggestion-panel__field-name">
            <span className="suggestion-panel__field-label">Field:</span>
            <strong>{field?.field_name}</strong>
          </div>

          {/* Current value */}
          <div className="suggestion-panel__current">
            <span className="suggestion-panel__field-label">Current value:</span>
            <span className="suggestion-panel__current-value">{field?.value || '—'}</span>
          </div>

          {/* Suggestions list */}
          <div className="suggestion-panel__list-header">Suggested alternatives:</div>
          {suggestions.length === 0 ? (
            <p className="suggestion-panel__empty">No suggestions available.</p>
          ) : (
            <ul className="suggestion-panel__list">
              {suggestions.map((sug, i) => {
                const colorKey = getConfidenceColor(sug.confidence || 0);
                const hexColor = getConfidenceHex(sug.confidence || 0);
                const label = getConfidenceLabel(sug.confidence || 0);
                return (
                  <li
                    key={i}
                    className="suggestion-panel__item"
                  >
                    <div className="suggestion-panel__item-top">
                      <span className="suggestion-panel__item-value">{sug.value}</span>
                      <span
                        className={`suggestion-panel__badge suggestion-panel__badge--${colorKey}`}
                        style={{ background: `${hexColor}22`, color: hexColor }}
                        title={`Confidence: ${Math.round((sug.confidence || 0) * 100)}%`}
                      >
                        {label} · {Math.round((sug.confidence || 0) * 100)}%
                      </span>
                    </div>
                    {sug.source && (
                      <div className="suggestion-panel__item-source">
                        Source: {sug.source}
                      </div>
                    )}
                    <button
                      className="suggestion-panel__accept-btn"
                      onClick={() => onAccept && onAccept(field.id, sug.value)}
                      aria-label={`Accept suggestion: ${sug.value}`}
                    >
                      ✓ Use this value
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

export default SuggestionPanel;
