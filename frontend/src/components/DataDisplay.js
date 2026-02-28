import React, { useState } from 'react';
import { extractData, exportDocument } from '../services/api';

/**
 * DataDisplay component.
 * Shows extracted fields and tables for the uploaded document.
 * Provides buttons to trigger extraction, edit data, and export.
 *
 * Props:
 *   document    - { documentId, filename }
 *   extraction  - ExtractionResult | null
 *   onExtract(result) - called after successful extraction
 *   onEdit()    - called when user clicks "Edit Data"
 */
function DataDisplay({ document, extraction, onExtract, onEdit }) {
  const [isExtracting, setIsExtracting] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState('pdf');
  const [exportUrl, setExportUrl] = useState('');
  const [error, setError] = useState('');

  const handleExtract = async () => {
    setIsExtracting(true);
    setError('');
    setExportUrl('');
    try {
      const result = await extractData(document.documentId);
      onExtract(result);
    } catch (err) {
      setError(err.message || 'Extraction failed. Please try again.');
    } finally {
      setIsExtracting(false);
    }
  };

  const handleExport = async () => {
    setIsExporting(true);
    setError('');
    try {
      const result = await exportDocument(document.documentId, exportFormat);
      setExportUrl(result.download_url);
    } catch (err) {
      setError(err.message || 'Export failed. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="data-display">
      <div className="document-info">
        <h2>📄 {document.filename}</h2>
        {extraction && (
          <span className="badge badge-success">
            {extraction.total_pages} page{extraction.total_pages !== 1 ? 's' : ''}
            &nbsp;·&nbsp;
            {extraction.fields.length} field{extraction.fields.length !== 1 ? 's' : ''} extracted
          </span>
        )}
      </div>

      {error && <p className="error-message" role="alert">{error}</p>}

      {!extraction && (
        <div className="action-bar">
          <button
            className="btn btn-primary"
            onClick={handleExtract}
            disabled={isExtracting}
            aria-busy={isExtracting}
          >
            {isExtracting ? 'Extracting…' : 'Extract Data'}
          </button>
        </div>
      )}

      {extraction && (
        <>
          {/* Extracted Fields */}
          {extraction.fields.length > 0 && (
            <section className="section">
              <h3>Extracted Fields</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Field</th>
                    <th>Value</th>
                    <th>Confidence</th>
                    <th>Page</th>
                  </tr>
                </thead>
                <tbody>
                  {extraction.fields.map((field, idx) => (
                    <tr key={idx}>
                      <td>{field.field_name}</td>
                      <td>{String(field.value)}</td>
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
            </section>
          )}

          {/* Extracted Tables */}
          {extraction.tables && extraction.tables.length > 0 && (
            <section className="section">
              <h3>Detected Tables ({extraction.tables.length})</h3>
              {extraction.tables.map((table, tIdx) => (
                <div key={tIdx} className="detected-table">
                  <h4>Table {tIdx + 1}</h4>
                  <table className="data-table">
                    <tbody>
                      {table.map((row, rIdx) => (
                        <tr key={rIdx}>
                          {row.map((cell, cIdx) => (
                            <td key={cIdx}>{cell}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </section>
          )}

          {/* Raw Text Preview */}
          {extraction.extracted_text && (
            <section className="section">
              <h3>Raw Text Preview</h3>
              <pre className="text-preview">
                {extraction.extracted_text.slice(0, 1000)}
                {extraction.extracted_text.length > 1000 ? '\n…[truncated]' : ''}
              </pre>
            </section>
          )}

          {/* Action bar */}
          <div className="action-bar">
            <button className="btn btn-secondary" onClick={onEdit}>
              ✏️ Edit Data
            </button>

            <div className="export-group">
              <select
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value)}
                aria-label="Export format"
              >
                <option value="pdf">PDF</option>
                <option value="json">JSON</option>
                <option value="csv">CSV</option>
              </select>
              <button
                className="btn btn-primary"
                onClick={handleExport}
                disabled={isExporting}
                aria-busy={isExporting}
              >
                {isExporting ? 'Exporting…' : '⬇️ Export'}
              </button>
            </div>

            {exportUrl && (
              <a
                href={exportUrl}
                className="download-link"
                target="_blank"
                rel="noreferrer"
              >
                Download {exportFormat.toUpperCase()}
              </a>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default DataDisplay;
