/**
 * useLayoutAnalysis.js — Hook for fetching form layout analysis data.
 *
 * Fetches zone, column, row, and label-value pair data for a PDF page.
 */

import { useState, useCallback } from 'react';

const API_BASE_URL =
  process.env.REACT_APP_API_URL
    ? `${process.env.REACT_APP_API_URL}/api/v1`
    : '/api/v1';

/**
 * @param {string|number} documentId
 * @returns {{ layoutData, loading, error, fetchLayout }}
 */
function useLayoutAnalysis(documentId) {
  const [layoutData, setLayoutData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchLayout = useCallback(
    async (page = 1) => {
      if (!documentId) return;
      setLoading(true);
      setError(null);

      try {
        const resp = await fetch(
          `${API_BASE_URL}/analyze/layout/${encodeURIComponent(documentId)}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ page }),
          }
        );
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          throw new Error(body.error || `Request failed: ${resp.status}`);
        }
        const data = await resp.json();
        setLayoutData(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    },
    [documentId]
  );

  return { layoutData, loading, error, fetchLayout };
}

export default useLayoutAnalysis;
