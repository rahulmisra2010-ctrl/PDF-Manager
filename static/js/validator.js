/**
 * validator.js — Smart Field Validator UI for the Live Address Book Editor.
 *
 * Workflow:
 *  1. On page load, fetch validation + suggestions from VALIDATE_URL (GET).
 *  2. Render summary, all-fields table, and issue cards with radio suggestions.
 *  3. On "Apply Selections", POST selections to APPLY_URL then redirect to editor.
 *
 * Depends on globals injected by validator.html:
 *   VALIDATE_URL  {string}  — GET endpoint (validate-and-suggest)
 *   APPLY_URL     {string}  — POST endpoint (apply-selections)
 *   CSRF_TOKEN    {string}  — Flask-WTF CSRF token
 *   EDITOR_URL    {string}  — URL of the address-book-live editor page
 */

/* global VALIDATE_URL, APPLY_URL, CSRF_TOKEN, EDITOR_URL */

(function () {
  "use strict";

  // -------------------------------------------------------------------------
  // Utility helpers
  // -------------------------------------------------------------------------
  function escHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function pct(n) {
    return Math.round((n || 0) * 100) + "%";
  }

  function statusBadgeHtml(status) {
    var map = {
      ok:         { cls: "vld-badge-ok",          label: "✓ OK" },
      blank:      { cls: "vld-badge-blank",        label: "⚠ Blank" },
      invalid:    { cls: "vld-badge-invalid",      label: "✗ Invalid" },
      suspicious: { cls: "vld-badge-suspicious",   label: "⚠ Suspicious" },
    };
    var s = map[status] || { cls: "vld-badge-ok", label: status };
    return '<span class="vld-badge ' + s.cls + '">' + s.label + "</span>";
  }

  // -------------------------------------------------------------------------
  // DOM references
  // -------------------------------------------------------------------------
  var loadingEl    = document.getElementById("validator-loading");
  var panelEl      = document.getElementById("validator-panel");
  var summaryEl    = document.getElementById("vld-summary");
  var issueSection = document.getElementById("vld-issues-section");
  var issuesList   = document.getElementById("vld-issues-list");
  var fieldsTbody  = document.getElementById("vld-fields-tbody");
  var btnApply     = document.getElementById("btn-apply");
  var applyStatus  = document.getElementById("vld-apply-status");

  // Holds the latest API response
  var apiData = null;

  // -------------------------------------------------------------------------
  // Render summary bar
  // -------------------------------------------------------------------------
  function renderSummary(data) {
    var total  = (data.extracted || []).length;
    var blanks = (data.blank_fields || []).length;
    var issues = (data.issues || []).length;
    var ok     = total - blanks - (issues - blanks > 0 ? issues - blanks : 0);
    if (ok < 0) ok = 0;

    summaryEl.innerHTML =
      '<div class="vld-summary-grid">' +
      '<div class="vld-summary-card vld-sum-ok"><div class="vld-sum-num">' + (total - issues) + '</div><div class="vld-sum-lbl">✓ OK</div></div>' +
      '<div class="vld-summary-card vld-sum-blank"><div class="vld-sum-num">' + blanks + '</div><div class="vld-sum-lbl">⚠ Blank</div></div>' +
      '<div class="vld-summary-card vld-sum-issue"><div class="vld-sum-num">' + issues + '</div><div class="vld-sum-lbl">Issues</div></div>' +
      '<div class="vld-summary-card vld-sum-total"><div class="vld-sum-num">' + total + '</div><div class="vld-sum-lbl">Total Fields</div></div>' +
      "</div>";
  }

  // -------------------------------------------------------------------------
  // Render all-fields table
  // -------------------------------------------------------------------------
  function renderFieldsTable(data) {
    var fields = data.fields || {};
    var rows = "";
    Object.keys(fields).forEach(function (fn) {
      var f = fields[fn];
      var confColor = f.confidence >= 0.85 ? "#198754" : f.confidence >= 0.65 ? "#fd7e14" : "#dc3545";
      rows +=
        "<tr>" +
        "<td><strong>" + escHtml(fn) + "</strong></td>" +
        "<td>" + (escHtml(f.value) || '<em class="text-muted">—</em>') + "</td>" +
        '<td><span style="color:' + confColor + '">' + pct(f.confidence) + "</span></td>" +
        "<td>" + statusBadgeHtml(f.status) + "</td>" +
        "</tr>";
    });
    fieldsTbody.innerHTML = rows || '<tr><td colspan="4" class="text-center text-muted">No fields found. Please extract fields first.</td></tr>';
  }

  // -------------------------------------------------------------------------
  // Render issue cards with radio-button suggestions
  // -------------------------------------------------------------------------
  function renderIssues(data) {
    var issues     = data.issues || [];
    var suggestions = data.suggestions || {};

    if (!issues.length) {
      issueSection.style.display = "none";
      return;
    }

    issueSection.style.display = "block";

    // Group issues by field name (deduplicate)
    var seen = {};
    var uniqueIssues = [];
    issues.forEach(function (iss) {
      if (!seen[iss.field_name]) {
        seen[iss.field_name] = true;
        uniqueIssues.push(iss);
      }
    });

    var html = "";
    uniqueIssues.forEach(function (iss, idx) {
      var fn    = iss.field_name;
      var sug   = suggestions[fn] || [];
      var typeLabel = iss.issue_type === "blank" ? "Blank" :
                      iss.issue_type === "invalid_format" ? "Invalid Format" : "Suspicious";
      var badgeCls  = iss.severity === "error" ? "vld-badge-invalid" : "vld-badge-blank";

      html += '<div class="vld-issue-card" data-field="' + escHtml(fn) + '">';
      html += '<div class="vld-issue-header">';
      html += '<span class="vld-issue-title">' + escHtml(fn) + '</span>';
      html += '<span class="vld-badge ' + badgeCls + ' ms-2">' + typeLabel + '</span>';
      html += '<small class="text-muted ms-2">' + escHtml(iss.message) + '</small>';
      html += '</div>';

      html += '<div class="vld-suggestions">';

      // Radio options from training / correction data
      sug.forEach(function (s, si) {
        var radioId = "radio-" + idx + "-" + si;
        var confColor = s.confidence >= 0.85 ? "#198754" : s.confidence >= 0.65 ? "#fd7e14" : "#dc3545";
        html += '<label class="vld-option" for="' + radioId + '">';
        html += '<input type="radio" id="' + radioId + '" name="sel-' + escHtml(fn) + '" value="' + escHtml(s.value) + '">';
        html += '<span class="vld-option-value">' + escHtml(s.value) + '</span>';
        html += '<span class="vld-option-meta">';
        html += '<span style="color:' + confColor + '">' + pct(s.confidence) + '</span>';
        html += ' · ' + escHtml(s.source);
        if (s.count > 1) html += ' · used ' + s.count + 'x';
        html += '</span>';
        html += '</label>';
      });

      // Manual entry option
      var manualId = "radio-" + idx + "-manual";
      html += '<label class="vld-option vld-option-manual" for="' + manualId + '">';
      html += '<input type="radio" id="' + manualId + '" name="sel-' + escHtml(fn) + '" value="__custom__">';
      html += '<span class="vld-option-value">Enter manually…</span>';
      html += '</label>';
      html += '<input type="text" class="vld-manual-input" data-field="' + escHtml(fn) + '" placeholder="Type value here…" style="display:none">';

      html += '</div>'; // .vld-suggestions
      html += '</div>'; // .vld-issue-card
    });

    issuesList.innerHTML = html;

    // Show/hide manual text input when "custom" radio is selected
    issuesList.querySelectorAll('input[type="radio"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        var card = radio.closest(".vld-issue-card");
        var manualInput = card.querySelector(".vld-manual-input");
        if (radio.value === "__custom__") {
          if (manualInput) {
            manualInput.style.display = "block";
            manualInput.focus();
          }
        } else {
          if (manualInput) {
            manualInput.style.display = "none";
          }
        }
      });
    });
  }

  // -------------------------------------------------------------------------
  // Collect selections from all issue cards
  // -------------------------------------------------------------------------
  function collectSelections() {
    var selections = {};
    if (!issuesList) return selections;

    issuesList.querySelectorAll(".vld-issue-card").forEach(function (card) {
      var fieldName = card.dataset.field;
      var checked = card.querySelector('input[type="radio"]:checked');
      if (!checked) return;

      var val = checked.value;
      if (val === "__custom__") {
        var manualInput = card.querySelector(".vld-manual-input");
        val = manualInput ? manualInput.value.trim() : "";
      }
      if (val) {
        selections[fieldName] = val;
      }
    });

    return selections;
  }

  // -------------------------------------------------------------------------
  // Fetch validation data and render
  // -------------------------------------------------------------------------
  function loadValidation() {
    fetch(VALIDATE_URL, {
      method: "GET",
      headers: { "X-CSRFToken": CSRF_TOKEN },
      credentials: "same-origin",
    })
      .then(function (r) {
        if (!r.ok) throw new Error("Server returned " + r.status);
        return r.json();
      })
      .then(function (data) {
        apiData = data;
        loadingEl.style.display = "none";
        panelEl.style.display = "block";
        renderSummary(data);
        renderFieldsTable(data);
        renderIssues(data);
      })
      .catch(function (err) {
        loadingEl.innerHTML =
          '<div class="vld-error"><i class="bi bi-exclamation-circle me-2"></i>' +
          "Failed to load validation results: " + escHtml(err.message) + "</div>";
      });
  }

  // -------------------------------------------------------------------------
  // Apply selections
  // -------------------------------------------------------------------------
  if (btnApply) {
    btnApply.addEventListener("click", function () {
      var selections = collectSelections();

      if (!Object.keys(selections).length) {
        applyStatus.textContent = "No selections made. Please choose a value for at least one field.";
        applyStatus.className = "vld-apply-status vld-status-warn";
        return;
      }

      btnApply.disabled = true;
      btnApply.innerHTML = '<span class="vld-spinner"></span> Applying…';
      applyStatus.textContent = "";
      applyStatus.className = "vld-apply-status";

      fetch(APPLY_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": CSRF_TOKEN,
        },
        credentials: "same-origin",
        body: JSON.stringify({ selections: selections }),
      })
        .then(function (r) {
          if (!r.ok) throw new Error("Server returned " + r.status);
          return r.json();
        })
        .then(function (data) {
          if (data.ok) {
            applyStatus.textContent =
              "✓ " + data.updated_count + " field(s) updated. Returning to editor…";
            applyStatus.className = "vld-apply-status vld-status-ok";
            setTimeout(function () {
              window.location.href = EDITOR_URL;
            }, 1200);
          } else {
            applyStatus.textContent = "Error: " + (data.error || "Unknown error");
            applyStatus.className = "vld-apply-status vld-status-error";
            btnApply.disabled = false;
            btnApply.innerHTML = '<i class="bi bi-check2-all me-1"></i>Apply Selections';
          }
        })
        .catch(function (err) {
          applyStatus.textContent = "Network error: " + err.message;
          applyStatus.className = "vld-apply-status vld-status-error";
          btnApply.disabled = false;
          btnApply.innerHTML = '<i class="bi bi-check2-all me-1"></i>Apply Selections';
        });
    });
  }

  // -------------------------------------------------------------------------
  // Boot
  // -------------------------------------------------------------------------
  loadValidation();
})();
