/**
 * usePixelHover.js — Pixel-level hover detection for PDF word markers.
 *
 * Given a list of markers (each with { id, x, y, width, height } in PDF coords)
 * and the current zoom scale, detects which marker is under the mouse cursor.
 *
 * Usage:
 *   const { hoveredMarker, handleMouseMove } = usePixelHover(markers, zoom);
 */

import { useState, useCallback } from 'react';

/**
 * @param {Array}  markers  Array of { id, x, y, width, height } objects (PDF coords)
 * @param {number} zoom     Current zoom scale applied to the PDF page
 * @returns {{ hoveredMarker: object|null, handleMouseMove: function }}
 */
export default function usePixelHover(markers = [], zoom = 1) {
  const [hoveredMarker, setHoveredMarker] = useState(null);

  const handleMouseMove = useCallback(
    (event) => {
      if (!markers.length) return;

      const rect = event.currentTarget.getBoundingClientRect();
      const mouseX = event.clientX - rect.left;
      const mouseY = event.clientY - rect.top;

      // Find the first marker whose scaled bounding box contains the cursor
      const found = markers.find((m) => {
        const left = m.x * zoom;
        const top = m.y * zoom;
        const right = left + m.width * zoom;
        const bottom = top + m.height * zoom;
        return mouseX >= left && mouseX <= right && mouseY >= top && mouseY <= bottom;
      });

      setHoveredMarker(found || null);
    },
    [markers, zoom]
  );

  const handleMouseLeave = useCallback(() => {
    setHoveredMarker(null);
  }, []);

  return { hoveredMarker, handleMouseMove, handleMouseLeave };
}
