/**
 * PDFViewer.js — Enhanced PDF viewer using react-pdf.
 *
 * Features:
 * - Page navigation (prev/next + direct input)
 * - Zoom in/out (50% – 300%)
 * - Dark theme
 * - Confidence indicator overlays via ConfidenceHeatmap component
 * - Smooth highlight transitions
 * - Pixel-level word hover detection via usePixelHover hook
 * - CSS Modules for styling
 *
 * Props:
 *   pdfUrl       {string}  URL of the PDF to display
 *   onPageChange {func}    Called with (pageNumber) when page changes
 *   highlightBox {object}  Optional { x, y, width, height } in PDF coords to highlight
 */

import React, { useState, useCallback } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/esm/Page/AnnotationLayer.css';
import 'react-pdf/dist/esm/Page/TextLayer.css';
import { motion } from 'framer-motion';
import ConfidenceHeatmap from './ConfidenceHeatmap';
import usePixelHover from '../hooks/usePixelHover';
import { useStore } from '../services/store';
import styles from './styles/PDFViewer.module.css';

// Use CDN worker
pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;

const ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0];

function PDFViewer({ pdfUrl, onPageChange, highlightBox }) {
  const [numPages, setNumPages] = useState(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1.25);
  const [loadError, setLoadError] = useState(null);

  const heatmapVisible = useStore((s) => s.heatmapVisible);
  const toggleHeatmap = useStore((s) => s.toggleHeatmap);
  const setHoveredWordId = useStore((s) => s.setHoveredWordId);

  // Pixel hover detection (no word markers by default; populated when OCR data is available)
  const { hoveredMarker, handleMouseMove, handleMouseLeave: handleMarkerLeave } = usePixelHover([], zoom);

  const onDocumentLoadSuccess = useCallback(({ numPages: n }) => {
    setNumPages(n);
    setPageNumber(1);
    setLoadError(null);
  }, []);

  const onDocumentLoadError = useCallback((err) => {
    setLoadError(err.message || 'Failed to load PDF');
  }, []);

  const goToPrev = () => {
    const next = Math.max(1, pageNumber - 1);
    setPageNumber(next);
    onPageChange && onPageChange(next);
  };

  const goToNext = () => {
    const next = Math.min(numPages || 1, pageNumber + 1);
    setPageNumber(next);
    onPageChange && onPageChange(next);
  };

  const handlePageInput = (e) => {
    const v = parseInt(e.target.value, 10);
    if (!isNaN(v) && v >= 1 && v <= (numPages || 1)) {
      setPageNumber(v);
      onPageChange && onPageChange(v);
    }
  };

  const zoomIn = () => {
    const idx = ZOOM_STEPS.indexOf(zoom);
    if (idx < ZOOM_STEPS.length - 1) setZoom(ZOOM_STEPS[idx + 1]);
  };

  const zoomOut = () => {
    const idx = ZOOM_STEPS.indexOf(zoom);
    if (idx > 0) setZoom(ZOOM_STEPS[idx - 1]);
  };

  const handleMouseMoveWrapper = (e) => {
    handleMouseMove(e);
    if (hoveredMarker) {
      setHoveredWordId(hoveredMarker.id);
    } else {
      setHoveredWordId(null);
    }
  };

  if (!pdfUrl) {
    return (
      <div className={`${styles.viewer} ${styles.viewerEmpty}`}>
        <p>No PDF loaded.</p>
      </div>
    );
  }

  return (
    <div className={styles.viewer}>
      {/* Toolbar */}
      <div className={styles.toolbar}>
        <button
          className={styles.toolbarBtn}
          onClick={goToPrev}
          disabled={pageNumber <= 1}
          aria-label="Previous page"
        >
          ‹
        </button>
        <input
          type="number"
          className={styles.pageInput}
          value={pageNumber}
          min={1}
          max={numPages || 1}
          onChange={handlePageInput}
          aria-label="Page number"
        />
        <span className={styles.pageInfo}>/ {numPages || '?'}</span>
        <button
          className={styles.toolbarBtn}
          onClick={goToNext}
          disabled={pageNumber >= (numPages || 1)}
          aria-label="Next page"
        >
          ›
        </button>

        <span className={styles.toolbarSep} />

        <button className={styles.toolbarBtn} onClick={zoomOut} aria-label="Zoom out">−</button>
        <span className={styles.zoomLabel}>{Math.round(zoom * 100)}%</span>
        <button className={styles.toolbarBtn} onClick={zoomIn} aria-label="Zoom in">+</button>

        <span className={styles.toolbarSep} />

        <button
          className={styles.toolbarBtn}
          onClick={toggleHeatmap}
          aria-pressed={heatmapVisible}
          title="Toggle confidence heatmap"
        >
          🔥
        </button>
      </div>

      {/* PDF Canvas */}
      <div className={styles.canvasArea}>
        {loadError ? (
          <div className={styles.error}>
            <p>⚠️ Could not load PDF: {loadError}</p>
          </div>
        ) : (
          <Document
            file={pdfUrl}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={<div className={styles.loadingMsg}>Loading PDF…</div>}
          >
            <div
              className={styles.pageWrapper}
              onMouseMove={handleMouseMoveWrapper}
              onMouseLeave={handleMarkerLeave}
            >
              <Page
                pageNumber={pageNumber}
                scale={zoom}
                renderTextLayer={true}
                renderAnnotationLayer={true}
              />

              {/* Highlight overlay (from field hover in editor) */}
              {highlightBox && (
                <motion.div
                  className={styles.highlight}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  style={{
                    left: highlightBox.x * zoom,
                    top: highlightBox.y * zoom,
                    width: highlightBox.width * zoom,
                    height: highlightBox.height * zoom,
                  }}
                />
              )}

              {/* Confidence heatmap overlay.
                  Words are populated when OCR confidence data is loaded from the API.
                  Pass word-level bbox+confidence data via props or store when available. */}
              <ConfidenceHeatmap
                words={[]}
                zoom={zoom}
                visible={heatmapVisible}
                onToggle={toggleHeatmap}
              />
            </div>
          </Document>
        )}
      </div>
    </div>
  );
}

export default PDFViewer;
