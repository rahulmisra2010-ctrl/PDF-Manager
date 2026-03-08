import React, { useState } from 'react';
import { Toaster } from 'react-hot-toast';
import UploadPDF from './components/UploadPDF';
import ExtractionPage from './components/ExtractionPage';
import './App.css';

/**
 * Main application component.
 * Manages top-level state: uploaded document and the extraction workflow.
 *
 * Flow:
 *   1. User uploads a PDF via UploadPDF
 *   2. ExtractionPage shows the split PDF viewer + fields editor
 */
function App() {
  const [document, setDocument] = useState(null);   // { documentId, filename }

  const handleUploadComplete = (doc) => {
    setDocument(doc);
  };

  const handleReset = () => {
    setDocument(null);
  };

  return (
    <div className="app">
      {/* Global toast notifications */}
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: { fontSize: '0.9rem' },
          success: { iconTheme: { primary: '#10b981', secondary: '#fff' } },
          error: { iconTheme: { primary: '#ef4444', secondary: '#fff' } },
        }}
      />

      <header className="app-header">
        <h1>📄 PDF Manager</h1>
        <p className="app-subtitle">
          Advanced OCR · AI Extraction · RAG · Interactive Viewer
        </p>
      </header>

      <main className="app-main">
        {!document ? (
          <UploadPDF onUploadComplete={handleUploadComplete} />
        ) : (
          <ExtractionPage document={document} onReset={handleReset} />
        )}
      </main>

      <footer className="app-footer">
        <p>PDF Manager &copy; {new Date().getFullYear()}</p>
      </footer>
    </div>
  );
}

export default App;


