import React, { useState, useRef, useEffect, useCallback } from 'react';

/**
 * SpreadsheetEditor component.
 *
 * Renders extracted PDF fields in a spreadsheet-like grid where every cell is
 * editable.  Supports:
 *   • Keyboard navigation  – Tab / Shift-Tab / Enter / Arrow keys
 *   • Clipboard paste      – Ctrl+V pastes TSV/CSV data from Excel or Google Sheets
 *   • Clipboard copy       – "Copy All" exports the grid as TSV
 *   • Add / Delete rows    – manage the field list inline
 *
 * Props:
 *   fields   {Array}    – initial array of ExtractedField objects
 *   onChange {Function} – called with the updated fields array on every change
 */
function SpreadsheetEditor({ fields, onChange }) {
  const [rows, setRows] = useState(() => fields.map((f) => ({ ...f })));
  const [focusTarget, setFocusTarget] = useState(null);
  const tableRef = useRef(null);

  // Columns the user may edit (in tab-order)
  const EDITABLE_COLS = ['field_name', 'value', 'page_number'];

  // Notify parent whenever rows change
  const notifyParent = useCallback(
    (updatedRows) => {
      onChange(updatedRows);
    },
    [onChange]
  );

  const updateRows = useCallback(
    (updater) => {
      setRows((prev) => {
        const next = typeof updater === 'function' ? updater(prev) : updater;
        notifyParent(next);
        return next;
      });
    },
    [notifyParent]
  );

  // ── Cell change ─────────────────────────────────────────────────────────
  const handleCellChange = (rowIdx, colKey, value) => {
    updateRows((prev) =>
      prev.map((r, i) => (i === rowIdx ? { ...r, [colKey]: value } : r))
    );
  };

  // ── Add / Delete rows ────────────────────────────────────────────────────
  const handleAddRow = () => {
    updateRows((prev) => [
      ...prev,
      { field_name: '', value: '', confidence: 1.0, page_number: 1 },
    ]);
  };

  const handleDeleteRow = (rowIdx) => {
    updateRows((prev) => prev.filter((_, i) => i !== rowIdx));
  };

  // ── Clipboard paste ──────────────────────────────────────────────────────
  /**
   * Handles Ctrl+V on a cell.
   * If the clipboard contains tab- or newline-delimited text (TSV from
   * Excel / Google Sheets), parse it as a grid and fill cells starting at
   * the current (rowIdx, colKey) position.  Single plain-text values fall
   * through to the browser's default paste.
   */
  const handlePaste = (e, rowIdx, colKey) => {
    const raw = e.clipboardData.getData('text/plain');
    const hasGrid = raw.includes('\t') || raw.includes('\n');
    if (!hasGrid) return; // let browser handle simple single-value paste

    e.preventDefault();

    const lines = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trimEnd().split('\n');
    const grid = lines.map((line) => line.split('\t'));
    const startColIdx = EDITABLE_COLS.indexOf(colKey);

    updateRows((prev) => {
      const updated = prev.map((r) => ({ ...r }));

      grid.forEach((cells, lineOffset) => {
        const targetRow = rowIdx + lineOffset;

        // Grow the row array if needed
        while (updated.length <= targetRow) {
          updated.push({ field_name: '', value: '', confidence: 1.0, page_number: 1 });
        }

        cells.forEach((cellValue, cellOffset) => {
          const targetColIdx = startColIdx + cellOffset;
          if (targetColIdx >= EDITABLE_COLS.length) return;
          const col = EDITABLE_COLS[targetColIdx];
          const trimmed = cellValue.trim();
          updated[targetRow] = {
            ...updated[targetRow],
            [col]:
              col === 'page_number'
                ? parseInt(trimmed, 10) || 1
                : trimmed,
          };
        });
      });

      return updated;
    });
  };

  // ── Copy all to clipboard (TSV) ──────────────────────────────────────────
  const handleCopyAll = () => {
    const header = 'Field Name\tValue\tConfidence\tPage';
    const body = rows.map(
      (r) =>
        `${r.field_name}\t${r.value}\t${(r.confidence * 100).toFixed(1)}%\t${r.page_number}`
    );
    const tsv = [header, ...body].join('\n');

    const fallback = () => {
      try {
        const el = document.createElement('textarea');
        el.value = tsv;
        document.body.appendChild(el);
        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);
      } catch (err) {
        console.warn('PDF Manager: copy to clipboard failed', err);
      }
    };

    if (navigator.clipboard) {
      navigator.clipboard.writeText(tsv).catch(fallback);
    } else {
      fallback();
    }
  };

  // ── Keyboard navigation ──────────────────────────────────────────────────
  const focusCell = useCallback((rowIdx, colKey) => {
    setFocusTarget({ row: rowIdx, col: colKey });
  }, []);

  // Apply focus after render whenever focusTarget changes
  useEffect(() => {
    if (!focusTarget || !tableRef.current) return;
    const el = tableRef.current.querySelector(
      `[data-row="${focusTarget.row}"][data-col="${focusTarget.col}"]`
    );
    el?.focus();
    setFocusTarget(null);
  }, [focusTarget]);

  const handleKeyDown = (e, rowIdx, colKey) => {
    const colIdx = EDITABLE_COLS.indexOf(colKey);

    if (e.key === 'Tab') {
      e.preventDefault();
      if (e.shiftKey) {
        // Move backwards
        if (colIdx > 0) {
          focusCell(rowIdx, EDITABLE_COLS[colIdx - 1]);
        } else if (rowIdx > 0) {
          focusCell(rowIdx - 1, EDITABLE_COLS[EDITABLE_COLS.length - 1]);
        }
      } else {
        // Move forwards
        if (colIdx < EDITABLE_COLS.length - 1) {
          focusCell(rowIdx, EDITABLE_COLS[colIdx + 1]);
        } else if (rowIdx < rows.length - 1) {
          focusCell(rowIdx + 1, EDITABLE_COLS[0]);
        } else {
          // Past the last cell – add a new row and move focus to its first column.
          // Both state updates happen in the same React 18 batch so the new row
          // is in the DOM before the focus effect fires.
          setRows((prev) => {
            const next = [
              ...prev,
              { field_name: '', value: '', confidence: 1.0, page_number: 1 },
            ];
            notifyParent(next);
            return next;
          });
          setFocusTarget({ row: rowIdx + 1, col: EDITABLE_COLS[0] });
        }
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (rowIdx < rows.length - 1) {
        focusCell(rowIdx + 1, colKey);
      }
    } else if (e.key === 'ArrowDown' && !e.shiftKey) {
      if (rowIdx < rows.length - 1) {
        e.preventDefault();
        focusCell(rowIdx + 1, colKey);
      }
    } else if (e.key === 'ArrowUp' && !e.shiftKey) {
      if (rowIdx > 0) {
        e.preventDefault();
        focusCell(rowIdx - 1, colKey);
      }
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="spreadsheet-editor">
      <div className="sheet-toolbar">
        <span className="sheet-hint">
          💡 <kbd>Tab</kbd> / <kbd>Enter</kbd> to navigate &nbsp;·&nbsp;
          <kbd>Ctrl+V</kbd> to paste from Excel / Google Sheets
        </span>
        <div className="sheet-toolbar-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleCopyAll}
            title="Copy all rows as TSV"
          >
            📋 Copy All
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleAddRow}
            title="Add a new empty row"
          >
            ➕ Add Row
          </button>
        </div>
      </div>

      <div className="sheet-scroll">
        <table className="data-table sheet-table" ref={tableRef}>
          <thead>
            <tr>
              <th className="col-num">#</th>
              <th>Field Name</th>
              <th>Value</th>
              <th>Confidence</th>
              <th className="col-page">Page</th>
              <th className="col-action"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIdx) => (
              <tr key={rowIdx} className="sheet-row">
                <td className="col-num row-num">{rowIdx + 1}</td>

                {/* Field Name */}
                <td>
                  <input
                    type="text"
                    className="sheet-input"
                    value={row.field_name}
                    data-row={rowIdx}
                    data-col="field_name"
                    onChange={(e) =>
                      handleCellChange(rowIdx, 'field_name', e.target.value)
                    }
                    onPaste={(e) => handlePaste(e, rowIdx, 'field_name')}
                    onKeyDown={(e) => handleKeyDown(e, rowIdx, 'field_name')}
                    aria-label={`Row ${rowIdx + 1} field name`}
                  />
                </td>

                {/* Value */}
                <td>
                  <input
                    type="text"
                    className="sheet-input"
                    value={String(row.value)}
                    data-row={rowIdx}
                    data-col="value"
                    onChange={(e) =>
                      handleCellChange(rowIdx, 'value', e.target.value)
                    }
                    onPaste={(e) => handlePaste(e, rowIdx, 'value')}
                    onKeyDown={(e) => handleKeyDown(e, rowIdx, 'value')}
                    aria-label={`Row ${rowIdx + 1} value`}
                  />
                </td>

                {/* Confidence (read-only) */}
                <td>
                  <span
                    className={`confidence ${
                      row.confidence >= 0.9
                        ? 'high'
                        : row.confidence >= 0.75
                        ? 'medium'
                        : 'low'
                    }`}
                  >
                    {(row.confidence * 100).toFixed(1)}%
                  </span>
                </td>

                {/* Page */}
                <td className="col-page">
                  <input
                    type="number"
                    className="sheet-input sheet-input-sm"
                    value={row.page_number}
                    min="1"
                    data-row={rowIdx}
                    data-col="page_number"
                    onChange={(e) =>
                      handleCellChange(
                        rowIdx,
                        'page_number',
                        parseInt(e.target.value, 10) || 1
                      )
                    }
                    onPaste={(e) => handlePaste(e, rowIdx, 'page_number')}
                    onKeyDown={(e) => handleKeyDown(e, rowIdx, 'page_number')}
                    aria-label={`Row ${rowIdx + 1} page number`}
                  />
                </td>

                {/* Delete */}
                <td className="col-action">
                  <button
                    type="button"
                    className="btn-icon btn-delete"
                    onClick={() => handleDeleteRow(rowIdx)}
                    aria-label={`Delete row ${rowIdx + 1}`}
                    title="Delete this row"
                  >
                    🗑
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {rows.length === 0 && (
        <p className="empty-state">
          No fields yet. Click <strong>➕ Add Row</strong> to add one, or
          paste data from Excel / Google Sheets.
        </p>
      )}
    </div>
  );
}

export default SpreadsheetEditor;
