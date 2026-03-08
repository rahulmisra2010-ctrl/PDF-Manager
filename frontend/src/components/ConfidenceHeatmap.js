/**
 * ConfidenceHeatmap.js — Enhanced confidence heatmap with animations and tooltips.
 *
 * Features:
 * - Color-coded word markers: Green (≥85%), Yellow (≥65%), Red (<65%)
 * - Framer Motion fade-in/out for word markers
 * - Hover tooltip showing exact confidence percentage
 * - Toggle overlay visibility
 * - Regional confidence breakdown (header/body/footer)
 * - Pixel heatmap mode (base64 PNG from backend)
 * - Stats summary row
 *
 * Props:
 *   heatmapData   {object}   Response from GET /api/v1/documents/:id/heatmap
 *   imageData     {string}   Optional base64 PNG for pixel heatmap mode
 *   pageNumber    {number}
 *   onWordHover   {func}     Called with hovered word text (for PDF sync)
 */

import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import useConfidenceColors from '../hooks/useConfidenceColors';
import { fadeVariants, heatmapTransition } from '../hooks/useAnimations';
import styles from './styles/ConfidenceHeatmap.module.css';

const DISPLAY_WIDTH = 480;

function WordMarker({ marker, scale, isHovered, onEnter, onLeave }) {
  const { getHeatmapColor, getGlowStyle } = useConfidenceColors();
  const { text, confidence, x, y, width, height } = marker;
  const pct = Math.round(confidence * 100);
  const bgColor = getHeatmapColor(confidence, isHovered ? 0.85 : 0.55);
  const boxShadow = isHovered ? getGlowStyle(confidence) : 'none';

  return (
    <motion.div
      className={styles.wordMarker}
      style={{
        left: x * scale,
        top: y * scale,
        width: width * scale,
        height: height * scale,
        background: bgColor,
        border: `1px solid ${getHeatmapColor(confidence, 0.7)}`,
        boxShadow,
        color: '#000',
        lineHeight: `${height * scale}px`,
      }}
      animate={{ opacity: 1 }}
      initial={{ opacity: 0 }}
      transition={heatmapTransition}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      aria-label={`"${text}" — ${pct}% confidence`}
    >
      {width * scale > 28 && (
        <span style={{ fontSize: '8px', userSelect: 'none' }}>{text}</span>
      )}
    </motion.div>
  );
}

function ConfidenceHeatmap({ heatmapData, imageData, pageNumber, onWordHover }) {
  const [mode, setMode] = useState('words'); // 'words' | 'image'
  const [visible, setVisible] = useState(true);
  const [tooltip, setTooltip] = useState(null); // { text, pct, x, y }
  const { getColors, HIGH_THRESHOLD, MED_THRESHOLD } = useConfidenceColors();

  const handleWordEnter = useCallback(
    (marker, e) => {
      const pct = Math.round(marker.confidence * 100);
      setTooltip({ text: marker.text, pct, x: e.clientX, y: e.clientY });
      onWordHover && onWordHover(marker.text);
    },
    [onWordHover]
  );

  const handleWordLeave = useCallback(() => {
    setTooltip(null);
    onWordHover && onWordHover(null);
  }, [onWordHover]);

  if (!heatmapData) {
    return (
      <div className={styles.heatmap}>
        <div className={styles.empty}>
          <span>🔥</span>
          <p>No heatmap data available.</p>
          <small>Run OCR extraction first.</small>
        </div>
      </div>
    );
  }

  const {
    word_markers = [],
    avg_confidence = 0,
    page_width = 595,
    page_height = 842,
    regions = null,
  } = heatmapData;

  const scale = DISPLAY_WIDTH / page_width;
  const displayHeight = page_height * scale;
  const avgPct = Math.round(avg_confidence * 100);
  const avgColors = getColors(avg_confidence);

  // Regional confidence
  // Approximate regional breakdown using thirds of the word list as a fallback.
  // When heatmapData contains an actual `regions` object from the backend,
  // that takes precedence over this approximation.
  const thirds = Math.floor(word_markers.length / 3);
  const headerWords = word_markers.slice(0, thirds);
  const bodyWords = word_markers.slice(thirds, thirds * 2);
  const footerWords = word_markers.slice(thirds * 2);
  const avgOf = (arr) =>
    arr.length
      ? Math.round((arr.reduce((s, m) => s + m.confidence, 0) / arr.length) * 100)
      : 0;

  const regionData = regions || {
    header: avgOf(headerWords),
    body: avgOf(bodyWords),
    footer: avgOf(footerWords),
  };

  const highCount = word_markers.filter((m) => m.confidence >= HIGH_THRESHOLD).length;
  const medCount = word_markers.filter(
    (m) => m.confidence >= MED_THRESHOLD && m.confidence < HIGH_THRESHOLD
  ).length;
  const lowCount = word_markers.length - highCount - medCount;

  return (
    <div className={styles.heatmap}>
      {/* Header row */}
      <div className={styles.header}>
        <h4 className={styles.title}>
          🔥 Confidence Heatmap — Page {pageNumber || heatmapData.page_number || 1}
        </h4>
        <span
          className={styles.avgBadge}
          style={{ background: avgColors.badge, color: avgColors.text }}
        >
          Avg: {avgPct}%
        </span>
        <button
          className={`${styles.toggleBtn} ${visible ? styles.active : ''}`}
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? 'Hide heatmap' : 'Show heatmap'}
        >
          {visible ? '👁 Hide' : '👁 Show'}
        </button>
      </div>

      {/* Legend */}
      <div className={styles.legend} role="list" aria-label="Confidence legend">
        {[
          { label: `High (≥${Math.round(HIGH_THRESHOLD * 100)}%)`, color: '#10b981' },
          { label: `Medium (≥${Math.round(MED_THRESHOLD * 100)}%)`, color: '#f59e0b' },
          { label: 'Low', color: '#ef4444' },
        ].map(({ label, color }) => (
          <span key={label} className={styles.legendItem} role="listitem">
            <span className={styles.legendDot} style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>

      {/* Mode switcher — only shown when pixel image is available */}
      {imageData && (
        <div className={styles.modeSwitch} role="group" aria-label="Display mode">
          <button
            className={`${styles.modeBtn} ${mode === 'words' ? styles.active : ''}`}
            onClick={() => setMode('words')}
            aria-pressed={mode === 'words'}
          >
            Word overlay
          </button>
          <button
            className={`${styles.modeBtn} ${mode === 'image' ? styles.active : ''}`}
            onClick={() => setMode('image')}
            aria-pressed={mode === 'image'}
          >
            Pixel heatmap
          </button>
        </div>
      )}

      {/* Regional breakdown */}
      <div className={styles.regions} aria-label="Regional confidence">
        {[
          { label: 'Header', score: regionData.header },
          { label: 'Body', score: regionData.body },
          { label: 'Footer', score: regionData.footer },
        ].map(({ label, score }) => {
          const conf = (score || 0) / 100;
          const c = getColors(conf);
          return (
            <div key={label} className={styles.regionCard}>
              <div className={styles.regionLabel}>{label}</div>
              <div className={styles.regionScore} style={{ color: c.hex }}>
                {score || 0}%
              </div>
            </div>
          );
        })}
      </div>

      {/* Canvas */}
      <AnimatePresence>
        {visible && (
          <motion.div
            key="canvas-wrapper"
            className={styles.canvasWrapper}
            variants={fadeVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
          >
            {mode === 'image' && imageData ? (
              <img
                className={styles.heatmapImage}
                src={imageData}
                alt={`Confidence heatmap page ${pageNumber}`}
              />
            ) : (
              <div
                className={styles.canvas}
                style={{ width: DISPLAY_WIDTH, height: displayHeight }}
                role="img"
                aria-label="Word confidence overlay"
              >
                {word_markers.map((marker, idx) => (
                  <WordMarker
                    key={`${marker.text}-${idx}`}
                    marker={marker}
                    scale={scale}
                    isHovered={
                      tooltip !== null && tooltip.text === marker.text
                    }
                    onEnter={(e) => handleWordEnter(marker, e)}
                    onLeave={handleWordLeave}
                  />
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Tooltip — rendered via fixed positioning */}
      <AnimatePresence>
        {tooltip && (
          <motion.div
            className={styles.tooltip}
            style={{ left: tooltip.x, top: tooltip.y }}
            variants={fadeVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
          >
            "{tooltip.text}" — {tooltip.pct}%
          </motion.div>
        )}
      </AnimatePresence>

      {/* Stats */}
      <div className={styles.stats} aria-label="Word confidence statistics">
        <span className={styles.statsItem}>Total: {word_markers.length}</span>
        <span className={styles.statsItem} style={{ color: '#065f46' }}>
          ✅ High: {highCount}
        </span>
        <span className={styles.statsItem} style={{ color: '#92400e' }}>
          ⚠️ Medium: {medCount}
        </span>
        <span className={styles.statsItem} style={{ color: '#991b1b' }}>
          ❌ Low: {lowCount}
        </span>
      </div>
    </div>
  );
}

export default ConfidenceHeatmap;
