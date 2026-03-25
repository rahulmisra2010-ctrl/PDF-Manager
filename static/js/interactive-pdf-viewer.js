/**
 * static/js/interactive-pdf-viewer.js
 *
 * Interactive PDF viewer using server-side page image rendering.
 *
 * Responsibilities:
 *  - Load and display server-rendered PDF page images on an HTML5 canvas
 *  - Support zoom in / zoom out / fit-width
 *  - Provide page navigation (prev / next / jump-to)
 *  - Overlay field highlights with confidence-based colours
 *  - Expose a page-render-complete callback
 */

/* exported InteractivePDFViewer */

'use strict';

class InteractivePDFViewer {
  /**
   * @param {object} options
   * @param {string}   options.canvasId        – id of the main <canvas>
   * @param {string}   options.overlayCanvasId – id of the highlight overlay canvas
   * @param {string}   options.pageInputId     – id of the <input> showing current page
   * @param {string}   options.pageCountId     – id of the element showing total pages
   * @param {string}   options.zoomSelectId    – id of the zoom <select>
   * @param {string}   options.pageImageUrl    – URL template for page images:
   *                                             replace '{page}' and '{zoom}' placeholders
   * @param {number}  [options.initialPage=1]  – page to render first
   * @param {number}  [options.totalPages=1]   – total page count from server
   * @param {Function}[options.onPageRendered] – called with (pageNum) after each render
   */
  constructor(options) {
    this.canvasId        = options.canvasId;
    this.overlayCanvasId = options.overlayCanvasId;
    this.pageInputId     = options.pageInputId;
    this.pageCountId     = options.pageCountId;
    this.zoomSelectId    = options.zoomSelectId;
    this.pageImageUrl    = options.pageImageUrl;
    this.onPageRendered  = options.onPageRendered || (() => {});

    this.currentPage = options.initialPage || 1;
    this.totalPages  = options.totalPages  || 1;
    this.zoom        = 1.5;

    this._canvas  = document.getElementById(this.canvasId);
    this._overlay = document.getElementById(this.overlayCanvasId);
    this._ctx     = this._canvas  ? this._canvas.getContext('2d')  : null;
    this._octx    = this._overlay ? this._overlay.getContext('2d') : null;

    this._setupControls();
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  /** Render (or re-render) the current page. */
  async renderCurrentPage() {
    if (!this._canvas) return;
    this._setLoading(true);
    try {
      const url = this._buildUrl(this.currentPage, this.zoom);
      const img = await this._loadImage(url);
      this._canvas.width  = img.naturalWidth;
      this._canvas.height = img.naturalHeight;
      if (this._overlay) {
        this._overlay.width  = img.naturalWidth;
        this._overlay.height = img.naturalHeight;
      }
      this._ctx.drawImage(img, 0, 0);
      this.clearOverlay();
      this._updatePageInput();
      this.onPageRendered(this.currentPage);
    } catch (err) {
      console.error('[PDFViewer] render error:', err);
    } finally {
      this._setLoading(false);
    }
  }

  /** Navigate to a specific page number (1-based). */
  goToPage(pageNum) {
    pageNum = Math.max(1, Math.min(this.totalPages, parseInt(pageNum, 10) || 1));
    this.currentPage = pageNum;
    this.renderCurrentPage();
  }

  prevPage() { if (this.currentPage > 1)             this.goToPage(this.currentPage - 1); }
  nextPage() { if (this.currentPage < this.totalPages) this.goToPage(this.currentPage + 1); }

  /** Set zoom factor and re-render. */
  setZoom(zoom) {
    this.zoom = Math.max(0.5, Math.min(3.0, parseFloat(zoom) || 1.5));
    const sel = document.getElementById(this.zoomSelectId);
    if (sel) sel.value = String(this.zoom);
    this.renderCurrentPage();
  }

  /** Draw a highlighted rectangle on the overlay canvas. */
  drawHighlight(x0, y0, x1, y1, color = 'rgba(13,110,253,0.25)', stroke = '#0d6efd') {
    if (!this._octx) return;
    this._octx.save();
    this._octx.strokeStyle = stroke;
    this._octx.lineWidth   = 1.5;
    this._octx.fillStyle   = color;
    this._octx.fillRect  (x0, y0, x1 - x0, y1 - y0);
    this._octx.strokeRect(x0, y0, x1 - x0, y1 - y0);
    this._octx.restore();
  }

  /**
   * Draw a highlighted rectangle with label and value text displayed.
   * This creates a brown-colored rectangle with the field label shown above
   * and the value shown inside the rectangle.
   *
   * @param {number} x0 - Left x coordinate
   * @param {number} y0 - Top y coordinate
   * @param {number} x1 - Right x coordinate
   * @param {number} y1 - Bottom y coordinate
   * @param {string} label - Field label to display above the rectangle
   * @param {string} value - Field value to display inside the rectangle
   * @param {object} options - Additional options (fillColor, strokeColor)
   */
  drawLabeledHighlight(x0, y0, x1, y1, label = '', value = '', options = {}) {
    if (!this._octx) return;
    const ctx = this._octx;
    const width  = x1 - x0;
    const height = y1 - y0;

    // Brown color scheme as shown in the reference image
    const fillColor   = options.fillColor   || 'rgba(139, 69, 19, 0.15)';
    const strokeColor = options.strokeColor || '#8B4513';
    const labelBgColor = options.labelBgColor || '#8B4513';

    ctx.save();

    // Draw rectangle with brown border
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth   = 2;
    ctx.fillStyle   = fillColor;
    ctx.fillRect(x0, y0, width, height);
    ctx.strokeRect(x0, y0, width, height);

    // Draw label above the rectangle if provided
    if (label) {
      const labelFontSize = Math.max(10, Math.min(14, height * 0.3));
      ctx.font = `bold ${labelFontSize}px Arial, sans-serif`;
      const labelMetrics = ctx.measureText(label);
      const labelWidth = labelMetrics.width + 8;
      const labelHeight = labelFontSize + 4;
      const labelX = x0;
      // Position label above the rectangle, but ensure it stays within canvas bounds
      let labelY = y0 - labelHeight - 2;
      if (labelY < 0) {
        // If label would be above canvas, position it inside the rectangle at the top
        labelY = y0 + 2;
      }

      // Label background
      ctx.fillStyle = labelBgColor;
      ctx.fillRect(labelX, labelY, labelWidth, labelHeight);

      // Label text (white)
      ctx.fillStyle = '#FFFFFF';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, labelX + 4, labelY + labelHeight / 2);
    }

    // Draw value inside the rectangle if provided
    if (value) {
      const valueFontSize = Math.max(10, Math.min(16, height * 0.5));
      ctx.font = `${valueFontSize}px Arial, sans-serif`;
      ctx.fillStyle = '#333333';
      ctx.textBaseline = 'middle';

      // Calculate text position (centered in box)
      const valueMetrics = ctx.measureText(value);
      const textX = x0 + (width - valueMetrics.width) / 2;
      const textY = y0 + height / 2;

      // Draw value text (clipped to box width)
      ctx.save();
      ctx.beginPath();
      ctx.rect(x0 + 2, y0 + 2, width - 4, height - 4);
      ctx.clip();
      ctx.fillText(value, Math.max(x0 + 4, textX), textY);
      ctx.restore();
    }

    ctx.restore();
  }

  /** Clear the overlay canvas. */
  clearOverlay() {
    if (this._octx && this._overlay) {
      this._octx.clearRect(0, 0, this._overlay.width, this._overlay.height);
    }
  }

  /** Draw all field bounding boxes at once with brown-colored highlights.
   *
   * Fields are drawn with their label shown above the rectangle and
   * the value shown inside the rectangle, using a brown color scheme.
   * This provides clear visual identification of extracted field sections.
   */
  drawFields(fields) {
    this.clearOverlay();
    for (const f of fields) {
      const label = f.label || f.field_name || '';
      const value = f.value || f.text || '';

      // If field has both label_bbox and bbox, draw them as a combined section
      // with the label shown above the combined bounding box
      if (f.label_bbox && f.bbox) {
        // Calculate combined bounding box that spans both label and value
        const lbox = f.label_bbox;
        const vbox = f.bbox;
        const combinedX0 = Math.min(lbox.x0 || 0, vbox.x0 || 0);
        const combinedY0 = Math.min(lbox.y0 || 0, vbox.y0 || 0);
        const combinedX1 = Math.max(lbox.x1 || 0, vbox.x1 || 0);
        const combinedY1 = Math.max(lbox.y1 || 0, vbox.y1 || 0);

        if (combinedX0 !== undefined && combinedX0 < combinedX1) {
          this.drawLabeledHighlight(
            combinedX0, combinedY0, combinedX1, combinedY1,
            label, value
          );
        }
      }
      // If only value bbox is present
      else if (f.bbox) {
        const { x0, y0, x1, y1 } = f.bbox;
        if (x0 !== undefined) {
          this.drawLabeledHighlight(x0, y0, x1, y1, label, value);
        }
      }
      // If only label bbox is present (label-only field)
      else if (f.label_bbox) {
        const { x0, y0, x1, y1 } = f.label_bbox;
        if (x0 !== undefined) {
          this.drawLabeledHighlight(x0, y0, x1, y1, label, '');
        }
      }
    }
  }

  /** Current canvas dimensions. */
  get canvasSize() {
    return {
      width:  this._canvas ? this._canvas.width  : 0,
      height: this._canvas ? this._canvas.height : 0,
    };
  }

  // -------------------------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------------------------

  _buildUrl(page, zoom) {
    return this.pageImageUrl
      .replace('{page}', page)
      .replace('{zoom}', zoom);
  }

  _loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload  = () => resolve(img);
      img.onerror = ()  => reject(new Error(`Failed to load image: ${src}`));
      img.src = src;
    });
  }

  _setupControls() {
    const sel = document.getElementById(this.zoomSelectId);
    if (sel) {
      sel.value = String(this.zoom);
      sel.addEventListener('change', () => this.setZoom(sel.value));
    }

    const pageInput = document.getElementById(this.pageInputId);
    if (pageInput) {
      pageInput.addEventListener('change', () => this.goToPage(pageInput.value));
    }

    const countEl = document.getElementById(this.pageCountId);
    if (countEl) countEl.textContent = this.totalPages;
  }

  _updatePageInput() {
    const inp = document.getElementById(this.pageInputId);
    if (inp) inp.value = this.currentPage;
  }

  _setLoading(on) {
    const overlay = document.getElementById('pdf-loading-overlay');
    if (overlay) overlay.style.display = on ? 'flex' : 'none';
  }

  _confColor(conf) {
    if (conf >= 0.80) return { fill: 'rgba(25,135,84,0.18)',  stroke: 'rgba(25,135,84,0.7)'  };
    if (conf >= 0.55) return { fill: 'rgba(255,193,7,0.18)',  stroke: 'rgba(255,193,7,0.7)'  };
    return               { fill: 'rgba(220,53,69,0.18)',  stroke: 'rgba(220,53,69,0.7)'  };
  }
}
