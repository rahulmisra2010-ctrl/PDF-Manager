/**
 * usePixelHover.js — Pixel-level hover detection for bounding boxes.
 *
 * Given a list of word markers with {x, y, width, height} in PDF coordinates
 * and a scale factor, tracks which marker is under the mouse cursor.
 *
 * Usage:
 *   const { hoveredMarker, containerProps } = usePixelHover(markers, scale, onHover);
 *   <div {...containerProps}>...</div>
 */

import { useState, useCallback, useRef } from 'react';

/**
 * @param {Array} markers   - Array of { x, y, width, height, text, confidence, ... }
 * @param {number} scale    - PDF coordinate scale factor
 * @param {function} onHover - Called with hovered marker or null
 */
export default function usePixelHover(markers = [], scale = 1, onHover) {
  const [hoveredMarker, setHoveredMarker] = useState(null);
  const containerRef = useRef(null);

  const handleMouseMove = useCallback(
    (e) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      // Find the topmost marker that contains the mouse position
      let found = null;
      for (let i = markers.length - 1; i >= 0; i--) {
        const m = markers[i];
        const left = m.x * scale;
        const top = m.y * scale;
        const right = left + m.width * scale;
        const bottom = top + m.height * scale;

        if (mouseX >= left && mouseX <= right && mouseY >= top && mouseY <= bottom) {
          found = m;
          break;
        }
      }

      if (found !== hoveredMarker) {
        setHoveredMarker(found);
        onHover && onHover(found);
      }
    },
    [markers, scale, hoveredMarker, onHover]
  );

  const handleMouseLeave = useCallback(() => {
    setHoveredMarker(null);
    onHover && onHover(null);
  }, [onHover]);

  const containerProps = {
    ref: containerRef,
    onMouseMove: handleMouseMove,
    onMouseLeave: handleMouseLeave,
  };

  /**
   * Given a single marker, return whether it is currently hovered.
   * Uses identity comparison (same object reference or matching text+position).
   */
  const isHovered = useCallback(
    (marker) => {
      if (!hoveredMarker || !marker) return false;
      return (
        hoveredMarker === marker ||
        (hoveredMarker.text === marker.text &&
          hoveredMarker.x === marker.x &&
          hoveredMarker.y === marker.y)
      );
    },
    [hoveredMarker]
  );

  return { hoveredMarker, containerProps, isHovered };
}
