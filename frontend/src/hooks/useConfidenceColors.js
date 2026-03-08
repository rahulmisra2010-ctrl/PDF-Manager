/**
 * useConfidenceColors.js — Maps confidence scores to color classes and labels.
 *
 * Confidence thresholds:
 *   HIGH  >= 0.85  → green
 *   MED   >= 0.65  → yellow
 *   LOW   <  0.65  → red
 */

const HIGH = 0.85;
const MED = 0.65;

/**
 * Returns color key ('green' | 'yellow' | 'red') for a 0–1 confidence score.
 * @param {number} confidence
 * @returns {'green'|'yellow'|'red'}
 */
export function getConfidenceColor(confidence) {
  if (confidence >= HIGH) return 'green';
  if (confidence >= MED) return 'yellow';
  return 'red';
}

/**
 * Returns a CSS hex color string for a confidence score.
 * @param {number} confidence
 * @returns {string}
 */
export function getConfidenceHex(confidence) {
  if (confidence >= HIGH) return '#10b981';
  if (confidence >= MED) return '#f59e0b';
  return '#ef4444';
}

/**
 * Returns the label string for a confidence score.
 * @param {number} confidence
 * @returns {'High'|'Medium'|'Low'}
 */
export function getConfidenceLabel(confidence) {
  if (confidence >= HIGH) return 'High';
  if (confidence >= MED) return 'Medium';
  return 'Low';
}

/**
 * React hook that provides confidence color utilities.
 */
export function useConfidenceColors() {
  return { getConfidenceColor, getConfidenceHex, getConfidenceLabel, HIGH, MED };
}

export default useConfidenceColors;
