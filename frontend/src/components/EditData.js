import React, { useState } from 'react';
import { editData } from '../services/api';

/**
 * EditData component.
 * Provides an inline editor for all extracted fields.
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

  const handleFieldChange = (index, newValue) => {
    setFields((prev) =>
      prev.map((f, i) => (i === index ? { ...f, value: newValue } : f))
    );
  };

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

      {error && <p className="error-message" role="alert">{error}</p>}

      {fields.length === 0 ? (
        <p className="empty-state">No fields to edit.</p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSave();
          }}
          aria-label="Edit extracted fields"
        >
          <table className="data-table edit-table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Value</th>
                <th>Confidence</th>
                <th>Page</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((field, idx) => (
                <tr key={idx}>
                  <td>
                    <span className="field-name">{field.field_name}</span>
                  </td>
                  <td>
                    <input
                      type="text"
                      className="field-input"
                      value={String(field.value)}
                      onChange={(e) => handleFieldChange(idx, e.target.value)}
                      aria-label={`Edit ${field.field_name}`}
                    />
                  </td>
                  <td>
                    <span
                      className={`confidence ${
                        field.confidence >= 0.9
                          ? 'high'
                          : field.confidence >= 0.75
                          ? 'medium'
                          : 'low'
                      }`}
                    >
                      {(field.confidence * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td>{field.page_number}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="action-bar">
            <button
              type="submit"
              className="btn btn-primary"
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
        </form>
      )}
    </div>
  );
}

export default EditData;
