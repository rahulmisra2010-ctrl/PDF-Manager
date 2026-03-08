/**
 * useFieldSync.js — Bidirectional synchronization between PDF viewer and FieldsEditor.
 *
 * Keeps track of:
 * - Which field is currently active (clicked in editor → highlighted in PDF)
 * - Which word/region is hovered in PDF (hovered in PDF → highlighted in editor)
 *
 * Returns callbacks and state that both PDFViewer and FieldsEditor consume.
 */

import { useState, useCallback } from 'react';

export default function useFieldSync() {
  /** Bounding box to highlight in the PDF viewer {x, y, width, height, page} */
  const [highlightBox, setHighlightBox] = useState(null);

  /** Field ID that is currently active/selected */
  const [activeFieldId, setActiveFieldId] = useState(null);

  /** Word text currently hovered in PDF (for reverse-sync to editor) */
  const [hoveredWord, setHoveredWord] = useState(null);

  /**
   * Called when user clicks/hovers a field in FieldsEditor.
   * Scrolls PDF viewer to the corresponding bounding box.
   */
  const focusField = useCallback((field) => {
    if (!field) {
      setHighlightBox(null);
      setActiveFieldId(null);
      return;
    }
    setActiveFieldId(field.id || field.field_name);
    if (field.bbox) {
      setHighlightBox({ ...field.bbox, page: field.page_number || 1 });
    }
  }, []);

  /**
   * Called when user hovers a word marker in PDFViewer/ConfidenceHeatmap.
   * Highlights the matching field row in FieldsEditor.
   */
  const focusWord = useCallback((wordText) => {
    setHoveredWord(wordText || null);
  }, []);

  const clearSync = useCallback(() => {
    setHighlightBox(null);
    setActiveFieldId(null);
    setHoveredWord(null);
  }, []);

  /** Determine if a field row should be highlighted based on hovered word */
  const isFieldHighlighted = useCallback(
    (field) => {
      if (!hoveredWord) return false;
      const val = (field.value || '').toLowerCase();
      const word = hoveredWord.toLowerCase();
      return val.includes(word);
    },
    [hoveredWord]
  );

  return {
    highlightBox,
    activeFieldId,
    hoveredWord,
    focusField,
    focusWord,
    clearSync,
    isFieldHighlighted,
    setHighlightBox,
  };
}
