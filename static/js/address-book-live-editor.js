/**
 * address-book-live-editor.js — Live Overlay Address Book PDF Editor.
 *
 * Depends on:
 *   - PDF.js 3.x (loaded from CDN before this script)
 *   - Global variables injected by the Jinja2 template:
 *       PDF_URL       {string}  — URL to fetch the raw PDF
 *       DOC_ID        {number}  — database id of the document
 *       CSRF_TOKEN    {string}  — Flask-WTF CSRF token
 *       UPDATE_URL    {string}  — POST endpoint for single-field AJAX update
 *       PREFILL_URL   {string}  — GET endpoint for pre-fill suggestions
 *       DEMO_BOXES    {object}  — default bounding boxes (normalised 0–1)
 *       FIELDS        {Array}   — extracted field data from Flask
 */

/* global pdfjsLib, PDF_URL, DOC_ID, CSRF_TOKEN, UPDATE_URL, PREFILL_URL, DEMO_BOXES, FIELDS */

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
  // Constants
  // -------------------------------------------------------------------------
  /** Height (px) reserved for the field label above each input. */
  var LABEL_HEIGHT = 14;
  var pdfDoc       = null;
  var currentPage  = 1;
  var totalPages   = 1;
  var currentScale = 1.3;
  var renderTask   = null;
  var canvasW      = 0;
  var canvasH      = 0;

  // -------------------------------------------------------------------------
  // DOM references
  // -------------------------------------------------------------------------
  var canvas      = document.getElementById("able-pdf-canvas");
  var ctx         = canvas ? canvas.getContext("2d") : null;
  var overlay     = document.getElementById("able-overlay");
  var statusEl    = document.getElementById("able-render-status");
  var pageInput   = document.getElementById("page-input");
  var pageTotalEl = document.getElementById("page-total");
  var btnPrev     = document.getElementById("btn-prev");
  var btnNext     = document.getElementById("btn-next");
  var zoomInput   = document.getElementById("zoom-input");
  var btnZoomIn   = document.getElementById("btn-zoom-in");
  var btnZoomOut  = document.getElementById("btn-zoom-out");
  var btnZoomFit  = document.getElementById("btn-zoom-fit");
  var saveForm    = document.getElementById("able-save-form");
  var btnSavePdf  = document.getElementById("btn-save-pdf");
  var btnPrefill  = document.getElementById("btn-prefill");

  // Pre-fill suggestions cache: { "Name": ["Alice Smith", ...], ... }
  var prefillSuggestions = {};

  // -------------------------------------------------------------------------
  // Utility
  // -------------------------------------------------------------------------
  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg;
  }

  // -------------------------------------------------------------------------
  // Bounding box helper
  // Returns a normalised box {page, x, y, w, h} (all in 0–1 fractions)
  // -------------------------------------------------------------------------
  function getBox(field) {
    if (field.bbox && field.bbox.x !== null && field.bbox.x !== undefined) {
      // PDF-point coordinates — we need to normalise them.
      // We'll store them and normalise after the first page is rendered.
      return {
        page:       field.page_number || 1,
        pdfX:       field.bbox.x,
        pdfY:       field.bbox.y,
        pdfW:       field.bbox.width,
        pdfH:       field.bbox.height,
        isPdfUnits: true,
      };
    }
    return DEMO_BOXES[field.field_name] || null;
  }

  // -------------------------------------------------------------------------
  // Render a page
  // -------------------------------------------------------------------------
  function renderPage(pageNum, callback) {
    if (!pdfDoc) return;
    if (renderTask) {
      renderTask.cancel();
    }
    setStatus("Rendering…");

    pdfDoc.getPage(pageNum).then(function (page) {
      var viewport = page.getViewport({ scale: currentScale });
      canvas.width  = viewport.width;
      canvas.height = viewport.height;
      canvasW = viewport.width;
      canvasH = viewport.height;

      renderTask = page.render({ canvasContext: ctx, viewport: viewport });
      return renderTask.promise.then(function () {
        return { page: page, viewport: viewport };
      });
    }).then(function (result) {
      renderTask = null;
      setStatus("Page " + pageNum + " of " + totalPages);
      updateNavButtons();
      positionOverlays(result.viewport);
      if (callback) callback();
    }).catch(function (err) {
      if (err && err.name === "RenderingCancelledException") return;
      setStatus("Render error: " + (err.message || err));
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
      pdfDoc     = doc;
      totalPages = doc.numPages;
      if (pageInput) pageInput.max = totalPages;
      renderPage(1, buildOverlays);
    }).catch(function (err) {
      setStatus("Failed to load PDF: " + (err.message || err));
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
    var scroll = document.getElementById("able-pdf-scroll");
    if (!scroll || !pdfDoc) return;
    pdfDoc.getPage(currentPage).then(function (page) {
      var vp = page.getViewport({ scale: 1.0 });
      var available = scroll.clientWidth - 48; // subtract padding
      applyZoom(available / vp.width);
    });
  }

  // -------------------------------------------------------------------------
  // Build overlay inputs (called once after first render)
  // -------------------------------------------------------------------------
  function buildOverlays() {
    if (!overlay || !FIELDS || !FIELDS.length) return;

    // Remove any existing overlays
    overlay.innerHTML = "";

    FIELDS.forEach(function (field) {
      var box = getBox(field);
      if (!box) return;

      // Only show on the current page
      var fieldPage = box.isPdfUnits ? box.page : (box.page || 1);
      if (fieldPage !== currentPage) return;

      var wrapper = document.createElement("div");
      wrapper.className = "able-field-overlay";
      wrapper.dataset.fieldId   = field.id;
      wrapper.dataset.fieldName = field.field_name;

      var label = document.createElement("span");
      label.className   = "able-field-label";
      label.textContent = field.field_name;

      var input = document.createElement("input");
      input.type        = "text";
      input.className   = "able-field-input" + (field.is_edited ? " able-edited" : "");
      input.value       = field.value || "";
      input.placeholder = "—";
      input.autocomplete = "off";
      input.dataset.fieldId   = field.id;
      input.dataset.fieldName = field.field_name;

      // Phone auto-formatting
      if (/phone/i.test(field.field_name)) {
        input.type = "tel";
        input.addEventListener("input", formatPhone);
      }

      // ZIP code validation
      if (/zip/i.test(field.field_name)) {
        input.maxLength = 10;
        input.addEventListener("input", validateZip);
      }

      // Email validation
      if (/email/i.test(field.field_name)) {
        input.type = "email";
      }

      // Live AJAX update on blur
      input.addEventListener("input", function () {
        input.classList.add("able-unsaved");
      });

      input.addEventListener("blur", function () {
        if (input.classList.contains("able-unsaved")) {
          updateField(parseInt(field.id, 10), input.value, input);
        }
      });

      // Sync hidden save-form input on every change
      input.addEventListener("input", function () {
        var hidden = document.getElementById("save-field-" + field.id);
        if (hidden) hidden.value = input.value;
      });

      wrapper.appendChild(label);
      wrapper.appendChild(input);
      overlay.appendChild(wrapper);
    });

    positionOverlays(null);
  }

  // -------------------------------------------------------------------------
  // Position / reposition overlay elements based on current canvas size
  // -------------------------------------------------------------------------
  function positionOverlays(viewport) {
    if (!overlay) return;

    var items = overlay.querySelectorAll(".able-field-overlay");
    if (!items.length) {
      // Overlays not built yet — build them now
      buildOverlays();
      return;
    }

    items.forEach(function (wrapper) {
      var fieldName = wrapper.dataset.fieldName;
      // Find the FIELDS entry
      var field = null;
      for (var i = 0; i < FIELDS.length; i++) {
        if (String(FIELDS[i].id) === String(wrapper.dataset.fieldId)) {
          field = FIELDS[i];
          break;
        }
      }
      if (!field) return;

      var box = getBox(field);
      if (!box) return;

      var left, top, width, height;

      if (box.isPdfUnits && viewport) {
        // Convert PDF-point units to canvas pixels using the viewport transform
        var pt1 = viewport.convertToViewportPoint(box.pdfX, box.pdfY);
        var pt2 = viewport.convertToViewportPoint(box.pdfX + box.pdfW, box.pdfY + box.pdfH);

        left   = Math.min(pt1[0], pt2[0]);
        top    = Math.min(pt1[1], pt2[1]);
        width  = Math.abs(pt2[0] - pt1[0]);
        height = Math.abs(pt2[1] - pt1[1]) + LABEL_HEIGHT; // extra for label
      } else {
        // Use normalised 0–1 fractions
        var cw = canvas ? canvas.width  : canvasW;
        var ch = canvas ? canvas.height : canvasH;
        left   = box.x * cw;
        top    = box.y * ch;
        width  = box.w * cw;
        height = box.h * ch + LABEL_HEIGHT; // extra for label
      }

      // Minimum dimensions
      width  = Math.max(width,  60);
      height = Math.max(height, 30);

      wrapper.style.left   = left   + "px";
      wrapper.style.top    = top    + "px";
      wrapper.style.width  = width  + "px";
      wrapper.style.height = height + "px";
    });
  }

  // -------------------------------------------------------------------------
  // Phone number auto-formatting  (e.g. 7699888010 → (769) 988-8010)
  // -------------------------------------------------------------------------
  function formatPhone(evt) {
    var input = evt.target;
    // Strip everything except digits
    var digits = input.value.replace(/\D/g, "");
    var formatted = digits;
    if (digits.length >= 10) {
      formatted = "(" + digits.substring(0, 3) + ") " +
                  digits.substring(3, 6) + "-" +
                  digits.substring(6, 10);
      if (digits.length > 10) {
        formatted += " x" + digits.substring(10);
      }
    } else if (digits.length > 6) {
      formatted = "(" + digits.substring(0, 3) + ") " +
                  digits.substring(3, 6) + "-" +
                  digits.substring(6);
    } else if (digits.length > 3) {
      formatted = "(" + digits.substring(0, 3) + ") " +
                  digits.substring(3);
    }
    input.value = formatted;
    input.classList.add("able-unsaved");
  }

  // -------------------------------------------------------------------------
  // ZIP code validation
  // -------------------------------------------------------------------------
  function validateZip(evt) {
    var input = evt.target;
    var val   = input.value.replace(/[^0-9-]/g, "");
    input.value = val;
    // Valid: 5 digits or 5+4 with hyphen
    var valid = /^\d{5}(-\d{4})?$/.test(val) || val.length < 5;
    input.classList.toggle("able-invalid", !valid && val.length >= 5);
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
          inputEl.classList.add("able-edited");
          inputEl.classList.remove("able-unsaved");
          var hidden = document.getElementById("save-field-" + fieldId);
          if (hidden) hidden.value = value;
        }
      })
      .catch(function (err) {
        console.error("Field update failed:", err);
        if (inputEl) inputEl.classList.remove("able-unsaved");
      });
  }

  // -------------------------------------------------------------------------
  // Save PDF button — flush pending AJAX updates then submit the form
  // -------------------------------------------------------------------------
  if (btnSavePdf && saveForm) {
    btnSavePdf.addEventListener("click", function () {
      var pending  = overlay
        ? overlay.querySelectorAll(".able-field-input.able-unsaved[data-field-id]")
        : [];
      var promises = [];

      pending.forEach(function (input) {
        var fieldId = parseInt(input.dataset.fieldId, 10);
        if (!fieldId) return;
        var hidden = document.getElementById("save-field-" + fieldId);
        if (hidden) hidden.value = input.value;
        promises.push(
          fetch(UPDATE_URL, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": CSRF_TOKEN,
            },
            body: JSON.stringify({ field_id: fieldId, value: input.value }),
          }).catch(function (err) {
            console.error("Pending field update failed for field " + fieldId + ":", err);
          })
        );
      });

      Promise.all(promises).finally(function () {
        saveForm.submit();
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

  // Reposition overlays when the window is resized
  window.addEventListener("resize", function () {
    positionOverlays(null);
  });

  // -------------------------------------------------------------------------
  // Pre-fill: fetch suggestions from server and run a callback when done
  // -------------------------------------------------------------------------
  function loadPrefillSuggestions(callback) {
    if (typeof PREFILL_URL === "undefined") {
      if (callback) callback();
      return;
    }
    fetch(PREFILL_URL, {
      headers: { "X-CSRFToken": CSRF_TOKEN },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok && data.suggestions) {
          prefillSuggestions = data.suggestions;
        }
        if (callback) callback();
      })
      .catch(function (err) {
        console.warn("Could not fetch pre-fill suggestions:", err);
        if (callback) callback();
      });
  }

  // Warm the suggestions cache on page load (silent, no callback needed)
  function fetchPrefillSuggestions() {
    loadPrefillSuggestions(null);
  }

  // -------------------------------------------------------------------------
  // Pre-fill: populate blank overlay inputs with saved suggestions
  // -------------------------------------------------------------------------
  function applyPrefill() {
    if (!overlay) return;

    var inputs = overlay.querySelectorAll(".able-field-input[data-field-name]");
    var filledCount = 0;

    inputs.forEach(function (input) {
      // Only fill blank fields
      if (input.value && input.value.trim() !== "") return;

      var fieldName = input.dataset.fieldName;
      var suggestions = prefillSuggestions[fieldName];
      if (!suggestions || !suggestions.length) return;

      var suggestion = suggestions[0];
      if (!suggestion) return;

      input.value = suggestion;
      input.classList.add("able-unsaved", "able-prefilled");

      // Sync the hidden save-form input
      var fieldId = input.dataset.fieldId;
      var hidden = document.getElementById("save-field-" + fieldId);
      if (hidden) hidden.value = suggestion;

      // Remove the animation class after it completes
      input.addEventListener("animationend", function () {
        input.classList.remove("able-prefilled");
      }, { once: true });

      filledCount++;
    });

    if (filledCount === 0) {
      setStatus(
        Object.keys(prefillSuggestions).length === 0
          ? "No saved defaults found. Use Train Me to save values."
          : "All fields already filled — no defaults applied."
      );
    } else {
      setStatus(filledCount + " field(s) pre-filled from saved defaults.");
    }
  }

  // -------------------------------------------------------------------------
  // Pre-fill button handler
  // -------------------------------------------------------------------------
  if (btnPrefill) {
    btnPrefill.addEventListener("click", function () {
      // If suggestions have already been fetched, apply immediately;
      // otherwise fetch first, then apply.
      if (Object.keys(prefillSuggestions).length > 0) {
        applyPrefill();
      } else {
        loadPrefillSuggestions(function () {
          applyPrefill();
        });
      }
    });
  }

  // -------------------------------------------------------------------------
  // Boot
  // -------------------------------------------------------------------------
  fetchPrefillSuggestions();
  loadPDF();
})();
