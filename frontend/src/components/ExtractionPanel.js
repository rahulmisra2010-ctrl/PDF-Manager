import React, { useState } from 'react';
import PropTypes from 'prop-types';

const ExtractionPanel = () => {
    const [selectedMethod, setSelectedMethod] = useState('');

    const methods = [
        'Extract Fields',
        'AI Extract',
        'PDF Viewer',
        'Overlay View',
        'Live Editor',
        'RAG Extract',
        'Mark as Training',
        'Auto-Detect',
    ];

    const handleMethodChange = (method) => {
        setSelectedMethod(method);
    };

    return (
        <div className="extraction-panel">
            <h2>Extraction Panel</h2>
            <div className="methods">
                {methods.map(method => (
                    <button key={method} onClick={() => handleMethodChange(method)}>
                        {method}
                    </button>
                ))}
            </div>
            {selectedMethod && <p>Selected Method: {selectedMethod}</p>}
        </div>
    );
};

ExtractionPanel.propTypes = {
    // Add PropTypes if needed for future use
};

export default ExtractionPanel;