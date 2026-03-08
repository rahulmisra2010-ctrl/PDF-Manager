/**
 * useFieldSync.js — Bidirectional synchronisation between PDF viewer and fields editor.
 *
 * Provides:
 *   - selectedFieldId: currently highlighted field
 *   - highlightBox: bounding box to draw on PDF canvas
 *   - selectField(field): select a field, set highlight box from field.bbox
 *   - clearSelection(): clear selection
 *   - onPageChange(page): notify page changes to filter visible fields
 */

import { useState, useCallback } from 'react';

/**
 * @param {Array} fields - List of extracted field objects with optional .bbox
 */
export function useFieldSync(fields = []) {
  const [selectedFieldId, setSelectedFieldId] = useState(null);
  const [highlightBox, setHighlightBox] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);

  const selectField = useCallback(
    (field) => {
      if (!field) {
        setSelectedFieldId(null);
        setHighlightBox(null);
        return;
      }
      setSelectedFieldId(field.id);
      if (field.bbox) {
        setHighlightBox(field.bbox);
      } else {
        setHighlightBox(null);
      }
    },
    []
  );

  const clearSelection = useCallback(() => {
    setSelectedFieldId(null);
    setHighlightBox(null);
  }, []);

  const onPageChange = useCallback((page) => {
    setCurrentPage(page);
    setHighlightBox(null);
    setSelectedFieldId(null);
  }, []);

  // Fields visible on the current page (if they have page info)
  const visibleFields = fields.filter(
    (f) => !f.bbox || !f.bbox.page || f.bbox.page === currentPage
  );

  return {
    selectedFieldId,
    highlightBox,
    currentPage,
    visibleFields,
    selectField,
    clearSelection,
    onPageChange,
  };
}

export default useFieldSync;
