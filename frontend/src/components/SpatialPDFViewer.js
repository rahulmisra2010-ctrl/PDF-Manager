/**
 * SpatialPDFViewer.js — Enhanced PDF viewer with spatial overlay support.
 *
 * Features:
 * - All PDFViewer capabilities (page nav, zoom)
 * - Bounding-box overlays for every OCR word
 * - Column / row grid overlay (toggleable)
 * - Zone highlighting (header / body / footer)
 * - Click-to-inspect: fires onPositionClick with PDF coordinates
 * - Hover context: fires onPositionHover with PDF coordinates
 *
 * Props:
 *   pdfUrl           {string}   URL of the PDF to display
 *   onPageChange     {func}     Called with (pageNumber) on page change
 *   highlightBox     {object}   Optional { x, y, width, height }
 *   words            {Array}    Enriched word list (SpatialOCREngine output)
 *   layoutData       {object}   Output of LayoutAnalyzer.analyze (optional)
 *   onPositionClick  {func}     Called with ({ x, y, page }) on canvas click
 *   onPositionHover  {func}     Called with ({ x, y, page }) on canvas hover
 *   showWordBoxes    {bool}     Toggle bounding boxes (default true)
 *   showGrid         {bool}     Toggle column/row grid (default false)
 *   showZones        {bool}     Toggle zone shading (default false)
 */

import React, { useState, useCallback, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/esm/Page/AnnotationLayer.css';
import 'react-pdf/dist/esm/Page/TextLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;

const ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0];

// Zone colours with low opacity
const ZONE_COLORS = {
  header: 'rgba(59,130,246,0.08)',
  body:   'rgba(16,185,129,0.05)',
  footer: 'rgba(245,158,11,0.08)',
};

// Confidence → border colour for word boxes
function confidenceColor(conf) {
  if (conf >= 0.85) return 'rgba(16,185,129,0.7)';  // green
  if (conf >= 0.65) return 'rgba(245,158,11,0.7)';   // amber
  return 'rgba(239,68,68,0.7)';                       // red
}

function SpatialPDFViewer({
  pdfUrl,
  onPageChange,
  highlightBox,
  words = [],
  layoutData = null,
  onPositionClick,
  onPositionHover,
  showWordBoxes = true,
  showGrid = false,
  showZones = false,
}) {
  const [numPages, setNumPages] = useState(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1.25);
  const [loadError, setLoadError] = useState(null);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const canvasRef = useRef(null);

  const onDocumentLoadSuccess = useCallback(({ numPages: n }) => {
    setNumPages(n);
    setPageNumber(1);
    setLoadError(null);
  }, []);

  const onDocumentLoadError = useCallback((err) => {
    setLoadError(err.message || 'Failed to load PDF');
  }, []);

  const onPageLoadSuccess = useCallback((page) => {
    setPageSize({ width: page.originalWidth, height: page.originalHeight });
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

  // Convert click/hover pixel offset to PDF coordinates
  const pixelToPdf = useCallback(
    (pixelX, pixelY) => {
      if (!pageSize.width || !pageSize.height) return { x: pixelX, y: pixelY };
      return {
        x: pixelX / zoom,
        y: pixelY / zoom,
      };
    },
    [zoom, pageSize]
  );

  const handleCanvasClick = useCallback(
    (e) => {
      if (!onPositionClick) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const pxX = e.clientX - rect.left;
      const pxY = e.clientY - rect.top;
      const pdf = pixelToPdf(pxX, pxY);
      onPositionClick({ ...pdf, page: pageNumber });
    },
    [onPositionClick, pixelToPdf, pageNumber]
  );

  const handleCanvasHover = useCallback(
    (e) => {
      if (!onPositionHover) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const pxX = e.clientX - rect.left;
      const pxY = e.clientY - rect.top;
      const pdf = pixelToPdf(pxX, pxY);
      onPositionHover({ ...pdf, page: pageNumber });
    },
    [onPositionHover, pixelToPdf, pageNumber]
  );

  const layout = layoutData && layoutData.layout ? layoutData.layout : layoutData;
  const pdfHeight = (layoutData && layoutData.page_height) || pageSize.height;

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
            <div
              ref={canvasRef}
              style={{ position: 'relative', display: 'inline-block', cursor: onPositionClick ? 'crosshair' : 'default' }}
              onClick={handleCanvasClick}
              onMouseMove={handleCanvasHover}
            >
              <Page
                pageNumber={pageNumber}
                scale={zoom}
                renderTextLayer={true}
                renderAnnotationLayer={true}
                onLoadSuccess={onPageLoadSuccess}
              />

              {/* Zone shading */}
              {showZones && layout && layout.zones && pdfHeight > 0 && (
                <>
                  {Object.entries(layout.zones).map(([zone, bounds]) => (
                    <div
                      key={zone}
                      title={zone}
                      style={{
                        position: 'absolute',
                        left: 0,
                        top: bounds.y_start * zoom,
                        width: '100%',
                        height: (bounds.y_end - bounds.y_start) * zoom,
                        background: ZONE_COLORS[zone] || 'transparent',
                        pointerEvents: 'none',
                        borderTop: zone !== 'header' ? '1px dashed rgba(100,116,139,0.3)' : 'none',
                      }}
                    />
                  ))}
                  {/* Zone labels */}
                  {Object.entries(layout.zones).map(([zone, bounds]) => (
                    <div
                      key={`label-${zone}`}
                      style={{
                        position: 'absolute',
                        left: 4,
                        top: bounds.y_start * zoom + 2,
                        fontSize: '9px',
                        color: 'rgba(100,116,139,0.7)',
                        pointerEvents: 'none',
                        textTransform: 'uppercase',
                        fontWeight: 600,
                        letterSpacing: '0.05em',
                      }}
                    >
                      {zone}
                    </div>
                  ))}
                </>
              )}

              {/* Column grid */}
              {showGrid && layout && layout.columns && pdfHeight > 0 && (
                <>
                  {layout.columns.map((col) => (
                    <div
                      key={`col-${col.index}`}
                      title={`Column ${col.index}`}
                      style={{
                        position: 'absolute',
                        left: col.x_start * zoom,
                        top: 0,
                        width: (col.x_end - col.x_start) * zoom,
                        height: pdfHeight * zoom,
                        borderLeft: '1px dashed rgba(99,102,241,0.25)',
                        borderRight: '1px dashed rgba(99,102,241,0.15)',
                        pointerEvents: 'none',
                      }}
                    />
                  ))}
                </>
              )}

              {/* Row grid */}
              {showGrid && layout && layout.rows && pdfHeight > 0 && (
                <>
                  {layout.rows.map((row) => (
                    <div
                      key={`row-${row.index}`}
                      title={`Row ${row.index}`}
                      style={{
                        position: 'absolute',
                        left: 0,
                        top: row.y_start * zoom,
                        width: '100%',
                        height: (row.y_end - row.y_start) * zoom,
                        borderTop: '1px dashed rgba(16,185,129,0.2)',
                        pointerEvents: 'none',
                      }}
                    />
                  ))}
                </>
              )}

              {/* Word bounding boxes */}
              {showWordBoxes && words.map((w, i) => {
                const pos = w.position || w;
                const ctx = w.contextual_features || {};
                const conf = ctx.ocr_confidence || 0.95;
                const color = confidenceColor(conf);
                return (
                  <div
                    key={i}
                    title={`${w.text}\nField: ${ctx.field_type_inferred || 'unknown'}\nConf: ${(conf * 100).toFixed(0)}%`}
                    style={{
                      position: 'absolute',
                      left: pos.x * zoom,
                      top: pos.y * zoom,
                      width: pos.width * zoom,
                      height: pos.height * zoom,
                      border: `1px solid ${color}`,
                      background: 'rgba(255,255,255,0.02)',
                      pointerEvents: 'none',
                      boxSizing: 'border-box',
                    }}
                  />
                );
              })}

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

export default SpatialPDFViewer;
