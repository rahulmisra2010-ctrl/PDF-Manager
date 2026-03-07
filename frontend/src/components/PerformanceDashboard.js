/**
 * PerformanceDashboard.js — OCR & extraction performance metrics.
 *
 * Displays:
 * - Document quality score with grade
 * - Regional scores (Header / Body / Footer)
 * - Word confidence breakdown bar chart
 * - Per-page quality
 * - Engines used
 *
 * Props:
 *   quality        {object}  Quality dict from AI extraction API
 *   enginesUsed    {Array}   List of engine name strings
 *   extractionTime {number}  Seconds taken for extraction
 *   fields         {Array}   Extracted fields (for field-level stats)
 */

import React from 'react';

function ScoreBar({ label, score, maxScore = 100 }) {
  const pct = Math.min(100, Math.max(0, (score / maxScore) * 100));
  let barColor = '#ef4444'; // red
  if (pct >= 85) barColor = '#10b981';      // green
  else if (pct >= 65) barColor = '#f59e0b'; // yellow

  return (
    <div className="perf-dash__score-bar">
      <div className="perf-dash__score-label">
        <span>{label}</span>
        <span style={{ color: barColor }}>{Math.round(pct)}%</span>
      </div>
      <div className="perf-dash__bar-track">
        <div
          className="perf-dash__bar-fill"
          style={{ width: `${pct}%`, background: barColor }}
        />
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, sub }) {
  return (
    <div className="perf-dash__stat-card">
      <div className="perf-dash__stat-icon">{icon}</div>
      <div className="perf-dash__stat-value">{value}</div>
      <div className="perf-dash__stat-label">{label}</div>
      {sub && <div className="perf-dash__stat-sub">{sub}</div>}
    </div>
  );
}

function PerformanceDashboard({ quality, enginesUsed = [], extractionTime, fields = [] }) {
  if (!quality) {
    return (
      <div className="perf-dash perf-dash--empty">
        <p>Run AI extraction to see performance metrics.</p>
      </div>
    );
  }

  const {
    score = 0,
    grade = 'N/A',
    header_score = 0,
    body_score = 0,
    footer_score = 0,
    total_words = 0,
    high_conf_words = 0,
    medium_conf_words = 0,
    low_conf_words = 0,
    page_scores = [],
  } = quality;

  const highPct = total_words > 0 ? Math.round((high_conf_words / total_words) * 100) : 0;
  const medPct  = total_words > 0 ? Math.round((medium_conf_words / total_words) * 100) : 0;
  const lowPct  = total_words > 0 ? Math.round((low_conf_words / total_words) * 100) : 0;

  const avgFieldConf =
    fields.length > 0
      ? Math.round(fields.reduce((s, f) => s + (f.confidence || 0), 0) / fields.length * 100)
      : 0;

  let gradeColor = '#ef4444';
  if (score >= 85) gradeColor = '#10b981';
  else if (score >= 65) gradeColor = '#f59e0b';

  return (
    <div className="perf-dash">
      <h4 className="perf-dash__title">📊 Performance Dashboard</h4>

      {/* Top stat cards */}
      <div className="perf-dash__cards">
        <StatCard
          icon="🏅"
          label="Document Quality"
          value={<span style={{ color: gradeColor }}>{Math.round(score)}%</span>}
          sub={`Grade: ${grade}`}
        />
        <StatCard
          icon="📝"
          label="Total Words"
          value={total_words}
          sub={`${fields.length} fields extracted`}
        />
        <StatCard
          icon="🎯"
          label="Avg Field Confidence"
          value={`${avgFieldConf}%`}
        />
        <StatCard
          icon="⏱"
          label="Extraction Time"
          value={extractionTime != null ? `${extractionTime}s` : '—'}
        />
      </div>

      {/* Regional scores */}
      <div className="perf-dash__section">
        <h5>Regional Quality Scores</h5>
        <ScoreBar label="Header Region" score={header_score} />
        <ScoreBar label="Body Region" score={body_score} />
        <ScoreBar label="Footer Region" score={footer_score} />
      </div>

      {/* Word confidence breakdown */}
      <div className="perf-dash__section">
        <h5>Word Confidence Breakdown</h5>
        <div className="perf-dash__breakdown">
          <div className="perf-dash__breakdown-bar" style={{ flex: highPct, background: '#10b981' }} title={`High: ${highPct}%`} />
          <div className="perf-dash__breakdown-bar" style={{ flex: medPct, background: '#f59e0b' }} title={`Medium: ${medPct}%`} />
          <div className="perf-dash__breakdown-bar" style={{ flex: Math.max(lowPct, 1), background: '#ef4444' }} title={`Low: ${lowPct}%`} />
        </div>
        <div className="perf-dash__breakdown-legend">
          <span style={{ color: '#10b981' }}>✅ High (≥85%): {high_conf_words}</span>
          <span style={{ color: '#f59e0b' }}>⚠️ Med (≥65%): {medium_conf_words}</span>
          <span style={{ color: '#ef4444' }}>❌ Low: {low_conf_words}</span>
        </div>
      </div>

      {/* Per-page quality */}
      {page_scores.length > 0 && (
        <div className="perf-dash__section">
          <h5>Per-Page Quality</h5>
          {page_scores.map((ps, idx) => (
            <ScoreBar key={idx} label={`Page ${idx + 1}`} score={ps} />
          ))}
        </div>
      )}

      {/* Engines */}
      <div className="perf-dash__section">
        <h5>OCR Engines Used</h5>
        <div className="perf-dash__engines">
          {(enginesUsed.length ? enginesUsed : ['pymupdf']).map((eng) => (
            <span key={eng} className="perf-dash__engine-badge">
              {eng}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export default PerformanceDashboard;
