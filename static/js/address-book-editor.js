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
  // Default / suggested field values shown when extracted value is empty
  // -------------------------------------------------------------------------
  var FIELD_DEFAULTS = {
    "Name":           "Rahul Misra",
    "Street Address": "Sumoth pally. Durgamandir",
    "City":           "Asansol",
    "State":          "WB",
    "Zip Code":       "713301",
    "Home Phone":     "",
    "Cell Phone":     "7699888010",
    "Work Phone":     "",
    "Email":          ""
  };

  // Fields that must not be empty when saved
  var REQUIRED_FIELDS = ["Name", "Cell Phone"];

  // Phone fields: value must be exactly 10 digits (if non-empty)
  var PHONE_FIELDS = ["Home Phone", "Cell Phone", "Work Phone"];

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
  var pdfDoc     = null;
  var currentPage  = 1;
  var totalPages   = 1;
  var currentScale = 1.5;
  var renderTask   = null;

  // -------------------------------------------------------------------------
  // DOM references
  // -------------------------------------------------------------------------
  var canvas      = document.getElementById("abe-pdf-canvas");
  var ctx         = canvas ? canvas.getContext("2d") : null;
  var statusEl    = document.getElementById("abe-render-status");
  var pageInput   = document.getElementById("page-input");
  var pageTotalEl = document.getElementById("page-total");
  var btnPrev     = document.getElementById("btn-prev");
  var btnNext     = document.getElementById("btn-next");
  var zoomInput   = document.getElementById("zoom-input");
  var btnZoomIn   = document.getElementById("btn-zoom-in");
  var btnZoomOut  = document.getElementById("btn-zoom-out");
  var btnZoomFit  = document.getElementById("btn-zoom-fit");
  var saveForm    = document.getElementById("abe-save-form");

  // -------------------------------------------------------------------------
  // Toast notifications
  // -------------------------------------------------------------------------
  var toastContainer = (function () {
    var el = document.getElementById("abe-toast-container");
    if (!el) {
      el = document.createElement("div");
      el.id = "abe-toast-container";
      document.body.appendChild(el);
    }
    return el;
  }());

  function showToast(message, type) {
    var toast = document.createElement("div");
    toast.className = "abe-toast abe-toast-" + (type || "info");

    var icon = type === "success" ? "✔" : type === "error" ? "✖" : "ℹ";
    toast.textContent = icon + "\u00a0" + message;

    toastContainer.appendChild(toast);

    setTimeout(function () {
      toast.style.animation = "abeToastOut 0.3s ease forwards";
      setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 320);
    }, 3200);
  }

  // -------------------------------------------------------------------------
  // Field validation
  // -------------------------------------------------------------------------
  function validateFieldValue(fieldName, value) {
    // Required check
    if (REQUIRED_FIELDS.indexOf(fieldName) !== -1 && !value.trim()) {
      return fieldName + " is required.";
    }
    // Phone format: 10 digits (when non-empty)
    if (PHONE_FIELDS.indexOf(fieldName) !== -1 && value.trim()) {
      if (!/^\d{10}$/.test(value.trim())) {
        return "Phone must be exactly 10 digits.";
      }
    }
    // Email format (when non-empty)
    if (fieldName === "Email" && value.trim()) {
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())) {
        return "Enter a valid email address.";
      }
    }
    return null;
  }

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
      var viewport = page.getViewport({ scale: currentScale });
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
      pdfDoc     = doc;
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
    var scroll = document.getElementById("abe-pdf-scroll");
    if (!scroll || !pdfDoc) return;
    pdfDoc.getPage(currentPage).then(function (page) {
      var vp = page.getViewport({ scale: 1.0 });
      var available = scroll.clientWidth - 32; // subtract padding
      applyZoom(available / vp.width);
    });
  }

  // -------------------------------------------------------------------------
  // AJAX: single-field update
  // -------------------------------------------------------------------------
  function updateFieldAjax(fieldId, value, onSuccess, onError) {
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
        if (data.ok) {
          // Keep hidden save-form input in sync
          var hidden = document.getElementById("save-field-" + fieldId);
          if (hidden) hidden.value = value;
          if (onSuccess) onSuccess(data);
        } else {
          if (onError) onError(data.error || "Save failed.");
        }
      })
      .catch(function (err) {
        if (onError) onError("Network error: " + err.message);
      });
  }

  // -------------------------------------------------------------------------
  // Inline field editor: switch a field group between view ↔ edit mode
  // -------------------------------------------------------------------------
  function enterEditMode(group) {
    var viewEl  = group.querySelector(".abe-field-view");
    var editRow = group.querySelector(".abe-field-edit-row");
    var input   = editRow ? editRow.querySelector(".abe-field-edit-input") : null;
    if (!viewEl || !editRow || !input) return;

    // If value is empty, suggest the default
    var fieldName = viewEl.dataset.fieldName || "";
    if (!input.value && FIELD_DEFAULTS[fieldName]) {
      input.value = FIELD_DEFAULTS[fieldName];
    }

    viewEl.style.display  = "none";
    editRow.classList.add("abe-active");
    input.focus();
    input.select();
    clearFieldError(editRow);
  }

  function exitEditMode(group, restoreValue) {
    var viewEl  = group.querySelector(".abe-field-view");
    var editRow = group.querySelector(".abe-field-edit-row");
    var input   = editRow ? editRow.querySelector(".abe-field-edit-input") : null;
    if (!viewEl || !editRow) return;

    if (restoreValue && input) {
      // Revert to the value shown in view mode
      var textSpan = viewEl.querySelector(".abe-field-value-text");
      var currentDisplayed = textSpan ? textSpan.dataset.rawValue || textSpan.textContent.trim() : "";
      input.value = currentDisplayed;
    }

    editRow.classList.remove("abe-active");
    viewEl.style.display = "";
    clearFieldError(editRow);
  }

  function setFieldError(editRow, message) {
    var errEl = editRow.querySelector(".abe-field-error");
    var input = editRow.querySelector(".abe-field-edit-input");
    if (errEl) {
      errEl.textContent = message;
      errEl.classList.add("abe-visible");
    }
    if (input) input.classList.add("abe-invalid");
  }

  function clearFieldError(editRow) {
    var errEl = editRow ? editRow.querySelector(".abe-field-error") : null;
    var input = editRow ? editRow.querySelector(".abe-field-edit-input") : null;
    if (errEl) {
      errEl.textContent = "";
      errEl.classList.remove("abe-visible");
    }
    if (input) input.classList.remove("abe-invalid");
  }

  function updateViewText(group, newValue) {
    var viewEl   = group.querySelector(".abe-field-view");
    var textSpan = viewEl ? viewEl.querySelector(".abe-field-value-text") : null;
    var fieldName = viewEl ? (viewEl.dataset.fieldName || "") : "";

    if (!textSpan) return;
    var displayVal = newValue || FIELD_DEFAULTS[fieldName] || "";
    textSpan.textContent = displayVal || "(empty)";
    textSpan.dataset.rawValue = newValue;

    // Toggle placeholder style
    if (!newValue) {
      textSpan.classList.add("abe-placeholder");
    } else {
      textSpan.classList.remove("abe-placeholder");
    }

    // Mark the label's edited badge
    var label = group.querySelector(".abe-field-label");
    var badge = label ? label.querySelector(".abe-edited-badge") : null;
    if (!badge && label && newValue) {
      var b = document.createElement("span");
      b.className = "abe-edited-badge";
      b.textContent = "edited";
      label.appendChild(b);
    }
  }

  // -------------------------------------------------------------------------
  // Wire up inline editors for all field groups
  // -------------------------------------------------------------------------
  function initInlineEditors() {
    var groups = document.querySelectorAll(".abe-field-group");
    groups.forEach(function (group) {
      var viewEl  = group.querySelector(".abe-field-view");
      var editRow = group.querySelector(".abe-field-edit-row");

      if (!viewEl) return;

      // Apply default value to view text if currently empty
      var textSpan  = viewEl.querySelector(".abe-field-value-text");
      var fieldName = viewEl.dataset.fieldName || "";
      if (textSpan) {
        var raw = textSpan.dataset.rawValue !== undefined
          ? textSpan.dataset.rawValue
          : textSpan.textContent.trim();

        if (!raw) {
          var def = FIELD_DEFAULTS[fieldName] || "";
          if (def) {
            textSpan.textContent = def;
            textSpan.classList.remove("abe-placeholder");
          }
        }
      }

      // No edit row → field not in DB; skip interaction
      if (!editRow) return;

      // Click on view → enter edit mode
      viewEl.addEventListener("click", function () {
        enterEditMode(group);
      });

      var input     = editRow.querySelector(".abe-field-edit-input");
      var saveBtn   = editRow.querySelector(".abe-btn-save-field");
      var cancelBtn = editRow.querySelector(".abe-btn-cancel-field");

      if (!input || !saveBtn || !cancelBtn) return;

      var fieldId = parseInt(input.dataset.fieldId, 10);

      // Cancel → exit without saving
      cancelBtn.addEventListener("click", function () {
        exitEditMode(group, true);
      });

      // Escape key → cancel
      input.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
          exitEditMode(group, true);
        } else if (e.key === "Enter") {
          saveBtn.click();
        }
      });

      // Clear validation error on input
      input.addEventListener("input", function () {
        clearFieldError(editRow);
      });

      // Save button
      saveBtn.addEventListener("click", function () {
        var newValue = input.value;
        var err = validateFieldValue(fieldName, newValue);
        if (err) {
          setFieldError(editRow, err);
          return;
        }

        saveBtn.disabled = true;
        saveBtn.textContent = "Saving…";

        updateFieldAjax(
          fieldId,
          newValue,
          function () {
            // Success
            updateViewText(group, newValue);
            exitEditMode(group, false);
            showToast("\"" + fieldName + "\" saved.", "success");
            saveBtn.disabled = false;
            saveBtn.textContent = "Save";
          },
          function (errMsg) {
            // Error
            setFieldError(editRow, errMsg);
            showToast("Save failed: " + errMsg, "error");
            saveBtn.disabled = false;
            saveBtn.textContent = "Save";
          }
        );
      });
    });
  }

  // -------------------------------------------------------------------------
  // Legacy: wire up plain .abe-field-input inputs (for extra fields)
  // -------------------------------------------------------------------------
  function initFieldInputs() {
    document.querySelectorAll(".abe-field-input[data-field-id]").forEach(function (input) {
      var fieldId = parseInt(input.dataset.fieldId, 10);
      if (!fieldId) return;

      input.addEventListener("input", function () {
        input.classList.add("abe-unsaved");
      });

      input.addEventListener("blur", function () {
        if (input.classList.contains("abe-unsaved")) {
          updateFieldAjax(fieldId, input.value, function () {
            input.classList.add("abe-edited");
            input.classList.remove("abe-unsaved");
          }, function () {
            input.classList.remove("abe-unsaved");
          });
        }
      });

      input.addEventListener("change", function () {
        var hidden = document.getElementById("save-field-" + fieldId);
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
  // Save all button: flush inline edits to the hidden form then submit
  // -------------------------------------------------------------------------
  var btnSaveAll = document.getElementById("btn-save-all");
  if (btnSaveAll && saveForm) {
    btnSaveAll.addEventListener("click", function () {
      // Flush any currently-unsaved plain inputs via AJAX before submitting.
      var pending = document.querySelectorAll(".abe-field-input.abe-unsaved[data-field-id]");
      var promises = [];
      pending.forEach(function (input) {
        var fieldId = parseInt(input.dataset.fieldId, 10);
        if (fieldId) {
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
            }).catch(function () {})
          );
        }
      });
      Promise.all(promises).finally(function () {
        saveForm.submit();
      });
    });
  }

  // -------------------------------------------------------------------------
  // Boot
  // -------------------------------------------------------------------------
  initInlineEditors();
  initFieldInputs();
  loadPDF();
}());
