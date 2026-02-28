import React, { useState } from 'react';
import UploadPDF from './components/UploadPDF';
import DataDisplay from './components/DataDisplay';
import EditData from './components/EditData';
import './App.css';

/**
 * Main application component.
 * Manages the top-level state: uploaded document, extracted data, and edit mode.
 */
function App() {
  const [document, setDocument] = useState(null);   // { documentId, filename }
  const [extraction, setExtraction] = useState(null); // ExtractionResult
  const [isEditing, setIsEditing] = useState(false);

  const handleUploadComplete = (doc) => {
    setDocument(doc);
    setExtraction(null);
    setIsEditing(false);
  };

  const handleExtractionComplete = (result) => {
    setExtraction(result);
    setIsEditing(false);
  };

  const handleEditSave = (updatedExtraction) => {
    setExtraction(updatedExtraction);
    setIsEditing(false);
  };

  const handleReset = () => {
    setDocument(null);
    setExtraction(null);
    setIsEditing(false);
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>📄 PDF Manager</h1>
        <p className="app-subtitle">Upload, Extract, Edit &amp; Export PDF Data</p>
        {document && (
          <button className="btn btn-secondary" onClick={handleReset}>
            Upload New PDF
          </button>
        )}
      </header>

      <main className="app-main">
        {!document && (
          <UploadPDF onUploadComplete={handleUploadComplete} />
        )}

        {document && !isEditing && (
          <DataDisplay
            document={document}
            extraction={extraction}
            onExtract={handleExtractionComplete}
            onEdit={() => setIsEditing(true)}
          />
        )}

        {document && isEditing && extraction && (
          <EditData
            document={document}
            extraction={extraction}
            onSave={handleEditSave}
            onCancel={() => setIsEditing(false)}
          />
        )}
      </main>

      <footer className="app-footer">
        <p>PDF Manager &copy; {new Date().getFullYear()}</p>
      </footer>
    </div>
  );
}

export default App;
