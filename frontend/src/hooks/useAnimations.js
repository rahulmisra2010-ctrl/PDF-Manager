/**
 * useAnimations.js — Reusable Framer Motion animation variants.
 *
 * Provides common animation presets for components:
 * - fadeIn / fadeOut
 * - slideFromRight (SuggestionPanel)
 * - scaleEdit (FieldsEditor row in edit mode)
 * - pulse (one-click apply effect)
 * - hoverGlow (PDFViewer bounding boxes)
 */

import { useCallback } from 'react';

/** Fade in/out variant */
export const fadeVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.2 } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
};

/** Slide from right + fade in (suggestion panel) */
export const slideFromRightVariants = {
  hidden: { opacity: 0, x: 40 },
  visible: { opacity: 1, x: 0, transition: { duration: 0.3, ease: 'easeOut' } },
  exit: { opacity: 0, x: 40, transition: { duration: 0.2 } },
};

/** Scale + glow when entering edit mode */
export const editRowVariants = {
  normal: { scale: 1, boxShadow: 'none' },
  editing: {
    scale: 1.02,
    boxShadow: '0 0 0 2px rgba(99, 102, 241, 0.4)',
    transition: { duration: 0.2 },
  },
};

/** Pulse effect for one-click apply */
export const pulseVariants = {
  idle: { scale: 1 },
  pulse: {
    scale: [1, 1.08, 1],
    transition: { duration: 0.35, ease: 'easeInOut' },
  },
};

/** Hover glow for PDF bounding boxes */
export const glowVariants = {
  hidden: { opacity: 0, scale: 0.98 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.18 },
  },
  exit: { opacity: 0, scale: 0.98, transition: { duration: 0.15 } },
};

/** Stagger children list */
export const listContainerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.05 } },
};

export const listItemVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.2 } },
};

/** Heatmap color transition */
export const heatmapTransition = { duration: 0.5, ease: 'easeInOut' };

export default function useAnimations() {
  const getHoverAnimation = useCallback((isHovered) => ({
    opacity: isHovered ? 1 : 0,
    scale: isHovered ? 1 : 0.98,
    transition: { duration: 0.18 },
  }), []);

  return {
    fadeVariants,
    slideFromRightVariants,
    editRowVariants,
    pulseVariants,
    glowVariants,
    listContainerVariants,
    listItemVariants,
    heatmapTransition,
    getHoverAnimation,
  };
}
