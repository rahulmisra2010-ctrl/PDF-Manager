/**
 * useConfidenceColors.js — Maps confidence scores to colors and labels.
 *
 * Thresholds:
 *   HIGH  >= 0.85  → green
 *   MED   >= 0.65  → yellow
 *   LOW    < 0.65  → red
 *
 * Returns a hook and a standalone utility function.
 */

const HIGH_THRESHOLD = 0.85;
const MED_THRESHOLD = 0.65;

export const CONFIDENCE_LEVELS = {
  HIGH: {
    key: 'HIGH',
    label: 'High',
    color: '#065f46',
    background: '#d1fae5',
    border: '#6ee7b7',
    badge: '✅',
    hex: '#10b981',
  },
  MED: {
    key: 'MED',
    label: 'Medium',
    color: '#92400e',
    background: '#fef3c7',
    border: '#fcd34d',
    badge: '⚠️',
    hex: '#f59e0b',
  },
  LOW: {
    key: 'LOW',
    label: 'Low',
    color: '#991b1b',
    background: '#fee2e2',
    border: '#fca5a5',
    badge: '❌',
    hex: '#ef4444',
  },
};

/**
 * Returns the confidence level object for a given score (0–1).
 */
export function getConfidenceLevel(score) {
  if (score >= HIGH_THRESHOLD) return CONFIDENCE_LEVELS.HIGH;
  if (score >= MED_THRESHOLD) return CONFIDENCE_LEVELS.MED;
  return CONFIDENCE_LEVELS.LOW;
}

/**
 * useConfidenceColors — hook exposing confidence color utilities.
 */
export default function useConfidenceColors() {
  return { getConfidenceLevel, CONFIDENCE_LEVELS, HIGH_THRESHOLD, MED_THRESHOLD };
}
