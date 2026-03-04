import React, { useState, useCallback } from 'react';
import { editData } from '../services/api';
import SpreadsheetEditor from './SpreadsheetEditor';

/**
 * EditData component.
 * Wraps SpreadsheetEditor to provide full spreadsheet-style editing for all
 * extracted fields.  Supports:
 *   – Inline cell editing (field name, value, page)
 *   – Paste from Excel / Google Sheets (Ctrl+V)
 *   – Copy all data to clipboard as TSV
 *   – Add / delete rows
 *   – Save changes back to the backend → regenerate / export PDF
 *
 * Props:
 *   document    - { documentId, filename }
 *   extraction  - ExtractionResult
 *   onSave(updatedExtraction) - called after successful save
 *   onCancel()  - called when user discards changes
 */
function EditData({ document, extraction, onSave, onCancel }) {
  const [fields, setFields] = useState(
    extraction.fields.map((f) => ({ ...f }))
  );
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');

  // SpreadsheetEditor calls this whenever any cell changes
  const handleSheetChange = useCallback((updatedFields) => {
    setFields(updatedFields);
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setError('');
    try {
      await editData(document.documentId, fields);
      onSave({ ...extraction, fields });
    } catch (err) {
      setError(err.message || 'Save failed. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="edit-data">
      <h2>✏️ Edit Extracted Data</h2>
      <p className="edit-subtitle">Document: {document.filename}</p>

      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      <SpreadsheetEditor fields={fields} onChange={handleSheetChange} />

      <div className="action-bar">
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSave}
          disabled={isSaving}
          aria-busy={isSaving}
        >
          {isSaving ? 'Saving…' : '💾 Save Changes'}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onCancel}
          disabled={isSaving}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export default EditData;
