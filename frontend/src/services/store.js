/**
 * store.js — Zustand global state for PDF-Manager.
 *
 * Manages cross-component state:
 * - Current document
 * - Extracted fields with undo/redo history
 * - Active field / PDF highlight sync
 * - Suggestion panel state
 * - UI toggles (heatmap visible, dark mode)
 */

import { create } from 'zustand';

const useStore = create((set, get) => ({
  // ─── Document ────────────────────────────────────────────────────────────────
  document: null,
  setDocument: (doc) => set({ document: doc }),
  clearDocument: () =>
    set({
      document: null,
      fields: [],
      fieldHistory: [],
      historyIndex: -1,
      activeFieldId: null,
      highlightBox: null,
      suggestions: [],
      activeSuggestionFieldId: null,
    }),

  // ─── Fields with undo/redo ───────────────────────────────────────────────────
  fields: [],
  /** Stack of past field states for undo */
  fieldHistory: [],
  historyIndex: -1,

  setFields: (fields) =>
    set((state) => {
      // Push current fields onto history before replacing
      const newHistory = state.fieldHistory.slice(0, state.historyIndex + 1);
      newHistory.push(state.fields);
      return {
        fields,
        fieldHistory: newHistory.slice(-50), // keep last 50 snapshots
        historyIndex: newHistory.length - 1,
      };
    }),

  /** Update a single field value (also pushes to history) */
  updateFieldValue: (fieldId, newValue) =>
    set((state) => {
      // Only push to history once per update (don't use setFields to avoid duplicate push)
      const newHistory = state.fieldHistory.slice(0, state.historyIndex + 1);
      newHistory.push(state.fields);
      const updated = state.fields.map((f) =>
        f.id === fieldId ? { ...f, value: newValue, is_edited: true } : f
      );
      return {
        fields: updated,
        fieldHistory: newHistory.slice(-50),
        historyIndex: newHistory.length - 1,
      };
    }),

  undo: () =>
    set((state) => {
      if (state.historyIndex < 0) return {};
      const prevFields = state.fieldHistory[state.historyIndex];
      return {
        fields: prevFields || [],
        historyIndex: state.historyIndex - 1,
      };
    }),

  redo: () =>
    set((state) => {
      const nextIndex = state.historyIndex + 1;
      if (nextIndex >= state.fieldHistory.length) return {};
      return {
        fields: state.fieldHistory[nextIndex],
        historyIndex: nextIndex,
      };
    }),

  canUndo: () => get().historyIndex >= 0,
  canRedo: () => get().historyIndex < get().fieldHistory.length - 1,

  // ─── Active field / PDF sync ─────────────────────────────────────────────────
  activeFieldId: null,
  highlightBox: null,

  setActiveField: (field) =>
    set({
      activeFieldId: field ? field.id || field.field_name : null,
      highlightBox: field?.bbox
        ? { ...field.bbox, page: field.page_number || 1 }
        : null,
    }),

  clearActiveField: () => set({ activeFieldId: null, highlightBox: null }),

  // ─── Suggestion panel ────────────────────────────────────────────────────────
  suggestions: [],
  activeSuggestionFieldId: null,

  setSuggestions: (fieldId, suggestions) =>
    set({ suggestions, activeSuggestionFieldId: fieldId }),

  clearSuggestions: () =>
    set({ suggestions: [], activeSuggestionFieldId: null }),

  // ─── UI toggles ──────────────────────────────────────────────────────────────
  heatmapVisible: false,
  toggleHeatmap: () => set((s) => ({ heatmapVisible: !s.heatmapVisible })),

  darkMode: false,
  toggleDarkMode: () => set((s) => ({ darkMode: !s.darkMode })),
}));

export default useStore;
