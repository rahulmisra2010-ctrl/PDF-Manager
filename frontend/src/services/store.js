/**
 * store.js — Zustand global state for PDF Manager.
 *
 * State:
 *   fields        {Array}   Current extracted fields
 *   past          {Array}   History stack for undo (each entry is a fields array)
 *   future        {Array}   Future stack for redo
 *   documentId    {*}       Currently loaded document ID
 *   isLoading     {boolean} Global loading flag
 *   error         {string}  Global error message
 *
 * Actions:
 *   setFields(fields)              - Replace all fields (clears history)
 *   updateField(id, value)         - Update one field, push to undo history
 *   batchUpdateFields(updates)     - Update multiple fields, single history entry
 *   undo()                         - Revert to previous state
 *   redo()                         - Reapply next state
 *   setDocumentId(id)              - Set active document
 *   setLoading(bool)               - Set loading state
 *   setError(msg)                  - Set error message
 *   clearError()                   - Clear error message
 */

import { create } from 'zustand';

const MAX_HISTORY = 50;

const useStore = create((set, get) => ({
  // ── State ────────────────────────────────────────────────────────────────
  fields: [],
  past: [],
  future: [],
  documentId: null,
  isLoading: false,
  error: '',

  // ── Field actions ────────────────────────────────────────────────────────

  /** Replace all fields and reset undo/redo history */
  setFields: (fields) =>
    set({ fields, past: [], future: [] }),

  /** Update a single field value; saves current state to undo history */
  updateField: (id, value) => {
    const { fields, past } = get();
    const newFields = fields.map((f) =>
      f.id === id ? { ...f, value, is_edited: true } : f
    );
    const newPast = [...past, fields].slice(-MAX_HISTORY);
    set({ fields: newFields, past: newPast, future: [] });
  },

  /** Update multiple fields at once; single undo history entry */
  batchUpdateFields: (updates) => {
    const { fields, past } = get();
    const updateMap = new Map(updates.map((u) => [u.id, u.value]));
    const newFields = fields.map((f) =>
      updateMap.has(f.id) ? { ...f, value: updateMap.get(f.id), is_edited: true } : f
    );
    const newPast = [...past, fields].slice(-MAX_HISTORY);
    set({ fields: newFields, past: newPast, future: [] });
  },

  // ── Undo / Redo ──────────────────────────────────────────────────────────

  undo: () => {
    const { past, fields, future } = get();
    if (!past.length) return;
    const previous = past[past.length - 1];
    const newPast = past.slice(0, -1);
    const newFuture = [fields, ...future].slice(0, MAX_HISTORY);
    set({ fields: previous, past: newPast, future: newFuture });
  },

  redo: () => {
    const { past, fields, future } = get();
    if (!future.length) return;
    const next = future[0];
    const newFuture = future.slice(1);
    const newPast = [...past, fields].slice(-MAX_HISTORY);
    set({ fields: next, past: newPast, future: newFuture });
  },

  // ── Document ─────────────────────────────────────────────────────────────

  setDocumentId: (id) => set({ documentId: id }),

  /** Sync a field from server response back into the store */
  syncServerField: (updatedField) =>
    set((state) => ({
      fields: state.fields.map((f) => (f.id === updatedField.id ? updatedField : f)),
    })),

  // ── UI state ─────────────────────────────────────────────────────────────

  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  clearError: () => set({ error: '' }),
}));

export default useStore;
