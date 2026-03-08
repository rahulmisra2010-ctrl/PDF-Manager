/**
 * ConfidenceHeatmap.js — Word-level confidence visualization overlay.
 *
 * Features:
 * - Color-coded word markers (Green ≥85%, Yellow ≥65%, Red <65%)
 * - Framer Motion fade-in/out for overlay visibility
 * - Hover tooltips showing exact confidence percentages
 * - Toggle overlay visibility
 * - Regional confidence breakdown (header / body / footer)
 * - Statistics summary row
 *
 * Props:
 *   words        {Array}   [{ id, text, x, y, width, height, confidence, region }]
 *   zoom         {number}  Current PDF zoom scale
 *   visible      {boolean} Whether the overlay is shown
 *   onToggle     {func}    Called to toggle visibility
 */

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { getConfidenceLevel } from '../hooks/useConfidenceColors';
import { fadeVariants, heatmapTransition } from '../hooks/useAnimations';
import styles from './styles/ConfidenceHeatmap.module.css';

function Tooltip({ text, confidence }) {
  const level = getConfidenceLevel(confidence);
  return (
    <div className={styles.tooltip}>
      <span className={styles.tooltipWord}>{text}</span>
      <span className={styles.tooltipConf} style={{ color: level.hex }}>
        {Math.round(confidence * 100)}% — {level.label}
      </span>
    </div>
  );
}

function WordMarker({ word, zoom }) {
  const [hovered, setHovered] = useState(false);
  const level = getConfidenceLevel(word.confidence || 0);

  return (
    <motion.div
      className={styles.wordMarker}
      style={{
        left: word.x * zoom,
        top: word.y * zoom,
        width: word.width * zoom,
        height: word.height * zoom,
        background: level.background,
        border: `1px solid ${level.border}`,
      }}
      initial={{ opacity: 0 }}
      animate={{ opacity: hovered ? 0.85 : 0.45 }}
      transition={heatmapTransition}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      aria-label={`${word.text}: ${Math.round((word.confidence || 0) * 100)}% confidence`}
    >
      {hovered && <Tooltip text={word.text} confidence={word.confidence || 0} />}
    </motion.div>
  );
}

function RegionStats({ words, region }) {
  const regionWords = words.filter((w) => w.region === region);
  if (!regionWords.length) return null;
  const avg = regionWords.reduce((sum, w) => sum + (w.confidence || 0), 0) / regionWords.length;
  const level = getConfidenceLevel(avg);
  return (
    <span className={styles.regionStat} style={{ color: level.color, background: level.background }}>
      {region}: {Math.round(avg * 100)}%
    </span>
  );
}

function ConfidenceHeatmap({ words = [], zoom = 1, visible, onToggle }) {
  const high = words.filter((w) => (w.confidence || 0) >= 0.85).length;
  const med  = words.filter((w) => (w.confidence || 0) >= 0.65 && (w.confidence || 0) < 0.85).length;
  const low  = words.length - high - med;

  return (
    <>
      {/* Toggle button + stats summary */}
      <div className={styles.controls}>
        <button
          className={styles.toggleBtn}
          onClick={onToggle}
          aria-pressed={visible}
        >
          {visible ? '🙈 Hide Heatmap' : '🔥 Show Heatmap'}
        </button>

        {words.length > 0 && (
          <div className={styles.stats}>
            <span className={styles.statHigh}>✅ {high}</span>
            <span className={styles.statMed}>⚠️ {med}</span>
            <span className={styles.statLow}>❌ {low}</span>
            <RegionStats words={words} region="header" />
            <RegionStats words={words} region="body" />
            <RegionStats words={words} region="footer" />
          </div>
        )}
      </div>

      {/* Overlay markers */}
      <AnimatePresence>
        {visible && words.length > 0 && (
          <motion.div
            className={styles.overlay}
            variants={fadeVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            aria-label="Confidence heatmap overlay"
          >
            {words.map((word, idx) => (
              <WordMarker key={word.id || idx} word={word} zoom={zoom} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

export default ConfidenceHeatmap;
