/**
 * ExtractionPage.js — Full split-layout extraction page.
 *
 * Layout:
 *   Left panel  — PDF viewer (react-pdf) with zoom & page nav
 *   Right panel — Tabbed panel:
 *     Tab 1: Editable Fields (FieldsEditor)
 *     Tab 2: OCR Confidence Heatmap
 *     Tab 3: Performance Dashboard
 *
 * Props:
 *   document      {object}  { documentId, filename }
 *   onReset       {func}    Called when user clicks "Upload New PDF"
 */

import React, { useState, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import toast, { Toaster } from 'react-hot-toast';
import PDFViewer from './PDFViewer';
import FieldsEditor from './FieldsEditor';
import OCRConfidenceHeatmap from './OCRConfidenceHeatmap';
import PerformanceDashboard from './PerformanceDashboard';
import SuggestionPanel from './SuggestionPanel';
import {
  runOCRExtraction,
  runAIExtraction,
  getFields,
  updateField,
  getHeatmap,
  getPDFUrl,
} from '../services/api';
import { useStore } from '../services/store';
import { fadeVariants } from '../hooks/useAnimations';
import styles from './styles/ExtractionPage.module.css';

const TABS = ['Fields', 'Heatmap', 'Performance'];

function ExtractionPage({ document: doc, onReset }) {
  const [activeTab, setActiveTab] = useState('Fields');
  const [currentPage, setCurrentPage] = useState(1);
  const [highlightBox, setHighlightBox] = useState(null);
  const [quality, setQuality] = useState(null);
  const [enginesUsed, setEnginesUsed] = useState([]);
  const [extractionTime, setExtractionTime] = useState(null);
  const [heatmapData, setHeatmapData] = useState(null);
  const [heatmapImage, setHeatmapImage] = useState(null);

  // Loading
  const [loadingOCR, setLoadingOCR] = useState(false);
  const [loadingAI, setLoadingAI] = useState(false);
  const [loadingHeatmap, setLoadingHeatmap] = useState(false);
  const [loadingFields, setLoadingFields] = useState(false);

  // Zustand store
  const fields = useStore((s) => s.fields);
  const setFields = useStore((s) => s.setFields);
  const storeUpdateField = useStore((s) => s.updateField);
  const undo = useStore((s) => s.undo);
  const redo = useStore((s) => s.redo);
  const canUndo = useStore((s) => s.canUndo);
  const canRedo = useStore((s) => s.canRedo);
  const suggestionPanelOpen = useStore((s) => s.suggestionPanelOpen);
  const suggestionTargetFieldId = useStore((s) => s.suggestionTargetFieldId);
  const closeSuggestionPanel = useStore((s) => s.closeSuggestionPanel);
  const applySuggestion = useStore((s) => s.applySuggestion);
  const undoLastSuggestion = useStore((s) => s.undoLastSuggestion);
  const suggestionHistory = useStore((s) => s.suggestionHistory);

  const pdfUrl = doc ? getPDFUrl(doc.documentId) : null;

  // Load fields from DB on mount / document change
  useEffect(() => {
    if (!doc) return;
    setLoadingFields(true);
    getFields(doc.documentId)
      .then((data) => { if (Array.isArray(data)) setFields(data); })
      .catch(() => {})
      .finally(() => setLoadingFields(false));
  }, [doc, setFields]);

  // Load heatmap when tab switches to Heatmap or page changes
  useEffect(() => {
    if (activeTab !== 'Heatmap' || !doc) return;
    setLoadingHeatmap(true);
    getHeatmap(doc.documentId, currentPage, true)
      .then((data) => {
        setHeatmapImage(data.image || null);
        const { image, ...rest } = data;
        setHeatmapData(rest);
      })
      .catch((err) => toast.error(err.message))
      .finally(() => setLoadingHeatmap(false));
  }, [activeTab, doc, currentPage]);

  const handleRunOCR = useCallback(async () => {
    if (!doc) return;
    setLoadingOCR(true);
    try {
      const result = await runOCRExtraction(doc.documentId);
      const updatedFields = await getFields(doc.documentId);
      if (Array.isArray(updatedFields)) setFields(updatedFields);
      setEnginesUsed(result.engines_used || []);
      toast.success('OCR extraction complete');
    } catch (err) {
      toast.error('OCR failed: ' + err.message);
    } finally {
      setLoadingOCR(false);
    }
  }, [doc, setFields]);

  const handleRunAI = useCallback(async () => {
    if (!doc) return;
    setLoadingAI(true);
    try {
      const result = await runAIExtraction(doc.documentId);
      if (result.fields) setFields(result.fields);
      if (result.quality) setQuality(result.quality);
      if (result.engines_available) setEnginesUsed(result.engines_available);
      if (result.extraction_time_seconds != null) setExtractionTime(result.extraction_time_seconds);
      toast.success('AI extraction complete');
    } catch (err) {
      toast.error('AI extraction failed: ' + err.message);
    } finally {
      setLoadingAI(false);
    }
  }, [doc, setFields]);

  const handleFieldUpdate = useCallback(
    async (fieldId, newValue) => {
      try {
        const updated = await updateField(fieldId, newValue);
        storeUpdateField(fieldId, updated.value ?? newValue);
        toast.success('Field saved');
      } catch (err) {
        toast.error('Save failed: ' + err.message);
      }
    },
    [storeUpdateField]
  );

  const handleApplySuggestion = useCallback(
    async (fieldId, value) => {
      applySuggestion(fieldId, value);
      try {
        await updateField(fieldId, value);
        toast.success('Suggestion applied');
      } catch (err) {
        toast.error('Apply failed: ' + err.message);
      }
    },
    [applySuggestion]
  );

  const handleExportJSON = () => {
    const blob = new Blob([JSON.stringify(fields, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = window.document.createElement('a');
    a.href = url;
    a.download = `${doc?.filename || 'export'}_fields.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportCSV = () => {
    if (!fields.length) return;
    const header = 'field_name,value,confidence,field_type,source\n';
    const rows = fields
      .map((f) => `"${f.field_name}","${f.value || ''}",${f.confidence || 0},"${f.field_type || ''}","${f.source || ''}"`)
      .join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = window.document.createElement('a');
    a.href = url;
    a.download = `${doc?.filename || 'export'}_fields.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Suggestion panel target field
  const suggestionTargetField = fields.find((f) => f.id === suggestionTargetFieldId);
  // Suggestions are populated here from the field's existing value for demonstration.
  // In production, these would come from a dedicated AI suggestions API endpoint.
  const suggestions = suggestionTargetField
    ? [
        { value: suggestionTargetField.value || '', confidence: suggestionTargetField.confidence || 0, source: suggestionTargetField.source || 'rule' },
      ].filter((s) => s.value)
    : [];

  return (
    <div className={styles.page}>
      <Toaster position="top-right" />

      {/* Top bar */}
      <div className={styles.topbar}>
        <div className={styles.docInfo}>
          <span className={styles.docIcon}>📄</span>
          <span className={styles.docName}>{doc?.filename}</span>
        </div>
        <div className={styles.actions}>
          <button
            className={`${styles.btn} ${styles.btnOcr}`}
            onClick={handleRunOCR}
            disabled={loadingOCR || loadingAI}
          >
            {loadingOCR ? '⏳ Running OCR…' : '🔍 Run OCR'}
          </button>
          <button
            className={`${styles.btn} ${styles.btnAi}`}
            onClick={handleRunAI}
            disabled={loadingOCR || loadingAI}
          >
            {loadingAI ? '⏳ AI Extracting…' : '🤖 AI Extract (RAG)'}
          </button>
          <button className={`${styles.btn} ${styles.btnExport}`} onClick={handleExportJSON}>
            ⬇ JSON
          </button>
          <button className={`${styles.btn} ${styles.btnExport}`} onClick={handleExportCSV}>
            ⬇ CSV
          </button>
          {onReset && (
            <button className={`${styles.btn} ${styles.btnReset}`} onClick={onReset}>
              ↩ New PDF
            </button>
          )}
        </div>
      </div>

      {/* Split layout */}
      <div className={styles.split}>
        {/* Left: PDF viewer */}
        <div className={styles.leftPanel}>
          <PDFViewer
            pdfUrl={pdfUrl}
            onPageChange={setCurrentPage}
            highlightBox={highlightBox}
          />
        </div>

        {/* Right: Tabbed panels */}
        <div className={styles.rightPanel}>
          {/* Tabs */}
          <div className={styles.tabs} role="tablist">
            {TABS.map((tab) => (
              <button
                key={tab}
                role="tab"
                aria-selected={activeTab === tab}
                className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab === 'Fields' && `📋 ${tab}`}
                {tab === 'Heatmap' && `🔥 ${tab}`}
                {tab === 'Performance' && `📊 ${tab}`}
              </button>
            ))}
          </div>

          {/* Tab content with Framer Motion transitions */}
          <div className={styles.tabContent} role="tabpanel">
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
                    loading={loadingFields}
                    canUndo={canUndo()}
                    canRedo={canRedo()}
                    onUndo={undo}
                    onRedo={redo}
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
                    <div className={styles.loading}>Loading heatmap…</div>
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

          {/* Suggestion panel (slides in from right within right panel) */}
          {suggestionPanelOpen && suggestionTargetField && (
            <SuggestionPanel
              fieldId={suggestionTargetFieldId}
              fieldName={suggestionTargetField.field_name}
              suggestions={suggestions}
              onApply={handleApplySuggestion}
              onUndoLast={undoLastSuggestion}
              onClose={closeSuggestionPanel}
              canUndo={suggestionHistory.length > 0}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default ExtractionPage;
