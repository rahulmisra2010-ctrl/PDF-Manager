import React, { useState, useRef } from 'react';
import { uploadPDF } from '../services/api';

/**
 * UploadPDF component.
 * Allows the user to select and upload a PDF file, then triggers extraction.
 *
 * Props:
 *   onUploadComplete(doc) - called with { documentId, filename } after upload
 */
function UploadPDF({ onUploadComplete }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  const handleFileChange = (file) => {
    setError('');
    if (!file) return;
    if (file.type !== 'application/pdf') {
      setError('Please select a valid PDF file.');
      return;
    }
    setSelectedFile(file);
  };

  const handleInputChange = (e) => {
    handleFileChange(e.target.files[0]);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    handleFileChange(e.dataTransfer.files[0]);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setError('Please select a file first.');
      return;
    }
    setIsUploading(true);
    setError('');
    try {
      const response = await uploadPDF(selectedFile);
      onUploadComplete({
        documentId: response.document_id,
        filename: response.filename,
      });
    } catch (err) {
      setError(err.message || 'Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="upload-container">
      <div
        className={`drop-zone ${isDragging ? 'drag-over' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current && fileInputRef.current.click()}
        role="button"
        aria-label="Drop zone for PDF upload"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current && fileInputRef.current.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          onChange={handleInputChange}
          style={{ display: 'none' }}
          aria-label="PDF file input"
        />
        <div className="drop-zone-content">
          <span className="drop-icon">📂</span>
          {selectedFile ? (
            <p className="selected-file">{selectedFile.name}</p>
          ) : (
            <>
              <p>Drag &amp; drop a PDF here</p>
              <p className="or-text">or click to browse</p>
            </>
          )}
        </div>
      </div>

      {error && <p className="error-message" role="alert">{error}</p>}

      <button
        className="btn btn-primary"
        onClick={handleUpload}
        disabled={!selectedFile || isUploading}
        aria-busy={isUploading}
      >
        {isUploading ? 'Uploading…' : 'Upload PDF'}
      </button>
    </div>
  );
}

export default UploadPDF;
