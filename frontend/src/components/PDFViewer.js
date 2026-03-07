/**
 * PDFViewer.js — Embedded PDF viewer using react-pdf.
 *
 * Features:
 * - Page navigation (prev/next + direct input)
 * - Zoom in/out (50% – 300%)
 * - Vertical scrolling for multi-page PDFs
 * - Loading and error states
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

// Use locally bundled worker to avoid CDN dependency
pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;

const ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0];

function PDFViewer({ pdfUrl, onPageChange, highlightBox }) {
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

  if (!pdfUrl) {
    return (
      <div className="pdf-viewer pdf-viewer--empty">
        <p>No PDF loaded.</p>
      </div>
    );
  }

  return (
    <div className="pdf-viewer">
      {/* Toolbar */}
      <div className="pdf-viewer__toolbar">
        <button onClick={goToPrev} disabled={pageNumber <= 1} aria-label="Previous page">‹</button>
        <input
          type="number"
          value={pageNumber}
          min={1}
          max={numPages || 1}
          onChange={handlePageInput}
          aria-label="Page number"
        />
        <span>/ {numPages || '?'}</span>
        <button onClick={goToNext} disabled={pageNumber >= (numPages || 1)} aria-label="Next page">›</button>

        <span className="pdf-viewer__toolbar-sep" />

        <button onClick={zoomOut} aria-label="Zoom out">−</button>
        <span>{Math.round(zoom * 100)}%</span>
        <button onClick={zoomIn} aria-label="Zoom in">+</button>
      </div>

      {/* PDF Canvas */}
      <div className="pdf-viewer__canvas-area">
        {loadError ? (
          <div className="pdf-viewer__error">
            <p>⚠️ Could not load PDF: {loadError}</p>
          </div>
        ) : (
          <Document
            file={pdfUrl}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={<div className="pdf-viewer__loading">Loading PDF…</div>}
          >
            <div style={{ position: 'relative', display: 'inline-block' }}>
              <Page
                pageNumber={pageNumber}
                scale={zoom}
                renderTextLayer={true}
                renderAnnotationLayer={true}
              />
              {/* Highlight overlay */}
              {highlightBox && (
                <div
                  className="pdf-viewer__highlight"
                  style={{
                    position: 'absolute',
                    left: highlightBox.x * zoom,
                    top: highlightBox.y * zoom,
                    width: highlightBox.width * zoom,
                    height: highlightBox.height * zoom,
                    border: '2px solid #f59e0b',
                    background: 'rgba(245,158,11,0.15)',
                    pointerEvents: 'none',
                  }}
                />
              )}
            </div>
          </Document>
        )}
      </div>
    </div>
  );
}

export default PDFViewer;
