/**
 * useSpatialContext.js — Hook for fetching spatial context on hover/click.
 *
 * Returns spatial word data and suggestions for a given PDF coordinate.
 */

import { useState, useCallback, useRef } from 'react';

const API_BASE_URL =
  process.env.REACT_APP_API_URL
    ? `${process.env.REACT_APP_API_URL}/api/v1`
    : '/api/v1';

/**
 * @param {string|number} documentId
 * @returns {{ contextData, loading, error, fetchContext, clearContext }}
 */
function useSpatialContext(documentId) {
  const [contextData, setContextData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);

  const fetchContext = useCallback(
    async (x, y, page = 1, radius = 30) => {
      if (!documentId) return;

      // Cancel any in-flight request
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);

      try {
        const resp = await fetch(
          `${API_BASE_URL}/suggestions/spatial/${encodeURIComponent(documentId)}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ x, y, page, radius }),
            signal: controller.signal,
          }
        );
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          throw new Error(body.error || `Request failed: ${resp.status}`);
        }
        const data = await resp.json();
        setContextData(data);
      } catch (err) {
        if (err.name !== 'AbortError') {
          setError(err.message);
        }
      } finally {
        setLoading(false);
      }
    },
    [documentId]
  );

  const clearContext = useCallback(() => {
    setContextData(null);
    setError(null);
  }, []);

  return { contextData, loading, error, fetchContext, clearContext };
}

export default useSpatialContext;
