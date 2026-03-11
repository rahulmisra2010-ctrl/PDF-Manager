/**
 * static/js/validator.js
 * Handles the Validate & Suggest UI: runs validation, renders issues,
 * manages radio-button selections, updates the preview panel, and
 * submits apply_selections via AJAX.
 */

"use strict";

// ── DOM references ──────────────────────────────────────────────────────────
const btnRun      = document.getElementById("btn-run-validate");
const btnApply    = document.getElementById("btn-apply");
const loadingEl   = document.getElementById("vld-loading");
const summaryEl   = document.getElementById("vld-summary");
const summaryText = document.getElementById("vld-summary-text");
const issuesList  = document.getElementById("vld-issues-list");
const applySection = document.getElementById("vld-apply-section");
const alertEl     = document.getElementById("vld-alert");

// Track user selections: field_name → chosen value
const userSelections = {};

// ── Helpers ─────────────────────────────────────────────────────────────────

function setLoading(on) {
  loadingEl.style.display = on ? "flex" : "none";
  btnRun.disabled = on;
}

function showAlert(message, type = "danger") {
  alertEl.className = `vld-alert vld-alert-${type}`;
  alertEl.textContent = message;
  alertEl.style.display = "block";
  setTimeout(() => { alertEl.style.display = "none"; }, 5000);
}

function showAlertNode(node, type = "danger") {
  alertEl.className = `vld-alert vld-alert-${type}`;
  alertEl.replaceChildren(node);
  alertEl.style.display = "block";
  setTimeout(() => { alertEl.style.display = "none"; }, 5000);
}

function updatePreview(fieldName, value) {
  const rows = document.querySelectorAll(`.vld-preview-row[data-field="${CSS.escape(fieldName)}"]`);
  rows.forEach(row => {
    const span = row.querySelector(".vld-preview-value");
    if (span) span.textContent = value || "—";
  });
}

function severityIcon(severity) {
  if (severity === "blank")      return '<i class="bi bi-slash-circle text-danger me-1"></i>';
  if (severity === "format")     return '<i class="bi bi-exclamation-triangle text-warning me-1"></i>';
  if (severity === "suspicious") return '<i class="bi bi-question-circle text-info me-1"></i>';
  return "";
}

function confidenceBadge(confidence) {
  const pct = Math.round(confidence * 100);
  let cls = "vld-badge-low";
  if (pct >= 80) cls = "vld-badge-high";
  else if (pct >= 50) cls = "vld-badge-med";
  return `<span class="vld-badge ${cls}">${pct}%</span>`;
}

// ── Render issues + suggestions ─────────────────────────────────────────────

function renderResults(validation, suggestions) {
  const issues  = validation.issues || [];
  const summary = validation.summary || "";

  summaryText.textContent = summary;
  summaryEl.style.display = "block";

  if (issues.length === 0) {
    issuesList.innerHTML = `
      <div class="vld-all-ok">
        <i class="bi bi-check-circle-fill text-success me-2"></i>
        All fields passed validation.
      </div>`;
    applySection.style.display = "none";
    return;
  }

  // Group issues by field_name
  const byField = {};
  issues.forEach(issue => {
    (byField[issue.field_name] = byField[issue.field_name] || []).push(issue);
  });

  let html = "";
  Object.entries(byField).forEach(([fieldName, fieldIssues]) => {
    const fieldSuggestions = suggestions[fieldName] || [];
    const currentValue = (FIELDS.find(f => f.field_name === fieldName) || {}).value || "";

    html += `<div class="vld-field-card">`;
    html += `<div class="vld-field-card-header"><strong>${escapeHtml(fieldName)}</strong></div>`;

    // Issue list
    fieldIssues.forEach(issue => {
      html += `<div class="vld-issue-row">
        ${severityIcon(issue.severity)}
        <span class="vld-issue-msg">${escapeHtml(issue.message)}</span>
      </div>`;
    });

    // Suggestions (radio buttons)
    if (fieldSuggestions.length > 0 || currentValue) {
      html += `<div class="vld-suggestions">`;
      html += `<p class="vld-suggestions-label">Select a value:</p>`;

      // Option: keep current value
      if (currentValue) {
        const radioId = `opt-${sanitizeId(fieldName)}-current`;
        html += `<label class="vld-option" for="${radioId}">
          <input type="radio" name="sel-${sanitizeId(fieldName)}"
                 id="${radioId}" value="${escapeAttr(currentValue)}"
                 data-field="${escapeAttr(fieldName)}" class="vld-radio">
          <span class="vld-option-value">${escapeHtml(currentValue)}</span>
          <span class="vld-badge vld-badge-current">current</span>
        </label>`;
      }

      // Suggestions from training data
      fieldSuggestions.forEach((sugg, idx) => {
        const radioId = `opt-${sanitizeId(fieldName)}-${idx}`;
        html += `<label class="vld-option" for="${radioId}">
          <input type="radio" name="sel-${sanitizeId(fieldName)}"
                 id="${radioId}" value="${escapeAttr(sugg.value)}"
                 data-field="${escapeAttr(fieldName)}" class="vld-radio">
          <span class="vld-option-value">${escapeHtml(sugg.value)}</span>
          ${confidenceBadge(sugg.confidence)}
          <span class="vld-source">${escapeHtml(sugg.source)}</span>
        </label>`;
      });

      // Manual entry option
      const manualId = `opt-${sanitizeId(fieldName)}-manual`;
      html += `<label class="vld-option vld-option-manual" for="${manualId}">
        <input type="radio" name="sel-${sanitizeId(fieldName)}"
               id="${manualId}" value="__manual__"
               data-field="${escapeAttr(fieldName)}" class="vld-radio vld-radio-manual">
        <span>Enter manually:</span>
        <input type="text" class="vld-manual-input" id="manual-input-${sanitizeId(fieldName)}"
               placeholder="Type value…" data-field="${escapeAttr(fieldName)}">
      </label>`;

      html += `</div>`;
    }

    html += `</div>`; // .vld-field-card
  });

  issuesList.innerHTML = html;
  applySection.style.display = "block";

  // Wire up radio buttons
  document.querySelectorAll(".vld-radio").forEach(radio => {
    radio.addEventListener("change", onRadioChange);
  });

  // Wire up manual inputs
  document.querySelectorAll(".vld-manual-input").forEach(input => {
    input.addEventListener("input", onManualInput);
  });
}

function onRadioChange(event) {
  const radio     = event.target;
  const fieldName = radio.dataset.field;
  const value     = radio.value;

  if (value === "__manual__") {
    const manualInput = document.getElementById(`manual-input-${sanitizeId(fieldName)}`);
    userSelections[fieldName] = manualInput ? manualInput.value : "";
  } else {
    userSelections[fieldName] = value;
    updatePreview(fieldName, value);
  }
}

function onManualInput(event) {
  const input     = event.target;
  const fieldName = input.dataset.field;
  userSelections[fieldName] = input.value;
  updatePreview(fieldName, input.value);
}

// ── Run Validation ───────────────────────────────────────────────────────────

btnRun.addEventListener("click", async () => {
  setLoading(true);
  issuesList.innerHTML = "";
  summaryEl.style.display = "none";
  applySection.style.display = "none";

  try {
    const resp = await fetch(VALIDATE_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CSRF_TOKEN,
      },
      body: JSON.stringify({}),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `Server error ${resp.status}`);
    }
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || "Validation failed");

    renderResults(data.validation, data.suggestions || {});
  } catch (err) {
    showAlert(`Validation failed: ${err.message}`);
  } finally {
    setLoading(false);
  }
});

// ── Apply Selections ─────────────────────────────────────────────────────────

btnApply.addEventListener("click", async () => {
  if (Object.keys(userSelections).length === 0) {
    showAlert("Please select at least one value before applying.", "warning");
    return;
  }

  btnApply.disabled = true;
  btnApply.textContent = "Applying…";

  try {
    const resp = await fetch(APPLY_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CSRF_TOKEN,
      },
      body: JSON.stringify({ selections: userSelections }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `Server error ${resp.status}`);
    }
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || "Apply failed");

    // Build the success message safely (avoid XSS from server-supplied URL)
    const count = Number(data.updated_fields.length);
    const alertMsg = document.createElement("span");
    alertMsg.textContent = `${count} field(s) updated. `;
    const link = document.createElement("a");
    link.href = data.download_url;
    link.className = "vld-alert-link";
    link.textContent = "Download PDF";
    alertMsg.appendChild(link);
    showAlertNode(alertMsg, "success");
  } catch (err) {
    showAlert(`Apply failed: ${err.message}`);
  } finally {
    btnApply.disabled = false;
    btnApply.innerHTML = '<i class="bi bi-check2-circle me-1"></i>Apply Selected Values';
  }
});

// ── Utilities ────────────────────────────────────────────────────────────────

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(str) {
  return String(str).replace(/"/g, "&quot;");
}

function sanitizeId(str) {
  return String(str).replace(/[^a-zA-Z0-9_-]/g, "_");
}
