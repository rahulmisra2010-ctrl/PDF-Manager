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
import toast from 'react-hot-toast';
import PDFViewer from './PDFViewer';
import FieldsEditor from './FieldsEditor';
import OCRConfidenceHeatmap from './OCRConfidenceHeatmap';
import PerformanceDashboard from './PerformanceDashboard';
import SuggestionPanel from './SuggestionPanel';
import useStore from '../services/store';
import { useFieldSync } from '../hooks/useFieldSync';
import {
  runOCRExtraction,
  runAIExtraction,
  getFields,
  updateField,
  getHeatmap,
  getPDFUrl,
} from '../services/api';
import '../styles/extraction.css';

const TABS = ['Fields', 'Heatmap', 'Performance'];

function ExtractionPage({ document: doc, onReset }) {
  const [activeTab, setActiveTab] = useState('Fields');
  const [quality, setQuality] = useState(null);
  const [enginesUsed, setEnginesUsed] = useState([]);
  const [extractionTime, setExtractionTime] = useState(null);
  const [heatmapData, setHeatmapData] = useState(null);
  const [heatmapImage, setHeatmapImage] = useState(null);

  // SuggestionPanel state
  const [suggestionField, setSuggestionField] = useState(null);
  const [suggestions, setSuggestions] = useState([]);

  // Loading / error
  const [loadingOCR, setLoadingOCR] = useState(false);
  const [loadingAI, setLoadingAI] = useState(false);
  const [loadingHeatmap, setLoadingHeatmap] = useState(false);
  const [loadingFields, setLoadingFields] = useState(false);
  const [error, setError] = useState('');

  // Zustand store for fields + undo/redo
  const {
    fields,
    setFields,
    updateField: storeUpdateField,
    syncServerField,
    undo,
    redo,
    past,
    future,
  } = useStore();

  // Bidirectional PDF ↔ editor sync
  const { highlightBox, currentPage, selectField, onPageChange } = useFieldSync(fields);

  const pdfUrl = doc ? getPDFUrl(doc.documentId) : null;

  // Set document ID in store
  useEffect(() => {
    if (doc) useStore.getState().setDocumentId(doc.documentId);
  }, [doc]);

  // Load fields from DB on mount / document change
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
      .catch((err) => setError(err.message))
      .finally(() => setLoadingHeatmap(false));
  }, [activeTab, doc, currentPage]);

  const handleRunOCR = useCallback(async () => {
    if (!doc) return;
    setLoadingOCR(true);
    setError('');
    const toastId = toast.loading('Running OCR extraction…');
    try {
      const result = await runOCRExtraction(doc.documentId);
      const updatedFields = await getFields(doc.documentId);
      if (Array.isArray(updatedFields)) setFields(updatedFields);
      setEnginesUsed(result.engines_used || []);
      toast.success(`OCR complete — ${updatedFields.length} fields extracted`, { id: toastId });
    } catch (err) {
      setError('OCR failed: ' + err.message);
      toast.error('OCR failed: ' + err.message, { id: toastId });
    } finally {
      setLoadingOCR(false);
    }
  }, [doc, setFields]);

  const handleRunAI = useCallback(async () => {
    if (!doc) return;
    setLoadingAI(true);
    setError('');
    const toastId = toast.loading('Running AI + RAG extraction…');
    try {
      const result = await runAIExtraction(doc.documentId);
      if (result.fields) {
        setFields(result.fields);
      }
      if (result.quality) setQuality(result.quality);
      if (result.engines_available) setEnginesUsed(result.engines_available);
      if (result.extraction_time_seconds != null) setExtractionTime(result.extraction_time_seconds);
      toast.success('AI extraction complete', { id: toastId });
    } catch (err) {
      setError('AI extraction failed: ' + err.message);
      toast.error('AI extraction failed: ' + err.message, { id: toastId });
    } finally {
      setLoadingAI(false);
    }
  }, [doc, setFields]);

  const handleFieldUpdate = useCallback(
    async (fieldId, newValue) => {
      // Optimistic update via store (supports undo)
      storeUpdateField(fieldId, newValue);
      try {
        const updated = await updateField(fieldId, newValue);
        // Sync server response back into store using the store's action
        syncServerField(updated);
        toast.success('Field saved');
      } catch (err) {
        // Roll back optimistic update by re-fetching
        setError('Save failed: ' + err.message);
        toast.error('Save failed: ' + err.message);
        const data = await getFields(doc.documentId).catch(() => null);
        if (Array.isArray(data)) setFields(data);
      }
    },
    [storeUpdateField, syncServerField, doc, setFields]
  );

  // Undo/Redo keyboard shortcuts
  const handleUndo = useCallback(() => {
    undo();
    toast('↩ Undo', { icon: '↩' });
  }, [undo]);

  const handleRedo = useCallback(() => {
    redo();
    toast('↪ Redo', { icon: '↪' });
  }, [redo]);

  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      }
      if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        handleRedo();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleUndo, handleRedo]);

  // Show suggestion panel for a field (if it has ai_suggestions)
  const handleShowSuggestions = useCallback((field) => {
    const sug = field?.ai_suggestions || [];
    setSuggestions(sug);
    setSuggestionField(field);
  }, []);

  const handleAcceptSuggestion = useCallback(
    async (fieldId, value) => {
      await handleFieldUpdate(fieldId, value);
      setSuggestionField(null);
    },
    [handleFieldUpdate]
  );

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

  return (
    <div className="extraction-page">
      {/* Top bar */}
      <div className="extraction-page__topbar">
        <div className="extraction-page__doc-info">
          <span className="extraction-page__doc-icon">📄</span>
          <span className="extraction-page__doc-name">{doc?.filename}</span>
        </div>
        <div className="extraction-page__actions">
          <button
            className="extraction-btn extraction-btn--ocr"
            onClick={handleRunOCR}
            disabled={loadingOCR || loadingAI}
            aria-label="Run OCR extraction"
          >
            {loadingOCR ? '⏳ Running OCR…' : '🔍 Run OCR'}
          </button>
          <button
            className="extraction-btn extraction-btn--ai"
            onClick={handleRunAI}
            disabled={loadingOCR || loadingAI}
            aria-label="Run AI RAG extraction"
          >
            {loadingAI ? '⏳ AI Extracting…' : '🤖 AI Extract (RAG)'}
          </button>
          <button
            className="extraction-btn extraction-btn--undo"
            onClick={handleUndo}
            disabled={!past.length}
            aria-label="Undo last field edit"
            title="Undo (Ctrl+Z)"
          >
            ↩ Undo
          </button>
          <button
            className="extraction-btn extraction-btn--redo"
            onClick={handleRedo}
            disabled={!future.length}
            aria-label="Redo field edit"
            title="Redo (Ctrl+Y)"
          >
            ↪ Redo
          </button>
          <button className="extraction-btn extraction-btn--export" onClick={handleExportJSON} aria-label="Export as JSON">
            ⬇ JSON
          </button>
          <button className="extraction-btn extraction-btn--export" onClick={handleExportCSV} aria-label="Export as CSV">
            ⬇ CSV
          </button>
          {onReset && (
            <button className="extraction-btn extraction-btn--reset" onClick={onReset} aria-label="Upload new PDF">
              ↩ New PDF
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="extraction-page__error" role="alert">
          ⚠️ {error}
          <button onClick={() => setError('')} aria-label="Dismiss error">✕</button>
        </div>
      )}

      {/* Split layout */}
      <div className="extraction-page__split">
        {/* Left: PDF viewer */}
        <div className="extraction-page__left">
          <PDFViewer
            pdfUrl={pdfUrl}
            onPageChange={onPageChange}
            highlightBox={highlightBox}
          />
        </div>

        {/* Right: Tabbed panels */}
        <div className="extraction-page__right">
          {/* Tabs */}
          <div className="extraction-page__tabs" role="tablist">
            {TABS.map((tab) => (
              <button
                key={tab}
                role="tab"
                aria-selected={activeTab === tab}
                className={`extraction-page__tab ${activeTab === tab ? 'active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab === 'Fields' && `📋 ${tab}`}
                {tab === 'Heatmap' && `🔥 ${tab}`}
                {tab === 'Performance' && `📊 ${tab}`}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="extraction-page__tab-content" role="tabpanel">
            {activeTab === 'Fields' && (
              <FieldsEditor
                fields={fields}
                onFieldUpdate={handleFieldUpdate}
                onFieldHover={(field) => selectField(field || null)}
                onFieldSelect={selectField}
                onShowSuggestions={handleShowSuggestions}
                loading={loadingFields}
              />
            )}

            {activeTab === 'Heatmap' && (
              loadingHeatmap ? (
                <div className="extraction-page__loading">Loading heatmap…</div>
              ) : (
                <OCRConfidenceHeatmap
                  heatmapData={heatmapData}
                  imageData={heatmapImage}
                  pageNumber={currentPage}
                />
              )
            )}

            {activeTab === 'Performance' && (
              <PerformanceDashboard
                quality={quality}
                enginesUsed={enginesUsed}
                extractionTime={extractionTime}
                fields={fields}
              />
            )}
          </div>
        </div>
      </div>

      {/* Suggestion panel (slides from right) */}
      <SuggestionPanel
        field={suggestionField}
        suggestions={suggestions}
        onAccept={handleAcceptSuggestion}
        onDismiss={() => setSuggestionField(null)}
      />
    </div>
  );
}

export default ExtractionPage;

