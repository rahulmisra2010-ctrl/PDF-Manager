/**
 * PositionContextDisplay.js — Show spatial features for a clicked/hovered word.
 *
 * Props:
 *   contextData  {object}  Response from /suggestions/spatial API
 *   loading      {bool}
 *   error        {string}
 *   onClose      {func}    Optional dismiss callback
 */

import React from 'react';

function Row({ label, value }) {
  if (value === null || value === undefined) return null;
  const display = typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value);
  return (
    <tr>
      <td className="pos-ctx__key">{label}</td>
      <td className="pos-ctx__val">{display}</td>
    </tr>
  );
}

function Section({ title, children }) {
  return (
    <div className="pos-ctx__section">
      <div className="pos-ctx__section-title">{title}</div>
      <table className="pos-ctx__table">
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function WordCard({ word }) {
  const pos = word.position || {};
  const sp = word.spatial_features || {};
  const vis = word.visual_features || {};
  const ctx = word.contextual_features || {};

  return (
    <div className="pos-ctx__word-card">
      <div className="pos-ctx__word-text">
        "{word.text}"
        {word._distance !== undefined && (
          <span className="pos-ctx__distance"> · {word._distance.toFixed(1)}px away</span>
        )}
      </div>

      <Section title="📍 Position">
        <Row label="x" value={pos.x !== undefined ? pos.x.toFixed(2) : undefined} />
        <Row label="y" value={pos.y !== undefined ? pos.y.toFixed(2) : undefined} />
        <Row label="w × h" value={pos.width !== undefined ? `${pos.width.toFixed(1)} × ${pos.height.toFixed(1)}` : undefined} />
        <Row label="zone" value={pos.zone} />
        <Row label="page" value={pos.page} />
      </Section>

      <Section title="📐 Spatial">
        <Row label="zone" value={sp.zone} />
        <Row label="column" value={sp.in_column} />
        <Row label="row" value={sp.in_row} />
        <Row label="h-align" value={sp.horizontal_alignment} />
        <Row label="v-align" value={sp.vertical_alignment} />
        <Row label="dist top" value={sp.distance_from_top !== undefined ? sp.distance_from_top.toFixed(1) + 'px' : undefined} />
        <Row label="dist left" value={sp.distance_from_left !== undefined ? sp.distance_from_left.toFixed(1) + 'px' : undefined} />
        <Row label="isolated" value={sp.is_isolated} />
        <Row label="nearest label" value={
          sp.nearby_labels && sp.nearby_labels.length > 0
            ? sp.nearby_labels[0]
            : '—'
        } />
        <Row label="label dist" value={
          sp.distance_to_nearest_label !== null && sp.distance_to_nearest_label !== undefined
            ? sp.distance_to_nearest_label.toFixed(1) + 'px'
            : '—'
        } />
      </Section>

      <Section title="🎨 Visual">
        <Row label="font size" value={vis.font_size !== undefined ? vis.font_size.toFixed(1) + 'pt' : undefined} />
        <Row label="bold" value={vis.is_bold} />
        <Row label="italic" value={vis.is_italic} />
        <Row label="color" value={vis.text_color} />
      </Section>

      <Section title="🧠 Context">
        <Row label="OCR conf" value={ctx.ocr_confidence !== undefined ? (ctx.ocr_confidence * 100).toFixed(0) + '%' : undefined} />
        <Row label="field type" value={ctx.field_type_inferred || '—'} />
        <Row label="field conf" value={ctx.field_type_confidence !== undefined ? (ctx.field_type_confidence * 100).toFixed(0) + '%' : undefined} />
        <Row label="pattern" value={ctx.matches_pattern || '—'} />
      </Section>
    </div>
  );
}

function PositionContextDisplay({ contextData, loading, error, onClose }) {
  if (loading) {
    return (
      <div className="pos-ctx pos-ctx--loading">
        <span>⏳ Fetching context…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="pos-ctx pos-ctx--error">
        <span>⚠️ {error}</span>
      </div>
    );
  }

  if (!contextData) {
    return (
      <div className="pos-ctx pos-ctx--empty">
        <p>🖱 Click anywhere on the PDF to inspect spatial context.</p>
      </div>
    );
  }

  const { hover_position, nearby_words = [], empty_field_inference } = contextData;

  return (
    <div className="pos-ctx">
      <div className="pos-ctx__header">
        <strong>📌 Position Context</strong>
        {hover_position && (
          <span className="pos-ctx__coords">
            x: {hover_position.x.toFixed(1)}, y: {hover_position.y.toFixed(1)}
          </span>
        )}
        {onClose && (
          <button className="pos-ctx__close" onClick={onClose} aria-label="Close">✕</button>
        )}
      </div>

      {nearby_words.length === 0 && !empty_field_inference && (
        <p className="pos-ctx__no-words">No words found near this position.</p>
      )}

      {/* Empty-field inference */}
      {empty_field_inference && empty_field_inference.field_type_inferred && (
        <div className="pos-ctx__empty-inference">
          <strong>💡 Empty field inference</strong>
          <p>
            Likely field: <strong>{empty_field_inference.field_type_inferred}</strong>
            {' '}({Math.round((empty_field_inference.field_type_confidence || 0) * 100)}% confidence)
          </p>
          {empty_field_inference.evidence && empty_field_inference.evidence.length > 0 && (
            <p style={{ fontSize: '0.8rem', color: '#64748b' }}>
              Evidence: {empty_field_inference.evidence.join(', ')}
            </p>
          )}
        </div>
      )}

      {/* Nearby word cards */}
      {nearby_words.slice(0, 3).map((word, i) => (
        <WordCard key={i} word={word} />
      ))}
    </div>
  );
}

export default PositionContextDisplay;
