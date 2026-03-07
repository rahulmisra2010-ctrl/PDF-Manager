/**
 * pdf-editor.js — Live PDF Editor frontend logic.
 *
 * Depends on:
 *   - PDF.js 3.x (loaded from CDN before this script)
 *   - Global variables injected by the Flask template:
 *       PDF_URL, DOC_ID, CSRF_TOKEN, FIELDS, DEMO_BOXES, UPDATE_URL
 */
"use strict";

/* ──────────────────────────────────────────────────────────────────────────
   PDF.js worker
────────────────────────────────────────────────────────────────────────── */
pdfjsLib.GlobalWorkerOptions.workerSrc =
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

/* ──────────────────────────────────────────────────────────────────────────
   DOM references
────────────────────────────────────────────────────────────────────────── */
const canvas        = document.getElementById("lpe-pdf-canvas");
const ctx           = canvas.getContext("2d");
const wrapper       = document.getElementById("lpe-pdf-wrapper");
const scrollArea    = document.getElementById("lpe-pdf-scroll");
const statusEl      = document.getElementById("lpe-render-status");
const pageTotalEl   = document.getElementById("page-total");
const pageInput     = document.getElementById("page-input");
const zoomInput     = document.getElementById("zoom-input");
const btnPrev       = document.getElementById("btn-prev");
const btnNext       = document.getElementById("btn-next");
const btnZoomIn     = document.getElementById("btn-zoom-in");
const btnZoomOut    = document.getElementById("btn-zoom-out");
const btnZoomFit    = document.getElementById("btn-zoom-fit");
const btnSaveAll    = document.getElementById("btn-save-all");
const saveForm      = document.getElementById("lpe-save-form");

// Right panel
const editPlaceholder = document.getElementById("lpe-edit-placeholder");
const editFormDiv     = document.getElementById("lpe-edit-form");
const editFieldName   = document.getElementById("lpe-edit-field-name");
const editMeta        = document.getElementById("lpe-edit-meta");
const editTextarea    = document.getElementById("lpe-edit-textarea");
const editOrig        = document.getElementById("lpe-edit-orig");
const editOrigValue   = document.getElementById("lpe-edit-orig-value");
const btnApply        = document.getElementById("lpe-edit-apply");
const btnReset        = document.getElementById("lpe-edit-reset");

// Popup
const popup       = document.getElementById("lpe-popup");
const popupTitle  = document.getElementById("lpe-popup-title");
const popupInput  = document.getElementById("lpe-popup-input");
const popupApply  = document.getElementById("lpe-popup-apply");
const popupCancel = document.getElementById("lpe-popup-cancel");
const popupClose  = document.getElementById("lpe-popup-close");

// Field list
const fieldListEl = document.getElementById("lpe-field-list");

/* ──────────────────────────────────────────────────────────────────────────
   State
────────────────────────────────────────────────────────────────────────── */
let pdfDoc      = null;
let pageNum     = 1;
let scale       = 1.0;
let rendering   = false;
let pendingPage = null;

/** Currently selected field object (from FIELDS array). */
let activeField   = null;
/** Currently active overlay element. */
let activeOverlay = null;

/* ──────────────────────────────────────────────────────────────────────────
   Bounding box helper
────────────────────────────────────────────────────────────────────────── */
function getBox(field) {
  if (field.bbox && field.bbox.x !== null) {
    return {
      page: field.page_number || 1,
      x: field.bbox.x,
      y: field.bbox.y,
      w: field.bbox.width,
      h: field.bbox.height,
    };
  }
  return DEMO_BOXES[field.field_name] || null;
}

function fieldsOnPage(page) {
  return FIELDS.filter(f => {
    const box = getBox(f);
    return box && box.page === page;
  });
}

/* ──────────────────────────────────────────────────────────────────────────
   PDF rendering
────────────────────────────────────────────────────────────────────────── */
async function renderPage(num) {
  if (rendering) {
    pendingPage = num;
    return;
  }
  rendering = true;
  pageNum = num;
  pageInput.value = num;
  btnPrev.disabled = num <= 1;
  btnNext.disabled = num >= pdfDoc.numPages;
  statusEl.textContent = "Rendering page " + num + "…";

  try {
    const page     = await pdfDoc.getPage(num);
    const viewport = page.getViewport({ scale });

    canvas.width  = viewport.width;
    canvas.height = viewport.height;

    wrapper.style.width  = viewport.width  + "px";
    wrapper.style.height = viewport.height + "px";

    await page.render({ canvasContext: ctx, viewport }).promise;
    statusEl.textContent = num + " / " + pdfDoc.numPages + " page(s)";

    drawOverlays(num, viewport.width, viewport.height);
  } catch (err) {
    statusEl.textContent = "Render error: " + err.message;
    console.error("PDF render error:", err);
  }

  rendering = false;

  if (pendingPage !== null) {
    const next = pendingPage;
    pendingPage = null;
    await renderPage(next);
  }
}

/* ──────────────────────────────────────────────────────────────────────────
   Field highlight overlays
────────────────────────────────────────────────────────────────────────── */
function drawOverlays(page, canvasW, canvasH) {
  // Remove previous overlays
  wrapper.querySelectorAll(".lpe-highlight").forEach(el => el.remove());
  closePopup();

  const pageFields = fieldsOnPage(page);
  if (!pageFields.length) return;

  pageFields.forEach(field => {
    const box = getBox(field);
    if (!box) return;

    const el = document.createElement("div");
    el.className       = "lpe-highlight";
    el.dataset.fieldId = field.id;
    el.style.left      = (box.x * canvasW) + "px";
    el.style.top       = (box.y * canvasH) + "px";
    el.style.width     = (box.w * canvasW) + "px";
    el.style.height    = (box.h * canvasH) + "px";

    // Label above the overlay
    const label = document.createElement("div");
    label.className   = "lpe-highlight-label";
    label.textContent = field.field_name;
    el.appendChild(label);

    // Click → open popup + activate right panel
    el.addEventListener("click", e => {
      e.stopPropagation();
      selectField(field, el);
      openPopup(e, field, el);
    });

    wrapper.appendChild(el);

    // Mark overlay if already active
    if (activeField && activeField.id === field.id) {
      el.classList.add("lpe-active");
      activeOverlay = el;
    }
  });
}

/* ──────────────────────────────────────────────────────────────────────────
   Field selection (left panel + right panel sync)
────────────────────────────────────────────────────────────────────────── */
function selectField(field, overlayEl) {
  activeField = field;

  // Highlight in left list
  if (fieldListEl) {
    fieldListEl.querySelectorAll(".lpe-field-item").forEach(li => {
      li.classList.remove("lpe-active");
    });
    const li = fieldListEl.querySelector(
      `.lpe-field-item[data-field-id="${field.id}"]`
    );
    if (li) {
      li.classList.add("lpe-active");
      li.scrollIntoView({ block: "nearest" });
    }
  }

  // Remove previous overlay active state
  if (activeOverlay && activeOverlay !== overlayEl) {
    activeOverlay.classList.remove("lpe-active");
  }
  if (overlayEl) {
    overlayEl.classList.add("lpe-active");
  }
  activeOverlay = overlayEl || null;

  // Populate right panel
  showEditPanel(field);
}

function showEditPanel(field) {
  if (!editPlaceholder || !editFormDiv) return;

  editPlaceholder.style.display = "none";
  editFormDiv.style.display     = "flex";

  editFieldName.textContent = field.field_name;
  editMeta.textContent =
    "Page " + (field.page_number || 1) +
    " · Confidence " + (field.confidence * 100).toFixed(0) + "%" +
    (field.is_edited ? " · edited" : "");

  editTextarea.value = field.value || "";

  if (field.is_edited && field.original_value) {
    editOrig.style.display = "block";
    editOrigValue.textContent = field.original_value;
  } else {
    editOrig.style.display = "none";
  }
}

/* ──────────────────────────────────────────────────────────────────────────
   Right panel Apply / Reset
────────────────────────────────────────────────────────────────────────── */
btnApply && btnApply.addEventListener("click", () => {
  if (!activeField) return;
  applyFieldValue(activeField, editTextarea.value);
});

btnReset && btnReset.addEventListener("click", () => {
  if (!activeField) return;
  const original = activeField.original_value || "";
  editTextarea.value = original;
  applyFieldValue(activeField, original);
});

/* ──────────────────────────────────────────────────────────────────────────
   Inline popup editor (on PDF canvas)
────────────────────────────────────────────────────────────────────────── */
function openPopup(e, field, overlayEl) {
  popupTitle.textContent = field.field_name;
  popupInput.value       = field.value || "";

  // Position near the overlay element, inside scrollArea
  const wRect  = wrapper.getBoundingClientRect();
  const oRect  = overlayEl.getBoundingClientRect();
  const relTop  = oRect.bottom - wRect.top + 6;
  const relLeft = oRect.left   - wRect.left;

  popup.style.top     = relTop  + "px";
  popup.style.left    = relLeft + "px";
  popup.style.display = "block";

  // Clamp to visible area
  requestAnimationFrame(() => {
    const pRect  = popup.getBoundingClientRect();
    const sRect  = scrollArea.getBoundingClientRect();
    if (pRect.right > sRect.right) {
      popup.style.left = (relLeft - (pRect.right - sRect.right) - 8) + "px";
    }
    if (pRect.bottom > sRect.bottom) {
      popup.style.top = (relTop - overlayEl.offsetHeight - popup.offsetHeight - 12) + "px";
    }
  });

  popupInput.focus();
  popupInput.select();
}

function closePopup() {
  popup.style.display = "none";
}

function applyPopup() {
  if (!activeField) { closePopup(); return; }
  applyFieldValue(activeField, popupInput.value);
  closePopup();
}

popupApply  && popupApply.addEventListener("click",  applyPopup);
popupCancel && popupCancel.addEventListener("click",  closePopup);
popupClose  && popupClose.addEventListener("click",  closePopup);
popupInput  && popupInput.addEventListener("keydown", e => {
  if (e.key === "Enter")  applyPopup();
  if (e.key === "Escape") closePopup();
});

// Close popup on outside click
document.addEventListener("click", e => {
  if (popup.style.display === "block" &&
      !popup.contains(e.target) &&
      !e.target.closest(".lpe-highlight")) {
    closePopup();
  }
});

/* ──────────────────────────────────────────────────────────────────────────
   Apply a new value to a field (updates in-memory + hidden save form + AJAX)
────────────────────────────────────────────────────────────────────────── */
function applyFieldValue(field, newValue) {
  const stringValue = String(newValue).trim();
  field.value = stringValue;

  // Sync to the hidden save form
  const hiddenInput = document.getElementById("save-field-" + field.id);
  if (hiddenInput) hiddenInput.value = stringValue;

  // Update left-panel list item value
  if (fieldListEl) {
    const li = fieldListEl.querySelector(
      `.lpe-field-item[data-field-id="${field.id}"]`
    );
    if (li) {
      const valEl = li.querySelector(".lpe-field-value");
      if (valEl) valEl.textContent = stringValue || "—";
      li.classList.add("lpe-field-edited");
    }
  }

  // Refresh right panel if this is the active field
  if (activeField && activeField.id === field.id) {
    editTextarea.value = stringValue;
  }

  // Persist to server via AJAX (fire-and-forget; errors are logged)
  persistField(field.id, stringValue);
}

async function persistField(fieldId, value) {
  try {
    const resp = await fetch(UPDATE_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken":  CSRF_TOKEN,
      },
      body: JSON.stringify({ field_id: fieldId, value }),
    });
    if (!resp.ok) {
      console.warn("Field update returned", resp.status);
    }
  } catch (err) {
    console.error("Field update failed:", err);
  }
}

/* ──────────────────────────────────────────────────────────────────────────
   Left panel — field list click handler
────────────────────────────────────────────────────────────────────────── */
if (fieldListEl) {
  fieldListEl.addEventListener("click", e => {
    const li = e.target.closest(".lpe-field-item");
    if (!li) return;
    const fieldId = parseInt(li.dataset.fieldId, 10);
    const field   = FIELDS.find(f => f.id === fieldId);
    if (!field) return;

    // Navigate to that field's page
    const box = getBox(field);
    const targetPage = (box && box.page) ? box.page : (field.page_number || 1);

    if (targetPage !== pageNum) {
      renderPage(targetPage).then(() => {
        const overlay = wrapper.querySelector(
          `.lpe-highlight[data-field-id="${fieldId}"]`
        );
        selectField(field, overlay);
      });
    } else {
      const overlay = wrapper.querySelector(
        `.lpe-highlight[data-field-id="${fieldId}"]`
      );
      selectField(field, overlay);
    }
  });

  // Keyboard support
  fieldListEl.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") {
      const li = e.target.closest(".lpe-field-item");
      if (li) li.click();
    }
  });
}

/* ──────────────────────────────────────────────────────────────────────────
   Save button — sync all FIELDS values into hidden form then submit
────────────────────────────────────────────────────────────────────────── */
btnSaveAll && btnSaveAll.addEventListener("click", () => {
  FIELDS.forEach(f => {
    const inp = document.getElementById("save-field-" + f.id);
    if (inp) inp.value = f.value || "";
  });
  if (saveForm) saveForm.submit();
});

/* ──────────────────────────────────────────────────────────────────────────
   PDF navigation
────────────────────────────────────────────────────────────────────────── */
btnPrev && btnPrev.addEventListener("click", () => {
  if (pageNum > 1) renderPage(pageNum - 1);
});
btnNext && btnNext.addEventListener("click", () => {
  if (pageNum < pdfDoc.numPages) renderPage(pageNum + 1);
});
pageInput && pageInput.addEventListener("change", () => {
  const n = parseInt(pageInput.value, 10);
  if (!isNaN(n) && n >= 1 && n <= pdfDoc.numPages) renderPage(n);
});

/* ──────────────────────────────────────────────────────────────────────────
   Zoom
────────────────────────────────────────────────────────────────────────── */
function setZoom(newScale) {
  scale = Math.min(4.0, Math.max(0.25, newScale));
  zoomInput.value = Math.round(scale * 100);
  renderPage(pageNum);
}

zoomInput && zoomInput.addEventListener("change", () => {
  const n = parseInt(zoomInput.value, 10);
  if (!isNaN(n)) setZoom(n / 100);
});
btnZoomIn  && btnZoomIn.addEventListener("click",  () => setZoom(scale + 0.25));
btnZoomOut && btnZoomOut.addEventListener("click", () => setZoom(scale - 0.25));
btnZoomFit && btnZoomFit.addEventListener("click", () => {
  if (!pdfDoc) return;
  pdfDoc.getPage(pageNum).then(page => {
    const vp = page.getViewport({ scale: 1 });
    const avail = scrollArea.clientWidth - 32;
    setZoom(Math.max(0.25, avail / vp.width));
  });
});

/* ──────────────────────────────────────────────────────────────────────────
   Load PDF
────────────────────────────────────────────────────────────────────────── */
pdfjsLib.getDocument(PDF_URL).promise.then(pdf => {
  pdfDoc = pdf;
  pageTotalEl.textContent = pdf.numPages;
  pageInput.max           = pdf.numPages;
  btnNext.disabled        = pdf.numPages <= 1;

  // Auto-fit width on first load
  pdf.getPage(1).then(page => {
    const vp    = page.getViewport({ scale: 1 });
    const avail = scrollArea.clientWidth - 32;
    scale       = Math.max(0.25, avail / vp.width);
    zoomInput.value = Math.round(scale * 100);
    renderPage(1);
  });
}).catch(err => {
  statusEl.textContent = "Failed to load PDF: " + err.message;
  statusEl.style.color = "#f88";
  console.error("PDF.js load error:", err);
});
