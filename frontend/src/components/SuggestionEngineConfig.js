/**
 * SuggestionEngineConfig.js — Configure the hover suggestion engine.
 *
 * Props:
 *   config      {object}   Current configuration values
 *   onChange    {func}     Called with updated config object
 */

import React from 'react';

const DEFAULT_CONFIG = {
  similarityThreshold: 70,
  confidenceThreshold: 85,
  maxSuggestions: 3,
  weightSamplePDF: 40,
  weightLogicRule: 40,
  weightHistory: 20,
};

function SuggestionEngineConfig({ config = DEFAULT_CONFIG, onChange }) {
  const cfg = { ...DEFAULT_CONFIG, ...config };

  const update = (key, value) => {
    const next = { ...cfg, [key]: value };
    if (onChange) onChange(next);
  };

  const weights = [
    {
      key: 'weightSamplePDF',
      label: 'Sample PDF match',
      fillClass: 'config-weight-row__fill--sample',
      value: cfg.weightSamplePDF,
    },
    {
      key: 'weightLogicRule',
      label: 'Logic rule match',
      fillClass: 'config-weight-row__fill--rule',
      value: cfg.weightLogicRule,
    },
    {
      key: 'weightHistory',
      label: 'Historical corrections',
      fillClass: 'config-weight-row__fill--history',
      value: cfg.weightHistory,
    },
  ];

  return (
    <div className="suggestion-config">
      <h3 className="suggestion-config__title">⚙️ Suggestion Engine</h3>

      <div className="suggestion-config__grid">
        {/* Similarity threshold */}
        <div className="config-field">
          <label className="config-field__label">
            Similarity Threshold
          </label>
          <input
            type="range"
            className="config-field__slider"
            min={0}
            max={100}
            value={cfg.similarityThreshold}
            onChange={(e) => update('similarityThreshold', Number(e.target.value))}
          />
          <span className="config-field__value">{cfg.similarityThreshold}%</span>
        </div>

        {/* Confidence threshold */}
        <div className="config-field">
          <label className="config-field__label">
            Confidence Threshold
          </label>
          <input
            type="range"
            className="config-field__slider"
            min={0}
            max={100}
            value={cfg.confidenceThreshold}
            onChange={(e) => update('confidenceThreshold', Number(e.target.value))}
          />
          <span className="config-field__value">{cfg.confidenceThreshold}%</span>
        </div>

        {/* Max suggestions */}
        <div className="config-field">
          <label className="config-field__label">
            Max Suggestions
          </label>
          <select
            className="config-field__input"
            value={cfg.maxSuggestions}
            onChange={(e) => update('maxSuggestions', Number(e.target.value))}
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Weight distribution */}
      <div>
        <p className="config-field__label" style={{ marginBottom: '0.5rem' }}>
          Weight Distribution
        </p>
        {weights.map((w) => (
          <div key={w.key} className="config-weight-row" style={{ marginBottom: '0.4rem' }}>
            <span style={{ minWidth: '145px', fontSize: '0.73rem' }}>{w.label}</span>
            <div className="config-weight-row__bar">
              <div
                className={`config-weight-row__fill ${w.fillClass}`}
                style={{ width: `${w.value}%` }}
              />
            </div>
            <span className="config-weight-row__pct">{w.value}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default SuggestionEngineConfig;
