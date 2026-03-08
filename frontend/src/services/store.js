/**
 * store.js — Zustand global state store for PDF Manager.
 *
 * Manages:
 *   - Document info
 *   - Fields with undo/redo history (max 50 snapshots)
 *   - Active field / PDF sync state
 *   - Suggestion panel state
 *   - UI toggles (dark mode, heatmap visibility)
 */

import { create } from 'zustand';

const HISTORY_LIMIT = 50;

export const useStore = create((set, get) => ({
  // ─── Document ───────────────────────────────────────────────────────────────
  document: null,
  setDocument: (doc) => set({ document: doc }),

  // ─── Fields with undo/redo ──────────────────────────────────────────────────
  fields: [],
  fieldHistory: [],   // past snapshots
  fieldFuture: [],    // future snapshots (for redo)

  setFields: (fields) => {
    const prev = get().fields;
    const history = [prev, ...get().fieldHistory].slice(0, HISTORY_LIMIT);
    set({ fields, fieldHistory: history, fieldFuture: [] });
  },

  /**
   * Update a single field value by id, pushing to history.
   */
  updateField: (fieldId, newValue) => {
    const prev = get().fields;
    const updated = prev.map((f) =>
      f.id === fieldId ? { ...f, value: newValue, is_edited: true } : f
    );
    const history = [prev, ...get().fieldHistory].slice(0, HISTORY_LIMIT);
    set({ fields: updated, fieldHistory: history, fieldFuture: [] });
  },

  /**
   * Batch-update multiple fields at once, single history entry.
   */
  batchUpdateFields: (updates) => {
    // updates: [{ id, value }, ...]
    const prev = get().fields;
    const patchMap = Object.fromEntries(updates.map((u) => [u.id, u.value]));
    const updated = prev.map((f) =>
      f.id in patchMap ? { ...f, value: patchMap[f.id], is_edited: true } : f
    );
    const history = [prev, ...get().fieldHistory].slice(0, HISTORY_LIMIT);
    set({ fields: updated, fieldHistory: history, fieldFuture: [] });
  },

  undo: () => {
    const { fieldHistory, fields, fieldFuture } = get();
    if (!fieldHistory.length) return;
    const [prev, ...rest] = fieldHistory;
    set({
      fields: prev,
      fieldHistory: rest,
      fieldFuture: [fields, ...fieldFuture].slice(0, HISTORY_LIMIT),
    });
  },

  redo: () => {
    const { fieldFuture, fields, fieldHistory } = get();
    if (!fieldFuture.length) return;
    const [next, ...rest] = fieldFuture;
    set({
      fields: next,
      fieldFuture: rest,
      fieldHistory: [fields, ...fieldHistory].slice(0, HISTORY_LIMIT),
    });
  },

  canUndo: () => get().fieldHistory.length > 0,
  canRedo: () => get().fieldFuture.length > 0,

  // ─── Active field / PDF sync ─────────────────────────────────────────────────
  activeFieldId: null,
  setActiveFieldId: (id) => set({ activeFieldId: id }),

  hoveredWordId: null,
  setHoveredWordId: (id) => set({ hoveredWordId: id }),

  // ─── Suggestion panel ────────────────────────────────────────────────────────
  suggestionPanelOpen: false,
  suggestionTargetFieldId: null,
  suggestionHistory: [], // [{ fieldId, appliedValue, previousValue }]

  openSuggestionPanel: (fieldId) =>
    set({ suggestionPanelOpen: true, suggestionTargetFieldId: fieldId }),

  closeSuggestionPanel: () =>
    set({ suggestionPanelOpen: false, suggestionTargetFieldId: null }),

  applySuggestion: (fieldId, newValue) => {
    const prev = get().fields.find((f) => f.id === fieldId);
    const previousValue = prev ? prev.value : '';
    get().updateField(fieldId, newValue);
    set((state) => ({
      suggestionHistory: [
        { fieldId, appliedValue: newValue, previousValue },
        ...state.suggestionHistory,
      ].slice(0, HISTORY_LIMIT),
    }));
  },

  undoLastSuggestion: () => {
    const { suggestionHistory } = get();
    if (!suggestionHistory.length) return;
    const [last, ...rest] = suggestionHistory;
    get().updateField(last.fieldId, last.previousValue);
    set({ suggestionHistory: rest });
  },

  // ─── UI toggles ──────────────────────────────────────────────────────────────
  darkMode: false,
  toggleDarkMode: () => set((s) => ({ darkMode: !s.darkMode })),

  heatmapVisible: false,
  toggleHeatmap: () => set((s) => ({ heatmapVisible: !s.heatmapVisible })),
}));

export default useStore;
