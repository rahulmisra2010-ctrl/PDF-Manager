/**
 * useAnimations.js — Framer Motion animation variants for PDF Manager components.
 *
 * Usage:
 *   const { fadeIn, slideInRight, scaleIn } = useAnimations();
 *   <motion.div variants={fadeIn} initial="hidden" animate="visible" />
 */

export const fadeIn = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.25 } },
  exit: { opacity: 0, transition: { duration: 0.2 } },
};

export const slideInRight = {
  hidden: { x: '100%', opacity: 0 },
  visible: { x: 0, opacity: 1, transition: { type: 'spring', stiffness: 300, damping: 30 } },
  exit: { x: '100%', opacity: 0, transition: { duration: 0.2 } },
};

export const slideInLeft = {
  hidden: { x: '-100%', opacity: 0 },
  visible: { x: 0, opacity: 1, transition: { type: 'spring', stiffness: 300, damping: 30 } },
  exit: { x: '-100%', opacity: 0, transition: { duration: 0.2 } },
};

export const scaleIn = {
  hidden: { scale: 0.9, opacity: 0 },
  visible: { scale: 1, opacity: 1, transition: { type: 'spring', stiffness: 300, damping: 25 } },
  exit: { scale: 0.9, opacity: 0, transition: { duration: 0.15 } },
};

export const listItem = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.2 } },
};

export const staggerContainer = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.05 } },
};

/**
 * React hook that exposes all animation variants.
 */
export function useAnimations() {
  return { fadeIn, slideInRight, slideInLeft, scaleIn, listItem, staggerContainer };
}

export default useAnimations;
