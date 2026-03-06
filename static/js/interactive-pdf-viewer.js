/**
 * static/js/interactive-pdf-viewer.js
 *
 * Interactive PDF viewer built on PDF.js.
 *
 * Responsibilities:
 *  - Load and render PDF pages onto an HTML5 canvas
 *  - Support zoom in / zoom out / fit-width
 *  - Provide page navigation (prev / next / jump-to)
 *  - Emit events so the AI extractor can overlay field highlights
 *  - Expose a page-render-complete callback
 */

/* global pdfjsLib */
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

  /** Clear the overlay canvas. */
  clearOverlay() {
    if (this._octx && this._overlay) {
      this._octx.clearRect(0, 0, this._overlay.width, this._overlay.height);
    }
  }

  /** Draw all field bounding boxes at once with confidence-based colours. */
  drawFields(fields) {
    this.clearOverlay();
    for (const f of fields) {
      const { x0, y0, x1, y1 } = f.bbox || {};
      if (x0 === undefined) continue;
      const { fill, stroke } = this._confColor(f.confidence || 0.5);
      this.drawHighlight(x0, y0, x1, y1, fill, stroke);
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
