/**
 * useConfidenceColors.js — Maps confidence scores to colors and labels.
 *
 * Thresholds: HIGH ≥ 0.85 (green), MED ≥ 0.65 (yellow), LOW < 0.65 (red)
 * Consistent with backend/ocr/confidence_calculator.py thresholds.
 */

import { useCallback } from 'react';

const HIGH_THRESHOLD = 0.85;
const MED_THRESHOLD = 0.65;

const COLORS = {
  high: {
    key: 'high',
    bg: 'rgba(16, 185, 129, 0.15)',
    border: 'rgba(16, 185, 129, 0.8)',
    text: '#065f46',
    badge: '#d1fae5',
    hex: '#10b981',
    label: 'High',
    icon: '✅',
  },
  medium: {
    key: 'medium',
    bg: 'rgba(245, 158, 11, 0.15)',
    border: 'rgba(245, 158, 11, 0.8)',
    text: '#92400e',
    badge: '#fef3c7',
    hex: '#f59e0b',
    label: 'Medium',
    icon: '⚠️',
  },
  low: {
    key: 'low',
    bg: 'rgba(239, 68, 68, 0.15)',
    border: 'rgba(239, 68, 68, 0.8)',
    text: '#991b1b',
    badge: '#fee2e2',
    hex: '#ef4444',
    label: 'Low',
    icon: '❌',
  },
};

export function getConfidenceKey(confidence) {
  if (confidence >= HIGH_THRESHOLD) return 'high';
  if (confidence >= MED_THRESHOLD) return 'medium';
  return 'low';
}

export function getConfidenceColors(confidence) {
  return COLORS[getConfidenceKey(confidence)];
}

export default function useConfidenceColors() {
  const getColors = useCallback((confidence) => getConfidenceColors(confidence), []);
  const getKey = useCallback((confidence) => getConfidenceKey(confidence), []);

  const getHeatmapColor = useCallback((confidence, alpha = 0.6) => {
    const key = getConfidenceKey(confidence);
    if (key === 'high') return `rgba(16, 185, 129, ${alpha})`;
    if (key === 'medium') return `rgba(245, 158, 11, ${alpha})`;
    return `rgba(239, 68, 68, ${alpha})`;
  }, []);

  const getGlowStyle = useCallback((confidence) => {
    const { hex } = getConfidenceColors(confidence);
    return `0 0 8px ${hex}80, 0 0 16px ${hex}40`;
  }, []);

  return { getColors, getKey, getHeatmapColor, getGlowStyle, COLORS, HIGH_THRESHOLD, MED_THRESHOLD };
}
