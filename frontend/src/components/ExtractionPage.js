/**
 * ExtractionPage.js — Master component orchestrating all sub-components.
 *
 * Layout:
 *   Left panel  — PDFViewer (react-pdf) with zoom, nav, word hover overlays
 *   Right panel — Tabbed panel:
 *     Tab 1: FieldsEditor (editable table)
 *     Tab 2: ConfidenceHeatmap (word-level confidence)
 *     Tab 3: PerformanceDashboard
 *   Optional: SuggestionPanel (slides from right when active)
 *
 * Features:
 * - Real-time bidirectional PDF ↔ editor synchronization via useFieldSync
 * - react-hot-toast notifications for success/error
 * - Framer Motion transitions between tabs
 * - Responsive: split on desktop, stacked on mobile
 * - Zustand store for fields undo/redo
 *
 * Props:
 *   document      {object}  { documentId, filename }
 *   onReset       {func}    Called when user clicks "Upload New PDF"
 */

import React, { useState, useCallback, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Toaster, toast } from 'react-hot-toast';
import PDFViewer from './PDFViewer';
import FieldsEditor from './FieldsEditor';
import ConfidenceHeatmap from './ConfidenceHeatmap';
import OCRConfidenceHeatmap from './OCRConfidenceHeatmap';
import PerformanceDashboard from './PerformanceDashboard';
import SuggestionPanel from './SuggestionPanel';
import useFieldSync from '../hooks/useFieldSync';
import useStore from '../services/store';
import {
  runOCRExtraction,
  runAIExtraction,
  getFields,
  updateField,
  getHeatmap,
  getPDFUrl,
} from '../services/api';
import { fadeVariants } from '../hooks/useAnimations';
import styles from './styles/ExtractionPage.module.css';

const TABS = ['Fields', 'Heatmap', 'Performance'];

function ExtractionPage({ document: doc, onReset }) {
  const [activeTab, setActiveTab] = useState('Fields');
  const [currentPage, setCurrentPage] = useState(1);
  const [wordMarkers, setWordMarkers] = useState([]);

  // Extraction state
  const [quality, setQuality] = useState(null);
  const [enginesUsed, setEnginesUsed] = useState([]);
  const [extractionTime, setExtractionTime] = useState(null);
  const [heatmapData, setHeatmapData] = useState(null);
  const [heatmapImage, setHeatmapImage] = useState(null);

  // Loading / error
  const [loadingOCR, setLoadingOCR] = useState(false);
  const [loadingAI, setLoadingAI] = useState(false);
  const [loadingHeatmap, setLoadingHeatmap] = useState(false);
  const [loadingFields, setLoadingFields] = useState(false);
  const [error, setError] = useState('');

  // Suggestion panel
  const [suggestionField, setSuggestionField] = useState(null);
  const [suggestions, setSuggestions] = useState([]);

  // Zustand store for fields with undo/redo
  const { fields, setFields, updateFieldValue } = useStore();

  // Bidirectional PDF ↔ editor sync
  const { highlightBox, activeFieldId, focusWord, setHighlightBox } =
    useFieldSync();

  const pdfUrl = doc ? getPDFUrl(doc.documentId) : null;

  // ─── Load fields from DB on mount / document change ──────────────────────
  useEffect(() => {
    if (!doc) return;
    setLoadingFields(true);
    getFields(doc.documentId)
      .then((data) => {
        if (Array.isArray(data)) setFields(data);
      })
      .catch(() => {})
      .finally(() => setLoadingFields(false));
  }, [doc, setFields]);

  // ─── Load heatmap when Heatmap tab active or page changes ─────────────────
  useEffect(() => {
    if (activeTab !== 'Heatmap' || !doc) return;
    setLoadingHeatmap(true);
    getHeatmap(doc.documentId, currentPage, true)
      .then((data) => {
        setHeatmapImage(data.image || null);
        const { image, ...rest } = data;
        setHeatmapData(rest);
        setWordMarkers(rest.word_markers || []);
      })
      .catch((err) => {
        setError(err.message);
        toast.error('Failed to load heatmap: ' + err.message);
      })
      .finally(() => setLoadingHeatmap(false));
  }, [activeTab, doc, currentPage]);

  // ─── Run OCR ──────────────────────────────────────────────────────────────
  const handleRunOCR = useCallback(async () => {
    if (!doc) return;
    setLoadingOCR(true);
    setError('');
    const toastId = toast.loading('Running OCR…');
    try {
      const result = await runOCRExtraction(doc.documentId);
      const updatedFields = await getFields(doc.documentId);
      if (Array.isArray(updatedFields)) setFields(updatedFields);
      setEnginesUsed(result.engines_used || []);
      toast.success(`OCR complete (${(result.engines_used || []).join(', ')})`, { id: toastId });
    } catch (err) {
      const msg = 'OCR failed: ' + err.message;
      setError(msg);
      toast.error(msg, { id: toastId });
    } finally {
      setLoadingOCR(false);
    }
  }, [doc, setFields]);

  // ─── Run AI extraction ─────────────────────────────────────────────────────
  const handleRunAI = useCallback(async () => {
    if (!doc) return;
    setLoadingAI(true);
    setError('');
    const toastId = toast.loading('Running AI extraction…');
    try {
      const result = await runAIExtraction(doc.documentId);
      if (result.fields) setFields(result.fields);
      if (result.quality) setQuality(result.quality);
      if (result.engines_available) setEnginesUsed(result.engines_available);
      if (result.extraction_time_seconds != null)
        setExtractionTime(result.extraction_time_seconds);
      toast.success('AI extraction complete', { id: toastId });
    } catch (err) {
      const msg = 'AI extraction failed: ' + err.message;
      setError(msg);
      toast.error(msg, { id: toastId });
    } finally {
      setLoadingAI(false);
    }
  }, [doc, setFields]);

  // ─── Field update (saves to API + updates Zustand store) ──────────────────
  const handleFieldUpdate = useCallback(
    async (fieldId, newValue) => {
      try {
        const updated = await updateField(fieldId, newValue);
        updateFieldValue(fieldId, updated.value ?? newValue);
        return updated;
      } catch (err) {
        const msg = 'Save failed: ' + err.message;
        setError(msg);
        toast.error(msg);
        throw err;
      }
    },
    [updateFieldValue]
  );

  // ─── Suggest: open suggestion panel for a field ────────────────────────────
  const handleSuggest = useCallback((field) => {
    setSuggestionField(field);
    // TODO: Replace with actual API call to GET /api/v1/fields/:id/suggestions
    //       when the backend AI suggestion endpoint is implemented.
    // Build candidate suggestions from fields with the same type already extracted.
    const mockSuggestions = (fields || [])
      .filter(
        (f) =>
          f.field_type === field.field_type &&
          f.value &&
          f.value !== field.value &&
          f.id !== field.id
      )
      .map((f) => ({ value: f.value, score: f.confidence || 0.7, source: f.source }))
      .slice(0, 5);
    setSuggestions(mockSuggestions);
  }, [fields]);

  // ─── Apply suggestion ──────────────────────────────────────────────────────
  const handleApplySuggestion = useCallback(
    async (fieldId, newValue) => {
      await handleFieldUpdate(fieldId, newValue);
    },
    [handleFieldUpdate]
  );

  // ─── Exports ───────────────────────────────────────────────────────────────
  const handleExportJSON = () => {
    const blob = new Blob([JSON.stringify(fields, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = window.document.createElement('a');
    a.href = url;
    a.download = `${doc?.filename || 'export'}_fields.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('JSON exported');
  };

  const handleExportCSV = () => {
    if (!fields.length) return;
    const header = 'field_name,value,confidence,field_type,source\n';
    const rows = fields
      .map(
        (f) =>
          `"${f.field_name}","${f.value || ''}",${f.confidence || 0},"${f.field_type || ''}","${f.source || ''}"`
      )
      .join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = window.document.createElement('a');
    a.href = url;
    a.download = `${doc?.filename || 'export'}_fields.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('CSV exported');
  };

  const isLoading = loadingOCR || loadingAI;

  return (
    <div className={styles.page}>
      {/* react-hot-toast container */}
      <Toaster
        position="top-right"
        toastOptions={{ duration: 3000, style: { fontSize: 13 } }}
      />

      {/* ── Top bar ── */}
      <div className={styles.topbar}>
        <div className={styles.docInfo}>
          <span aria-hidden>📄</span>
          <span className={styles.docName} title={doc?.filename}>
            {doc?.filename}
          </span>
        </div>
        <div className={styles.actions}>
          <button
            className={`${styles.btn} ${styles.btnOcr}`}
            onClick={handleRunOCR}
            disabled={isLoading}
            aria-label="Run OCR extraction"
          >
            {loadingOCR ? '⏳ OCR…' : '🔍 Run OCR'}
          </button>
          <button
            className={`${styles.btn} ${styles.btnAi}`}
            onClick={handleRunAI}
            disabled={isLoading}
            aria-label="Run AI extraction with RAG"
          >
            {loadingAI ? '⏳ AI…' : '🤖 AI Extract (RAG)'}
          </button>
          <button
            className={`${styles.btn} ${styles.btnExport}`}
            onClick={handleExportJSON}
            aria-label="Export as JSON"
          >
            ⬇ JSON
          </button>
          <button
            className={`${styles.btn} ${styles.btnExport}`}
            onClick={handleExportCSV}
            aria-label="Export as CSV"
          >
            ⬇ CSV
          </button>
          {onReset && (
            <button
              className={`${styles.btn} ${styles.btnReset}`}
              onClick={onReset}
              aria-label="Upload new PDF"
            >
              ↩ New PDF
            </button>
          )}
        </div>
      </div>

      {/* ── Error bar ── */}
      <AnimatePresence>
        {error && (
          <motion.div
            className={styles.errorBar}
            role="alert"
            aria-live="assertive"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            ⚠️ {error}
            <button
              className={styles.errorDismiss}
              onClick={() => setError('')}
              aria-label="Dismiss error"
            >
              ✕
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Split layout ── */}
      <div className={styles.split}>
        {/* Left: PDF viewer */}
        <div className={styles.leftPanel}>
          <PDFViewer
            pdfUrl={pdfUrl}
            onPageChange={setCurrentPage}
            highlightBox={highlightBox}
            wordMarkers={activeTab === 'Heatmap' ? wordMarkers : []}
            onWordHover={focusWord}
          />
        </div>

        {/* Right: Tabbed panels */}
        <div className={styles.rightPanel}>
          {/* Tabs */}
          <div className={styles.tabs} role="tablist" aria-label="Content tabs">
            {TABS.map((tab) => (
              <button
                key={tab}
                role="tab"
                aria-selected={activeTab === tab}
                className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab === 'Fields' && '📋 Fields'}
                {tab === 'Heatmap' && '🔥 Heatmap'}
                {tab === 'Performance' && '📊 Performance'}
              </button>
            ))}
          </div>

          {/* Tab content + optional suggestion panel side by side */}
          <div className={styles.withSuggestions}>
            <div
              className={
                suggestionField ? styles.tabContentWithPanel : styles.tabContent
              }
              role="tabpanel"
            >
              <AnimatePresence mode="wait">
                {activeTab === 'Fields' && (
                  <motion.div
                    key="fields"
                    variants={fadeVariants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                    style={{ height: '100%' }}
                  >
                    <FieldsEditor
                      fields={fields}
                      onFieldUpdate={handleFieldUpdate}
                      onFieldHover={setHighlightBox}
                      onSuggest={handleSuggest}
                      activeFieldId={activeFieldId}
                      loading={loadingFields}
                    />
                  </motion.div>
                )}

                {activeTab === 'Heatmap' && (
                  <motion.div
                    key="heatmap"
                    variants={fadeVariants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                    style={{ height: '100%' }}
                  >
                    {loadingHeatmap ? (
                      <div className={styles.loadingOverlay} aria-live="polite">
                        ⏳ Loading heatmap…
                      </div>
                    ) : heatmapData ? (
                      <ConfidenceHeatmap
                        heatmapData={heatmapData}
                        imageData={heatmapImage}
                        pageNumber={currentPage}
                        onWordHover={focusWord}
                      />
                    ) : (
                      <OCRConfidenceHeatmap
                        heatmapData={heatmapData}
                        imageData={heatmapImage}
                        pageNumber={currentPage}
                      />
                    )}
                  </motion.div>
                )}

                {activeTab === 'Performance' && (
                  <motion.div
                    key="performance"
                    variants={fadeVariants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                    style={{ height: '100%' }}
                  >
                    <PerformanceDashboard
                      quality={quality}
                      enginesUsed={enginesUsed}
                      extractionTime={extractionTime}
                      fields={fields}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Suggestion panel */}
            <AnimatePresence>
              {suggestionField && (
                <SuggestionPanel
                  key="suggestions"
                  fieldId={suggestionField.id}
                  fieldName={suggestionField.field_name}
                  currentValue={suggestionField.value}
                  suggestions={suggestions}
                  onApply={handleApplySuggestion}
                  onClose={() => setSuggestionField(null)}
                />
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ExtractionPage;

