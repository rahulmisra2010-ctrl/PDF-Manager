/**
 * PDFViewer.js — Advanced PDF viewer with pixel-level hover detection.
 *
 * Features:
 * - Load PDF with react-pdf
 * - Pixel-level word hover detection with bounding boxes and glow effects
 * - Display bounding boxes from OCR / heatmap data
 * - Confidence indicators (Green/Yellow/Red) on word boxes
 * - Smooth hover animations with Framer Motion (fade-in/out, 200ms)
 * - Zoom/pan functionality with sticky toolbar
 * - Multi-page PDF with page navigation
 * - Thumbnail navigation (prev/next)
 * - ARIA labels and keyboard navigation
 *
 * Props:
 *   pdfUrl        {string}   URL of the PDF to display
 *   onPageChange  {func}     Called with (pageNumber) when page changes
 *   highlightBox  {object}   Optional { x, y, width, height } in PDF coords
 *   wordMarkers   {Array}    Optional array from heatmap for hover overlays
 *   onWordHover   {func}     Called with hovered word text (for editor sync)
 */

import React, { useState, useCallback } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { motion, AnimatePresence } from 'framer-motion';
import 'react-pdf/dist/esm/Page/AnnotationLayer.css';
import 'react-pdf/dist/esm/Page/TextLayer.css';
import usePixelHover from '../hooks/usePixelHover';
import useConfidenceColors from '../hooks/useConfidenceColors';
import { glowVariants } from '../hooks/useAnimations';
import styles from './styles/PDFViewer.module.css';

pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;

const ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0];

function WordHoverBox({ marker, scale }) {
  const [hovered, setHovered] = useState(false);
  const { getHeatmapColor, getGlowStyle } = useConfidenceColors();
  const { x, y, width, height, text, confidence } = marker;
  const pct = Math.round((confidence ?? 0) * 100);
  const bg = getHeatmapColor(confidence ?? 0, hovered ? 0.35 : 0.1);
  const border = getHeatmapColor(confidence ?? 0, hovered ? 0.9 : 0.4);
  const glow = hovered ? getGlowStyle(confidence ?? 0) : 'none';

  return (
    <div
      className={styles.wordBox}
      style={{
        left: x * scale,
        top: y * scale,
        width: width * scale,
        height: height * scale,
        background: bg,
        border: `1px solid ${border}`,
        boxShadow: glow,
        position: 'absolute',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      role="img"
      aria-label={`"${text}" — ${pct}% confidence`}
    >
      <AnimatePresence>
        {hovered && (
          <motion.div
            className={styles.wordTooltip}
            variants={glowVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
          >
            "{text}" — {pct}%
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function PDFViewer({ pdfUrl, onPageChange, highlightBox, wordMarkers = [], onWordHover }) {
  const [numPages, setNumPages] = useState(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1.25);
  const [loadError, setLoadError] = useState(null);

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

  // Pixel-level hover detection for word markers
  const handleWordHover = useCallback(
    (marker) => onWordHover && onWordHover(marker ? marker.text : null),
    [onWordHover]
  );
  const { containerProps } = usePixelHover(wordMarkers, zoom, handleWordHover);

  if (!pdfUrl) {
    return (
      <div className={styles.viewer}>
        <div className={styles.empty}>
          <span aria-hidden>📄</span>
          <p>No PDF loaded.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.viewer} role="region" aria-label="PDF Viewer">
      {/* ── Sticky toolbar ── */}
      <div className={styles.toolbar} role="toolbar" aria-label="PDF controls">
        <button
          className={styles.toolbarBtn}
          onClick={goToPrev}
          disabled={pageNumber <= 1}
          aria-label="Previous page"
          title="Previous page"
        >
          ‹
        </button>
        <input
          className={styles.pageInput}
          type="number"
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
          title="Next page"
        >
          ›
        </button>

        <span className={styles.toolbarSep} aria-hidden />

        <button
          className={styles.toolbarBtn}
          onClick={zoomOut}
          disabled={ZOOM_STEPS.indexOf(zoom) === 0}
          aria-label="Zoom out"
          title="Zoom out"
        >
          −
        </button>
        <span className={styles.zoomLabel}>{Math.round(zoom * 100)}%</span>
        <button
          className={styles.toolbarBtn}
          onClick={zoomIn}
          disabled={ZOOM_STEPS.indexOf(zoom) === ZOOM_STEPS.length - 1}
          aria-label="Zoom in"
          title="Zoom in"
        >
          +
        </button>
      </div>

      {/* ── PDF canvas area ── */}
      <div className={styles.canvasArea}>
        {loadError ? (
          <div className={styles.error} role="alert">
            <span aria-hidden>⚠️</span>
            <p>Could not load PDF: {loadError}</p>
          </div>
        ) : (
          <Document
            file={pdfUrl}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={
              <div className={styles.loading} aria-live="polite">
                <span aria-hidden>⏳</span> Loading PDF…
              </div>
            }
          >
            {/* Page wrapper with overlay support */}
            <div className={styles.pageWrapper} {...containerProps}>
              <Page
                pageNumber={pageNumber}
                scale={zoom}
                renderTextLayer={true}
                renderAnnotationLayer={true}
              />

              {/* ── Word-level confidence hover overlays ── */}
              {wordMarkers.map((marker, idx) => (
                <WordHoverBox
                  key={`${marker.text}-${idx}`}
                  marker={marker}
                  scale={zoom}
                />
              ))}

              {/* ── Highlight box for active field ── */}
              <AnimatePresence>
                {highlightBox && (
                  <motion.div
                    key="highlight"
                    className={styles.highlightBox}
                    style={{
                      left: highlightBox.x * zoom,
                      top: highlightBox.y * zoom,
                      width: highlightBox.width * zoom,
                      height: highlightBox.height * zoom,
                    }}
                    variants={glowVariants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                    aria-label="Highlighted field region"
                  />
                )}
              </AnimatePresence>
            </div>
          </Document>
        )}
      </div>
    </div>
  );
}

export default PDFViewer;

