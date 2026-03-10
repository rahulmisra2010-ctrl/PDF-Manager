/**
 * train-me.js — "Train Me" validation UI for the Live Address Book Editor.
 *
 * Depends on globals injected by the Jinja2 template:
 *   DOC_ID        {number}  — database document id
 *   CSRF_TOKEN    {string}  — Flask-WTF CSRF token
 *   FIELDS        {Array}   — extracted field data from Flask
 *   TRAIN_ME_URL  {string}  — POST endpoint for Train Me
 */

/* global DOC_ID, CSRF_TOKEN, FIELDS, TRAIN_ME_URL */

(function () {
  "use strict";

  // -------------------------------------------------------------------------
  // Reference set to use (can be wired to a UI dropdown later)
  // -------------------------------------------------------------------------
  var DEFAULT_REFERENCE_SET = "mat_pdf_v1";

  // -------------------------------------------------------------------------
  // DOM references (created dynamically below)
  // -------------------------------------------------------------------------
  var btnTrainMe = document.getElementById("btn-train-me");
  var progressContainer = document.getElementById("train-me-progress");
  var modal = document.getElementById("train-me-modal");
  var modalOverlay = document.getElementById("train-me-modal-overlay");
  var modalClose = document.getElementById("train-me-modal-close");
  var modalBody = document.getElementById("train-me-modal-body");

  if (!btnTrainMe) return; // Guard: element must exist

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------
  function escHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function statusBadgeClass(status) {
    if (!status) return "tm-badge-pending";
    if (status.indexOf("\u2713") !== -1) return "tm-badge-validated";
    if (status.indexOf("\u2717") !== -1) return "tm-badge-correction";
    if (status.indexOf("\u26a0") !== -1) return "tm-badge-review";
    return "tm-badge-pending";
  }

  function scoreColor(score) {
    if (score >= 1.0) return "#198754";
    if (score >= 0.8) return "#fd7e14";
    return "#dc3545";
  }

  // -------------------------------------------------------------------------
  // Build progress bar
  // -------------------------------------------------------------------------
  function buildProgressBar(totalFields) {
    if (!progressContainer) return;
    progressContainer.innerHTML = "";
    progressContainer.style.display = "flex";

    for (var i = 0; i < totalFields; i++) {
      var cell = document.createElement("div");
      cell.className = "tm-progress-cell tm-progress-pending";
      cell.id = "tm-cell-" + i;
      cell.title = "Pending";
      progressContainer.appendChild(cell);
    }
  }

  function updateProgressCell(index, status) {
    var cell = document.getElementById("tm-cell-" + index);
    if (!cell) return;
    cell.className = "tm-progress-cell";
    if (status && status.indexOf("\u2713") !== -1) {
      cell.className += " tm-progress-validated";
      cell.title = "Validated";
    } else if (status && status.indexOf("\u2717") !== -1) {
      cell.className += " tm-progress-correction";
      cell.title = "Needs correction";
    } else if (status && status.indexOf("\u26a0") !== -1) {
      cell.className += " tm-progress-review";
      cell.title = "Needs review / blank";
    } else {
      cell.className += " tm-progress-pending";
      cell.title = "Pending";
    }
  }

  // -------------------------------------------------------------------------
  // Animate progress left → right
  // -------------------------------------------------------------------------
  function animateProgress(results, onDone) {
    var index = 0;

    function step() {
      if (index >= results.length) {
        if (onDone) onDone();
        return;
      }
      updateProgressCell(index, results[index].status);
      index++;
      setTimeout(step, 120);
    }

    step();
  }

  // -------------------------------------------------------------------------
  // Build validation results modal content
  // -------------------------------------------------------------------------
  function buildModalContent(data) {
    var meta = data.validation_metadata || {};
    var results = data.results || [];
    var ts = data.timestamp || "";

    var html = "";

    // Summary header
    html += '<div class="tm-modal-summary">';
    html += '<div class="tm-modal-ts"><i class="bi bi-clock me-1"></i>Validated: ' + escHtml(ts) + "</div>";
    html += '<div class="tm-modal-stats">';
    html += '<span class="tm-stat tm-stat-validated">\u2713 ' + (meta.validated || 0) + " validated</span>";
    html += '<span class="tm-stat tm-stat-correction">\u2717 ' + (meta.needs_correction || 0) + " need correction</span>";
    html += '<span class="tm-stat tm-stat-blank">\u26a0 ' + (meta.blank_fields || 0) + " blank</span>";
    html += '<span class="tm-stat tm-stat-accuracy">Accuracy: ' + Math.round((meta.accuracy || 0) * 100) + "%</span>";
    html += "</div>";
    html += "</div>";

    // Accuracy bar
    var accPct = Math.round((meta.accuracy || 0) * 100);
    html += '<div class="tm-accuracy-bar-wrap">';
    html += '<div class="tm-accuracy-bar" style="width:' + accPct + '%;background:' + scoreColor(meta.accuracy || 0) + '"></div>';
    html += "</div>";

    // Results table
    html += '<table class="tm-results-table">';
    html += "<thead><tr>";
    html += "<th>#</th><th>Field</th><th>Extracted</th><th>Reference</th><th>Status</th><th>Score</th><th>Action</th>";
    html += "</tr></thead><tbody>";

    results.forEach(function (r, idx) {
      var badgeCls = statusBadgeClass(r.status);
      html += "<tr>";
      html += "<td>" + r.position + "</td>";
      html += "<td><strong>" + escHtml(r.field_name) + "</strong></td>";
      html += "<td>" + (escHtml(r.extracted_value) || '<em class="text-muted">—</em>') + "</td>";
      html += "<td>" + (escHtml(r.reference_value) || '<em class="text-muted">—</em>') + "</td>";
      html += '<td><span class="tm-badge ' + badgeCls + '">' + escHtml(r.status) + "</span></td>";
      html +=
        '<td><span style="color:' +
        scoreColor(r.match_score) +
        '">' +
        Math.round((r.match_score || 0) * 100) +
        "%</span></td>";

      if (r.corrected && r.corrected_to !== undefined) {
        html +=
          '<td><button class="tm-apply-btn able-btn able-btn-success" ' +
          'data-field-id="' + escHtml(r.field_id) + '" ' +
          'data-corrected-to="' + escHtml(r.corrected_to) + '" ' +
          'title="Apply correction: ' + escHtml(r.corrected_to) + '">' +
          "Accept &amp; Apply</button></td>";
      } else {
        html += "<td>—</td>";
      }

      html += "</tr>";
    });

    html += "</tbody></table>";

    return html;
  }

  // -------------------------------------------------------------------------
  // Apply a single correction to the editor overlay + save form
  // -------------------------------------------------------------------------
  function applyCorrection(fieldId, correctedValue) {
    // Update overlay input
    var overlayInput = document.querySelector(
      '.able-field-input[data-field-id="' + fieldId + '"]'
    );
    if (overlayInput) {
      overlayInput.value = correctedValue;
      overlayInput.classList.add("able-edited");
      overlayInput.classList.remove("able-unsaved");
    }

    // Update hidden save-form input
    var hiddenInput = document.getElementById("save-field-" + fieldId);
    if (hiddenInput) {
      hiddenInput.value = correctedValue;
    }

    // Persist via AJAX if UPDATE_URL is defined
    if (typeof UPDATE_URL !== "undefined" && fieldId) {
      fetch(UPDATE_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": CSRF_TOKEN,
        },
        body: JSON.stringify({ field_id: parseInt(fieldId, 10), value: correctedValue }),
      }).catch(function (err) {
        console.error("Train Me: field correction AJAX failed:", err);
      });
    }
  }

  // -------------------------------------------------------------------------
  // Show modal
  // -------------------------------------------------------------------------
  function showModal(data) {
    if (!modal || !modalBody) return;
    modalBody.innerHTML = buildModalContent(data);
    modal.style.display = "flex";
    if (modalOverlay) modalOverlay.style.display = "block";

    // Wire "Accept & Apply" buttons
    var applyBtns = modalBody.querySelectorAll(".tm-apply-btn");
    applyBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var fieldId = btn.dataset.fieldId;
        var correctedTo = btn.dataset.correctedTo;
        applyCorrection(fieldId, correctedTo);
        btn.textContent = "\u2713 Applied";
        btn.disabled = true;
        btn.classList.remove("able-btn-success");
        btn.classList.add("able-btn-secondary");
      });
    });
  }

  function hideModal() {
    if (modal) modal.style.display = "none";
    if (modalOverlay) modalOverlay.style.display = "none";
  }

  // -------------------------------------------------------------------------
  // Close modal handlers
  // -------------------------------------------------------------------------
  if (modalClose) {
    modalClose.addEventListener("click", hideModal);
  }
  if (modalOverlay) {
    modalOverlay.addEventListener("click", hideModal);
  }
  document.addEventListener("keydown", function (evt) {
    if (evt.key === "Escape") hideModal();
  });

  // -------------------------------------------------------------------------
  // Collect current field values from the overlay inputs or FIELDS array
  // -------------------------------------------------------------------------
  function collectFields() {
    var collected = [];
    if (typeof FIELDS === "undefined" || !FIELDS.length) return collected;

    FIELDS.forEach(function (f) {
      var val = f.value || "";
      // Prefer the current value from the overlay input if present
      var overlayInput = document.querySelector(
        '.able-field-input[data-field-id="' + f.id + '"]'
      );
      if (overlayInput) val = overlayInput.value;

      collected.push({
        field_id: f.id,
        field_name: f.field_name,
        value: val,
      });
    });

    return collected;
  }

  // -------------------------------------------------------------------------
  // Main: start validation
  // -------------------------------------------------------------------------
  function startValidation() {
    if (!btnTrainMe || btnTrainMe.disabled) return;

    var fields = collectFields();
    if (!fields.length) {
      alert("No fields found. Please extract fields first.");
      return;
    }

    // Disable button + show spinner
    btnTrainMe.disabled = true;
    btnTrainMe.innerHTML =
      '<span class="tm-spinner"></span> Validating…';

    // Build/show progress bar
    buildProgressBar(fields.length);

    var payload = {
      reference_set: DEFAULT_REFERENCE_SET,
      fields: fields,
    };

    fetch(TRAIN_ME_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CSRF_TOKEN,
      },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data.results) {
          animateProgress(data.results, function () {
            showModal(data);
          });
        } else {
          alert("Validation failed: " + (data.error || "Unknown error"));
        }
      })
      .catch(function (err) {
        console.error("Train Me request failed:", err);
        alert("Network error during validation. Please try again.");
      })
      .finally(function () {
        btnTrainMe.disabled = false;
        btnTrainMe.innerHTML =
          '<i class="bi bi-mortarboard-fill me-1"></i>Train Me';
      });
  }

  // -------------------------------------------------------------------------
  // Wire Train Me button
  // -------------------------------------------------------------------------
  btnTrainMe.addEventListener("click", startValidation);
})();
