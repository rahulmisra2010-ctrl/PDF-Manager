/**
 * address-book-editor.js — Address Book PDF Editor frontend logic.
 *
 * Depends on:
 *   - PDF.js 3.x (loaded from CDN before this script)
 *   - Global variables injected by the Jinja2 template:
 *       PDF_URL       {string}  — URL to fetch the raw PDF
 *       DOC_ID        {number}  — database id of the document
 *       CSRF_TOKEN    {string}  — Flask-WTF CSRF token
 *       UPDATE_URL    {string}  — POST endpoint for single-field AJAX update
 */

/* global pdfjsLib, PDF_URL, DOC_ID, CSRF_TOKEN, UPDATE_URL */

(function () {
  "use strict";

  // -------------------------------------------------------------------------
  // PDF.js worker
  // -------------------------------------------------------------------------
  if (typeof pdfjsLib !== "undefined") {
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
  }

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------
  let pdfDoc = null;
  let currentPage = 1;
  let totalPages = 1;
  let currentScale = 1.5;
  let renderTask = null;

  // -------------------------------------------------------------------------
  // DOM references
  // -------------------------------------------------------------------------
  const canvas      = document.getElementById("abe-pdf-canvas");
  const ctx         = canvas ? canvas.getContext("2d") : null;
  const statusEl    = document.getElementById("abe-render-status");
  const pageInput   = document.getElementById("page-input");
  const pageTotalEl = document.getElementById("page-total");
  const btnPrev     = document.getElementById("btn-prev");
  const btnNext     = document.getElementById("btn-next");
  const zoomInput   = document.getElementById("zoom-input");
  const btnZoomIn   = document.getElementById("btn-zoom-in");
  const btnZoomOut  = document.getElementById("btn-zoom-out");
  const btnZoomFit  = document.getElementById("btn-zoom-fit");
  const saveForm    = document.getElementById("abe-save-form");

  // -------------------------------------------------------------------------
  // Utility: set status text
  // -------------------------------------------------------------------------
  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg;
  }

  // -------------------------------------------------------------------------
  // Render a given page onto the canvas
  // -------------------------------------------------------------------------
  function renderPage(pageNum) {
    if (!pdfDoc) return;
    if (renderTask) {
      renderTask.cancel();
    }
    setStatus("Rendering…");

    pdfDoc.getPage(pageNum).then(function (page) {
      const viewport = page.getViewport({ scale: currentScale });
      canvas.width  = viewport.width;
      canvas.height = viewport.height;

      renderTask = page.render({ canvasContext: ctx, viewport: viewport });
      return renderTask.promise;
    }).then(function () {
      renderTask = null;
      setStatus("Page " + pageNum + " of " + totalPages);
      updateNavButtons();
    }).catch(function (err) {
      if (err && err.name === "RenderingCancelledException") return;
      setStatus("Render error: " + err.message);
    });
  }

  // -------------------------------------------------------------------------
  // Navigation helpers
  // -------------------------------------------------------------------------
  function updateNavButtons() {
    if (btnPrev) btnPrev.disabled = currentPage <= 1;
    if (btnNext) btnNext.disabled = currentPage >= totalPages;
    if (pageInput) pageInput.value = currentPage;
    if (pageTotalEl) pageTotalEl.textContent = totalPages;
  }

  function goToPage(n) {
    n = Math.max(1, Math.min(totalPages, parseInt(n, 10) || 1));
    currentPage = n;
    renderPage(currentPage);
  }

  // -------------------------------------------------------------------------
  // Load PDF
  // -------------------------------------------------------------------------
  function loadPDF() {
    if (typeof pdfjsLib === "undefined" || !PDF_URL) {
      setStatus("PDF.js not available.");
      return;
    }
    setStatus("Loading PDF…");
    pdfjsLib.getDocument(PDF_URL).promise.then(function (doc) {
      pdfDoc   = doc;
      totalPages = doc.numPages;
      if (pageInput) {
        pageInput.max = totalPages;
      }
      renderPage(1);
    }).catch(function (err) {
      setStatus("Failed to load PDF: " + err.message);
    });
  }

  // -------------------------------------------------------------------------
  // Zoom helpers
  // -------------------------------------------------------------------------
  function applyZoom(newScale) {
    currentScale = Math.max(0.25, Math.min(4.0, newScale));
    if (zoomInput) zoomInput.value = Math.round(currentScale * 100);
    renderPage(currentPage);
  }

  function fitToWidth() {
    const scroll = document.getElementById("abe-pdf-scroll");
    if (!scroll || !pdfDoc) return;
    pdfDoc.getPage(currentPage).then(function (page) {
      const vp = page.getViewport({ scale: 1.0 });
      const available = scroll.clientWidth - 32; // subtract padding
      applyZoom(available / vp.width);
    });
  }

  // -------------------------------------------------------------------------
  // AJAX: single-field update
  // -------------------------------------------------------------------------
  function updateField(fieldId, value, inputEl) {
    fetch(UPDATE_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CSRF_TOKEN,
      },
      body: JSON.stringify({ field_id: fieldId, value: value }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok && inputEl) {
          inputEl.classList.add("abe-edited");
          inputEl.classList.remove("abe-unsaved");
          // Mark the hidden save-form input too
          const hidden = document.getElementById("save-field-" + fieldId);
          if (hidden) hidden.value = value;
        }
      })
      .catch(function (err) {
        console.error("Field update failed:", err);
        // Remove the unsaved marker so it can be retried on next blur
        if (inputEl) inputEl.classList.remove("abe-unsaved");
      });
  }

  // -------------------------------------------------------------------------
  // Wire up form inputs for live AJAX saving on blur
  // -------------------------------------------------------------------------
  function initFieldInputs() {
    document.querySelectorAll(".abe-field-input[data-field-id]").forEach(function (input) {
      const fieldId = parseInt(input.dataset.fieldId, 10);
      if (!fieldId) return;

      // Mark as unsaved on keypress
      input.addEventListener("input", function () {
        input.classList.add("abe-unsaved");
      });

      // AJAX-save on blur (focus leaves the field)
      input.addEventListener("blur", function () {
        if (input.classList.contains("abe-unsaved")) {
          updateField(fieldId, input.value, input);
        }
      });

      // Also update hidden save-form input on every change so the bulk
      // save form always has the latest values.
      input.addEventListener("change", function () {
        const hidden = document.getElementById("save-field-" + fieldId);
        if (hidden) hidden.value = input.value;
      });
    });
  }

  // -------------------------------------------------------------------------
  // Event listeners: navigation
  // -------------------------------------------------------------------------
  if (btnPrev) {
    btnPrev.addEventListener("click", function () {
      if (currentPage > 1) goToPage(currentPage - 1);
    });
  }

  if (btnNext) {
    btnNext.addEventListener("click", function () {
      if (currentPage < totalPages) goToPage(currentPage + 1);
    });
  }

  if (pageInput) {
    pageInput.addEventListener("change", function () {
      goToPage(pageInput.value);
    });
  }

  // -------------------------------------------------------------------------
  // Event listeners: zoom
  // -------------------------------------------------------------------------
  if (btnZoomIn)  btnZoomIn.addEventListener("click",  function () { applyZoom(currentScale + 0.25); });
  if (btnZoomOut) btnZoomOut.addEventListener("click", function () { applyZoom(currentScale - 0.25); });
  if (btnZoomFit) btnZoomFit.addEventListener("click", fitToWidth);

  if (zoomInput) {
    zoomInput.addEventListener("change", function () {
      applyZoom(parseInt(zoomInput.value, 10) / 100);
    });
  }

  // -------------------------------------------------------------------------
  // Save all button triggers the hidden form
  // -------------------------------------------------------------------------
  const btnSaveAll = document.getElementById("btn-save-all");
  if (btnSaveAll && saveForm) {
    btnSaveAll.addEventListener("click", function () {
      // Flush any currently-unsaved inputs via AJAX before submitting the form.
      const pending = document.querySelectorAll(".abe-field-input.abe-unsaved[data-field-id]");
      const promises = [];
      pending.forEach(function (input) {
        const fieldId = parseInt(input.dataset.fieldId, 10);
        if (fieldId) {
          // Update hidden save-form value immediately
          const hidden = document.getElementById("save-field-" + fieldId);
          if (hidden) hidden.value = input.value;
          promises.push(
            fetch(UPDATE_URL, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": CSRF_TOKEN,
              },
              body: JSON.stringify({ field_id: fieldId, value: input.value }),
            }).catch(function () {})
          );
        }
      });
      // Wait for all in-flight AJAX updates, then submit the form.
      Promise.all(promises).finally(function () {
        saveForm.submit();
      });
    });
  }

  // -------------------------------------------------------------------------
  // Boot
  // -------------------------------------------------------------------------
  initFieldInputs();
  loadPDF();
})();
