/**
 * usePixelHover.js — Pixel-level hover detection for bounding boxes on a canvas.
 *
 * Attaches a mousemove listener to a container ref and returns the field
 * whose bounding box contains the current mouse position.
 *
 * @param {React.RefObject} containerRef - Ref to the container element
 * @param {Array} fields - Fields with { bbox: { x, y, width, height } }
 * @param {number} scale - Current zoom scale factor
 * @returns {{ hoveredField: object|null, mousePos: { x, y } }}
 */

import { useState, useEffect, useCallback } from 'react';

export function usePixelHover(containerRef, fields = [], scale = 1) {
  const [hoveredField, setHoveredField] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  const handleMouseMove = useCallback(
    (e) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = (e.clientX - rect.left) / scale;
      const y = (e.clientY - rect.top) / scale;
      setMousePos({ x, y });

      const hit = fields.find((f) => {
        if (!f.bbox) return false;
        const { x: bx, y: by, width: bw, height: bh } = f.bbox;
        return x >= bx && x <= bx + bw && y >= by && y <= by + bh;
      });
      setHoveredField(hit || null);
    },
    [containerRef, fields, scale]
  );

  const handleMouseLeave = useCallback(() => {
    setHoveredField(null);
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener('mousemove', handleMouseMove);
    el.addEventListener('mouseleave', handleMouseLeave);
    return () => {
      el.removeEventListener('mousemove', handleMouseMove);
      el.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, [containerRef, handleMouseMove, handleMouseLeave]);

  return { hoveredField, mousePos };
}

export default usePixelHover;
