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
import PDFViewer from './PDFViewer';
import SpatialPDFViewer from './SpatialPDFViewer';
import FieldsEditor from './FieldsEditor';
import OCRConfidenceHeatmap from './OCRConfidenceHeatmap';
import PerformanceDashboard from './PerformanceDashboard';
import LayoutAnalysisPanel from './LayoutAnalysisPanel';
import PositionContextDisplay from './PositionContextDisplay';
import {
  runOCRExtraction,
  runAIExtraction,
  getFields,
  updateField,
  getHeatmap,
  getPDFUrl,
  extractSpatial,
} from '../services/api';
import useSpatialContext from '../hooks/useSpatialContext';
import useLayoutAnalysis from '../hooks/useLayoutAnalysis';
import '../styles/extraction.css';
import '../styles/spatial.css';

const TABS = ['Fields', 'Heatmap', 'Performance', 'Spatial'];

function ExtractionPage({ document: doc, onReset }) {
  const [activeTab, setActiveTab] = useState('Fields');
  const [currentPage, setCurrentPage] = useState(1);
  const [highlightBox, setHighlightBox] = useState(null);

  // Extraction state
  const [fields, setFields] = useState([]);
  const [quality, setQuality] = useState(null);
  const [enginesUsed, setEnginesUsed] = useState([]);
  const [extractionTime, setExtractionTime] = useState(null);
  const [heatmapData, setHeatmapData] = useState(null);
  const [heatmapImage, setHeatmapImage] = useState(null);

  // Spatial state
  const [spatialWords, setSpatialWords] = useState([]);
  const [loadingSpatial, setLoadingSpatial] = useState(false);
  const [showWordBoxes, setShowWordBoxes] = useState(true);
  const [showGrid, setShowGrid] = useState(false);
  const [showZones, setShowZones] = useState(false);

  // Spatial context hooks
  const {
    contextData,
    loading: contextLoading,
    error: contextError,
    fetchContext,
    clearContext,
  } = useSpatialContext(doc?.documentId);

  const {
    layoutData,
    loading: layoutLoading,
    error: layoutError,
    fetchLayout,
  } = useLayoutAnalysis(doc?.documentId);

  // Loading / error
  const [loadingOCR, setLoadingOCR] = useState(false);
  const [loadingAI, setLoadingAI] = useState(false);
  const [loadingHeatmap, setLoadingHeatmap] = useState(false);
  const [loadingFields, setLoadingFields] = useState(false);
  const [error, setError] = useState('');

  const pdfUrl = doc ? getPDFUrl(doc.documentId) : null;

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
  }, [doc]);

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
    try {
      const result = await runOCRExtraction(doc.documentId);
      // Reload fields in case backend created them
      const updatedFields = await getFields(doc.documentId);
      if (Array.isArray(updatedFields)) setFields(updatedFields);
      setEnginesUsed(result.engines_used || []);
    } catch (err) {
      setError('OCR failed: ' + err.message);
    } finally {
      setLoadingOCR(false);
    }
  }, [doc]);

  const handleRunAI = useCallback(async () => {
    if (!doc) return;
    setLoadingAI(true);
    setError('');
    try {
      const result = await runAIExtraction(doc.documentId);
      if (result.fields) {
        setFields(result.fields);
      }
      if (result.quality) setQuality(result.quality);
      if (result.engines_available) setEnginesUsed(result.engines_available);
      if (result.extraction_time_seconds != null) setExtractionTime(result.extraction_time_seconds);
    } catch (err) {
      setError('AI extraction failed: ' + err.message);
    } finally {
      setLoadingAI(false);
    }
  }, [doc]);

  const handleFieldUpdate = useCallback(
    async (fieldId, newValue) => {
      try {
        const updated = await updateField(fieldId, newValue);
        setFields((prev) =>
          prev.map((f) => (f.id === updated.id ? updated : f))
        );
      } catch (err) {
        setError('Save failed: ' + err.message);
      }
    },
    []
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
  };

  // -----------------------------------------------------------------------
  // Spatial handlers
  // -----------------------------------------------------------------------

  const handleRunSpatial = useCallback(async () => {
    if (!doc) return;
    setLoadingSpatial(true);
    setError('');
    try {
      const result = await extractSpatial(doc.documentId, currentPage);
      setSpatialWords(result.words || []);
    } catch (err) {
      setError('Spatial extraction failed: ' + err.message);
    } finally {
      setLoadingSpatial(false);
    }
  }, [doc, currentPage]);

  const handleAnalyseLayout = useCallback(async () => {
    if (!doc) return;
    await fetchLayout(currentPage);
  }, [doc, currentPage, fetchLayout]);

  const handlePositionClick = useCallback(
    ({ x, y, page }) => {
      fetchContext(x, y, page, 30);
    },
    [fetchContext]
  );

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
          >
            {loadingOCR ? '⏳ Running OCR…' : '🔍 Run OCR'}
          </button>
          <button
            className="extraction-btn extraction-btn--ai"
            onClick={handleRunAI}
            disabled={loadingOCR || loadingAI}
          >
            {loadingAI ? '⏳ AI Extracting…' : '🤖 AI Extract (RAG)'}
          </button>
          <button className="extraction-btn extraction-btn--export" onClick={handleExportJSON}>
            ⬇ JSON
          </button>
          <button className="extraction-btn extraction-btn--export" onClick={handleExportCSV}>
            ⬇ CSV
          </button>
          {onReset && (
            <button className="extraction-btn extraction-btn--reset" onClick={onReset}>
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
        {/* Left: PDF viewer — spatial variant when on Spatial tab */}
        <div className="extraction-page__left">
          {activeTab === 'Spatial' ? (
            <SpatialPDFViewer
              pdfUrl={pdfUrl}
              onPageChange={setCurrentPage}
              highlightBox={highlightBox}
              words={spatialWords}
              layoutData={layoutData}
              onPositionClick={handlePositionClick}
              showWordBoxes={showWordBoxes}
              showGrid={showGrid}
              showZones={showZones}
            />
          ) : (
            <PDFViewer
              pdfUrl={pdfUrl}
              onPageChange={setCurrentPage}
              highlightBox={highlightBox}
            />
          )}
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
                {tab === 'Spatial' && `🗺 ${tab}`}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="extraction-page__tab-content" role="tabpanel">
            {activeTab === 'Fields' && (
              <FieldsEditor
                fields={fields}
                onFieldUpdate={handleFieldUpdate}
                onFieldHover={setHighlightBox}
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

            {activeTab === 'Spatial' && (
              <div className="spatial-tab">
                {/* Toolbar */}
                <div className="spatial-tab__toolbar">
                  <button
                    className="extraction-btn extraction-btn--ocr"
                    onClick={handleRunSpatial}
                    disabled={loadingSpatial}
                    title="Extract word positions and spatial features"
                  >
                    {loadingSpatial ? '⏳ Extracting…' : '🔍 Extract Spatial'}
                  </button>
                  <button
                    className="extraction-btn extraction-btn--ai"
                    onClick={handleAnalyseLayout}
                    disabled={layoutLoading}
                    title="Detect zones, columns, rows, and label-value pairs"
                  >
                    {layoutLoading ? '⏳ Analysing…' : '📐 Analyse Layout'}
                  </button>

                  <span className="spatial-tab__sep" />

                  {/* Overlay toggles */}
                  <label className="spatial-tab__toggle">
                    <input
                      type="checkbox"
                      checked={showWordBoxes}
                      onChange={(e) => setShowWordBoxes(e.target.checked)}
                    />
                    Word boxes
                  </label>
                  <label className="spatial-tab__toggle">
                    <input
                      type="checkbox"
                      checked={showGrid}
                      onChange={(e) => setShowGrid(e.target.checked)}
                    />
                    Grid
                  </label>
                  <label className="spatial-tab__toggle">
                    <input
                      type="checkbox"
                      checked={showZones}
                      onChange={(e) => setShowZones(e.target.checked)}
                    />
                    Zones
                  </label>
                  {spatialWords.length > 0 && (
                    <span className="spatial-tab__word-count">
                      {spatialWords.length} words
                    </span>
                  )}
                </div>

                {/* Two-column sub-layout: layout panel + context panel */}
                <div className="spatial-tab__panels">
                  <div className="spatial-tab__panel">
                    <LayoutAnalysisPanel
                      layoutData={layoutData}
                      loading={layoutLoading}
                    />
                    {layoutError && (
                      <p style={{ color: '#dc2626', fontSize: '0.85rem' }}>
                        ⚠️ {layoutError}
                      </p>
                    )}
                  </div>
                  <div className="spatial-tab__panel">
                    <PositionContextDisplay
                      contextData={contextData}
                      loading={contextLoading}
                      error={contextError}
                      onClose={clearContext}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ExtractionPage;
