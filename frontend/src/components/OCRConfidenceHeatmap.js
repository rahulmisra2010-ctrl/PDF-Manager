/**
 * OCRConfidenceHeatmap.js — Visual heatmap of OCR confidence per word.
 *
 * Renders a grid of coloured cells (Green/Yellow/Red) and an optional
 * base64 PNG image from the backend.
 *
 * Props:
 *   heatmapData  {object}  Heatmap JSON from GET /api/v1/documents/:id/heatmap
 *   imageData    {string}  Optional base64 PNG string for pixel-accurate heatmap
 *   pageNumber   {number}
 */

import React, { useState } from 'react';

const CELL_COLORS = {
  green:  'rgba(16, 185, 129, 0.7)',
  yellow: 'rgba(245, 158, 11, 0.7)',
  red:    'rgba(239, 68, 68, 0.7)',
  none:   'rgba(200,200,200,0.1)',
};

function WordMarker({ marker, scale }) {
  const { text, confidence, color, x, y, width, height } = marker;
  const pct = Math.round(confidence * 100);
  return (
    <div
      className="heatmap__word-marker"
      style={{
        position: 'absolute',
        left: x * scale,
        top: y * scale,
        width: width * scale,
        height: height * scale,
        background: CELL_COLORS[color] || CELL_COLORS.none,
        border: '1px solid rgba(0,0,0,0.15)',
        boxSizing: 'border-box',
        overflow: 'hidden',
        cursor: 'default',
        fontSize: '9px',
        lineHeight: `${height * scale}px`,
        paddingLeft: 2,
        color: '#000',
      }}
      title={`"${text}" — ${pct}% confidence`}
    >
      {width * scale > 30 ? text : ''}
    </div>
  );
}

function OCRConfidenceHeatmap({ heatmapData, imageData, pageNumber }) {
  const [mode, setMode] = useState('words'); // 'words' | 'image'

  if (!heatmapData) {
    return (
      <div className="heatmap heatmap--empty">
        <p>No heatmap data available. Run OCR extraction first.</p>
      </div>
    );
  }

  const {
    word_markers = [],
    avg_confidence = 0,
    page_width = 595,
    page_height = 842,
  } = heatmapData;

  // Scale to fit 500px wide
  const displayWidth = 480;
  const scale = displayWidth / page_width;
  const displayHeight = page_height * scale;

  const avgPct = Math.round(avg_confidence * 100);
  let avgColor = 'red';
  if (avg_confidence >= 0.85) avgColor = 'green';
  else if (avg_confidence >= 0.65) avgColor = 'yellow';

  return (
    <div className="heatmap">
      {/* Header */}
      <div className="heatmap__header">
        <h4>OCR Confidence Heatmap — Page {pageNumber || heatmapData.page_number}</h4>
        <div className="heatmap__avg-badge" style={{ color: CELL_COLORS[avgColor] }}>
          Avg Confidence: {avgPct}%
        </div>
      </div>

      {/* Legend */}
      <div className="heatmap__legend">
        <span style={{ color: CELL_COLORS.green }}>■ High (≥85%)</span>
        <span style={{ color: CELL_COLORS.yellow }}>■ Medium (≥65%)</span>
        <span>■ Low ({'<'}65%)</span>
      </div>

      {/* Mode switcher */}
      {imageData && (
        <div className="heatmap__mode-switch">
          <button
            className={`heatmap__mode-btn ${mode === 'words' ? 'active' : ''}`}
            onClick={() => setMode('words')}
          >
            Word overlay
          </button>
          <button
            className={`heatmap__mode-btn ${mode === 'image' ? 'active' : ''}`}
            onClick={() => setMode('image')}
          >
            Pixel heatmap
          </button>
        </div>
      )}

      {/* Canvas */}
      <div className="heatmap__canvas-wrapper">
        {mode === 'image' && imageData ? (
          <img
            src={imageData}
            alt={`Confidence heatmap page ${pageNumber}`}
            style={{ maxWidth: '100%', border: '1px solid #ddd' }}
          />
        ) : (
          <div
            className="heatmap__canvas"
            style={{
              position: 'relative',
              width: displayWidth,
              height: displayHeight,
              background: '#f9fafb',
              border: '1px solid #ddd',
              overflow: 'hidden',
            }}
          >
            {word_markers.map((marker, idx) => (
              <WordMarker key={idx} marker={marker} scale={scale} />
            ))}
          </div>
        )}
      </div>

      {/* Stats */}
      <div className="heatmap__stats">
        <span>Total words: {word_markers.length}</span>
        <span>
          High:{' '}
          {word_markers.filter((m) => m.color === 'green').length}
        </span>
        <span>
          Medium:{' '}
          {word_markers.filter((m) => m.color === 'yellow').length}
        </span>
        <span>
          Low:{' '}
          {word_markers.filter((m) => m.color === 'red').length}
        </span>
      </div>
    </div>
  );
}

export default OCRConfidenceHeatmap;
