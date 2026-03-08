/**
 * useFieldSync.js — Bidirectional synchronization between PDF viewer and editor.
 *
 * Tracks:
 *   - activeFieldId: which field row is focused/selected in the editor
 *   - hoveredWordId: which word marker is currently hovered in the PDF viewer
 *
 * Provides callbacks to update each side and derive the other.
 */

import { useCallback } from 'react';
import { useStore } from '../services/store';

export default function useFieldSync() {
  const activeFieldId = useStore((s) => s.activeFieldId);
  const hoveredWordId = useStore((s) => s.hoveredWordId);
  const setActiveFieldId = useStore((s) => s.setActiveFieldId);
  const setHoveredWordId = useStore((s) => s.setHoveredWordId);

  /**
   * Called when a field row in the editor is clicked/focused.
   * Stores the field id so the PDF viewer can highlight the bbox.
   */
  const focusField = useCallback(
    (fieldId) => {
      setActiveFieldId(fieldId === activeFieldId ? null : fieldId);
    },
    [activeFieldId, setActiveFieldId]
  );

  /**
   * Called when a word marker in the PDF viewer is hovered.
   * Stores the word id so the matching editor row can be highlighted.
   */
  const hoverWord = useCallback(
    (wordId) => {
      setHoveredWordId(wordId);
    },
    [setHoveredWordId]
  );

  /**
   * Clear all sync state.
   */
  const clearSync = useCallback(() => {
    setActiveFieldId(null);
    setHoveredWordId(null);
  }, [setActiveFieldId, setHoveredWordId]);

  return { activeFieldId, hoveredWordId, focusField, hoverWord, clearSync };
}
