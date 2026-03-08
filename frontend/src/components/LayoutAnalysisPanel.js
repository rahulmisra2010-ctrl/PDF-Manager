/**
 * LayoutAnalysisPanel.js — Visualise form layout analysis results.
 *
 * Shows:
 * - Page zone breakdown (header / body / footer)
 * - Detected columns with word counts
 * - Detected rows
 * - Label-value pairs with confidence scores
 *
 * Props:
 *   layoutData  {object} Output from /analyze/layout API
 *   loading     {bool}
 */

import React, { useState } from 'react';

function ConfidenceBadge({ value }) {
  const pct = Math.round(value * 100);
  let color = '#dc2626';
  if (value >= 0.85) color = '#059669';
  else if (value >= 0.65) color = '#d97706';
  return (
    <span style={{
      display: 'inline-block',
      padding: '1px 7px',
      borderRadius: 999,
      background: color + '22',
      color,
      fontWeight: 700,
      fontSize: '0.78rem',
    }}>
      {pct}%
    </span>
  );
}

function SectionHeader({ children }) {
  return (
    <h5 style={{
      margin: '16px 0 8px',
      fontSize: '0.8rem',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.06em',
      color: '#64748b',
      borderBottom: '1px solid #e2e8f0',
      paddingBottom: 4,
    }}>
      {children}
    </h5>
  );
}

function LayoutAnalysisPanel({ layoutData, loading }) {
  const [expandPairs, setExpandPairs] = useState(true);

  if (loading) {
    return (
      <div className="layout-panel layout-panel--loading">
        <span>⏳ Analysing layout…</span>
      </div>
    );
  }

  if (!layoutData) {
    return (
      <div className="layout-panel layout-panel--empty">
        <p>📐 Click <strong>Analyse Layout</strong> to detect form structure.</p>
      </div>
    );
  }

  const layout = layoutData.layout || layoutData;
  const zones = layout.zones || {};
  const columns = layout.columns || [];
  const rows = layout.rows || [];
  const pairs = layout.label_value_pairs || [];
  const pageWidth = layoutData.page_width || 0;
  const pageHeight = layoutData.page_height || 0;

  return (
    <div className="layout-panel">
      {/* Page info */}
      <div className="layout-panel__page-info">
        <span>Page {layoutData.page}</span>
        {pageWidth > 0 && (
          <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}>
            {' '}· {Math.round(pageWidth)}×{Math.round(pageHeight)} pts
          </span>
        )}
      </div>

      {/* Zones */}
      <SectionHeader>🗺 Page Zones</SectionHeader>
      <div className="layout-panel__zones">
        {Object.entries(zones).map(([zone, bounds]) => {
          const heightPct = pageHeight > 0
            ? Math.round(((bounds.y_end - bounds.y_start) / pageHeight) * 100)
            : null;
          return (
            <div key={zone} className={`layout-panel__zone layout-panel__zone--${zone}`}>
              <span className="layout-panel__zone-name">{zone}</span>
              <span className="layout-panel__zone-range">
                y: {Math.round(bounds.y_start)}–{Math.round(bounds.y_end)}
              </span>
              {heightPct !== null && (
                <span className="layout-panel__zone-pct">{heightPct}%</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Columns */}
      <SectionHeader>📊 Columns ({columns.length})</SectionHeader>
      {columns.length === 0 ? (
        <p className="layout-panel__empty-hint">No columns detected.</p>
      ) : (
        <div className="layout-panel__grid-list">
          {columns.map((col) => (
            <div key={col.index} className="layout-panel__grid-item">
              <span className="layout-panel__grid-index">Col {col.index}</span>
              <span className="layout-panel__grid-range">
                x: {Math.round(col.x_start)}–{Math.round(col.x_end)}
              </span>
              <span className="layout-panel__grid-words">{col.word_count} words</span>
            </div>
          ))}
        </div>
      )}

      {/* Rows */}
      <SectionHeader>📏 Rows ({rows.length})</SectionHeader>
      {rows.length === 0 ? (
        <p className="layout-panel__empty-hint">No rows detected.</p>
      ) : (
        <div className="layout-panel__grid-list" style={{ maxHeight: 140, overflowY: 'auto' }}>
          {rows.map((row) => (
            <div key={row.index} className="layout-panel__grid-item">
              <span className="layout-panel__grid-index">Row {row.index}</span>
              <span className="layout-panel__grid-range">
                y: {Math.round(row.y_start)}–{Math.round(row.y_end)}
              </span>
              <span className="layout-panel__grid-words">{row.word_count} words</span>
            </div>
          ))}
        </div>
      )}

      {/* Label-Value Pairs */}
      <SectionHeader>
        🔗 Label–Value Pairs ({pairs.length})
        <button
          onClick={() => setExpandPairs((v) => !v)}
          style={{
            marginLeft: 8,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '0.8rem',
            color: '#0ea5e9',
          }}
        >
          {expandPairs ? 'hide' : 'show'}
        </button>
      </SectionHeader>

      {expandPairs && (
        pairs.length === 0 ? (
          <p className="layout-panel__empty-hint">No label-value pairs detected.</p>
        ) : (
          <div className="layout-panel__pairs">
            {pairs.map((pair, i) => (
              <div key={i} className="layout-panel__pair">
                <span className="layout-panel__pair-label">{pair.label}</span>
                <span className="layout-panel__pair-arrow">→</span>
                <span className="layout-panel__pair-value">{pair.value}</span>
                <ConfidenceBadge value={pair.confidence} />
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}

export default LayoutAnalysisPanel;
