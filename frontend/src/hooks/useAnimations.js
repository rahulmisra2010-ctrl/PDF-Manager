/**
 * useAnimations.js — Reusable Framer Motion animation variants.
 *
 * Provides pre-configured animation variants for use across the application.
 */

export const fadeVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.2 } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
};

export const slideFromRightVariants = {
  hidden: { opacity: 0, x: 60 },
  visible: { opacity: 1, x: 0, transition: { type: 'spring', stiffness: 300, damping: 30 } },
  exit: { opacity: 0, x: 60, transition: { duration: 0.2 } },
};

export const editRowVariants = {
  idle: { scale: 1, boxShadow: '0 0 0px rgba(59,130,246,0)' },
  editing: {
    scale: 1.01,
    boxShadow: '0 0 8px rgba(59,130,246,0.5)',
    transition: { duration: 0.2 },
  },
};

export const pulseVariants = {
  idle: { scale: 1 },
  pulse: {
    scale: [1, 1.08, 1],
    transition: { duration: 0.35, ease: 'easeInOut' },
  },
};

export const glowVariants = {
  idle: { boxShadow: '0 0 0px rgba(16,185,129,0)' },
  glow: {
    boxShadow: [
      '0 0 0px rgba(16,185,129,0)',
      '0 0 12px rgba(16,185,129,0.8)',
      '0 0 0px rgba(16,185,129,0)',
    ],
    transition: { duration: 0.6, ease: 'easeInOut' },
  },
};

export const listContainerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.05, when: 'beforeChildren' },
  },
};

export const listItemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.2 } },
  exit: { opacity: 0, y: -10, transition: { duration: 0.15 } },
};

export const heatmapTransition = { duration: 0.3, ease: 'easeOut' };
