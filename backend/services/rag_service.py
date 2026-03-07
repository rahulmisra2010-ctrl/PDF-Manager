"""
rag_service.py — RAG (Retrieval-Augmented Generation) extraction service.

Uses LangChain + HuggingFace sentence-transformers for embedding-based field
extraction.  Falls back gracefully to regex-based extraction when ML
dependencies are unavailable.

RAG text files are stored as ``RAG1.txt``, ``RAG2.txt``, … in the configured
``RAG_DIR`` (defaults to ``rag_data/`` relative to the application root).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Address-book field patterns (fallback regex extraction)
# ---------------------------------------------------------------------------

_FIELD_PATTERNS: dict[str, list[str]] = {
    "Name": [
        r"^Name[:\s]+(.+)$",
        r"^Full\s+Name[:\s]+(.+)$",
    ],
    "Street Address": [
        r"^Street\s+Address[:\s]+(.+)$",
        r"^Address[:\s]+(.+)$",
    ],
    "City": [r"^City[:\s]+(.+)$"],
    "State": [r"^State[:\s]+(.+)$"],
    "Zip Code": [r"^Zip\s+Code[:\s]+(.+)$", r"^ZIP[:\s]+(.+)$"],
    "Home Phone": [r"^Home\s+Phone[:\s]+(.+)$"],
    "Cell Phone": [r"^Cell\s+Phone[:\s]+(.+)$", r"^Cell[:\s]+(.+)$"],
    "Work Phone": [r"^Work\s+Phone[:\s]+(.+)$"],
    "Email": [r"^Email[:\s]+(.+)$", r"^E-?mail[:\s]+(.+)$"],
}

# Supported primary fields (in display order)
PRIMARY_FIELDS = [
    "Name",
    "Cell Phone",
    "Email",
    "Street Address",
    "City",
    "State",
    "Zip Code",
    "Work Phone",
    "Home Phone",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _clean_value(v: str) -> str:
    """Strip surrounding whitespace and common placeholder characters."""
    v = v.strip().strip("_").strip()
    return v


# ---------------------------------------------------------------------------
# RAGService
# ---------------------------------------------------------------------------

class RAGService:
    """
    RAG-based field extraction for address-book PDFs.

    Architecture
    ------------
    1. Text is extracted from the PDF (by the caller) and saved to a RAG
       text file (``RAG<n>.txt``).
    2. The text is split into sentence-level chunks and embedded with
       HuggingFace ``sentence-transformers/all-MiniLM-L6-v2``.
    3. For each target field, a query embedding is computed and the most
       similar chunk(s) are retrieved.
    4. A lightweight regex pass extracts the field value from those chunks.
    5. All embeddings + chunk metadata are persisted in a JSON sidecar file
       alongside the RAG text file for reuse.

    Graceful degradation
    --------------------
    When ``sentence-transformers`` / ``langchain`` are unavailable, the
    service falls back to the regex-only path (same confidence heuristic).
    """

    def __init__(self, rag_dir: str | None = None) -> None:
        self.rag_dir = Path(rag_dir or os.environ.get("RAG_DIR", "rag_data"))
        self.rag_dir.mkdir(parents=True, exist_ok=True)
        self._embedder = None  # lazy initialised
        self._embedder_loaded = False

    # ------------------------------------------------------------------
    # Embedder (lazy init with fallback)
    # ------------------------------------------------------------------

    def _get_embedder(self):
        if self._embedder_loaded:
            return self._embedder
        self._embedder_loaded = True
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
            self._embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            logger.info("RAGService: sentence-transformers loaded (all-MiniLM-L6-v2)")
        except Exception as exc:  # pragma: no cover
            logger.warning("RAGService: sentence-transformers unavailable (%s); using regex fallback.", exc)
            self._embedder = None
        return self._embedder

    # ------------------------------------------------------------------
    # RAG text file management
    # ------------------------------------------------------------------

    def _next_rag_filename(self) -> Path:
        """Return the path for the next available ``RAG<n>.txt`` file."""
        n = 1
        while (self.rag_dir / f"RAG{n}.txt").exists():
            n += 1
        return self.rag_dir / f"RAG{n}.txt"

    def save_rag_text(self, document_id: str, text: str) -> Path:
        """
        Save *text* as a RAG text file and return its path.

        A metadata header is prepended so the file is self-describing.
        """
        rag_path = self._next_rag_filename()
        header = (
            f"# RAG document\n"
            f"# document_id: {document_id}\n"
            f"# created_at: {datetime.utcnow().isoformat()}Z\n"
            f"#\n"
        )
        rag_path.write_text(header + text, encoding="utf-8")
        logger.info("RAGService: saved RAG text -> %s", rag_path)
        return rag_path

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 200) -> list[str]:
        """
        Split *text* into small chunks for embedding.

        Lines are primary split boundaries; long lines are further split
        at whitespace boundaries.
        """
        chunks: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            while len(line) > max_chars:
                split_at = line.rfind(" ", 0, max_chars)
                if split_at == -1:
                    split_at = max_chars
                chunks.append(line[:split_at].strip())
                line = line[split_at:].strip()
            if line:
                chunks.append(line)
        return chunks

    # ------------------------------------------------------------------
    # Embeddings (with JSON sidecar cache)
    # ------------------------------------------------------------------

    def _embed_chunks(self, chunks: list[str], cache_path: Path) -> list[dict]:
        """
        Return a list of ``{"text": ..., "embedding": [...]}`` dicts.

        If a JSON cache exists at *cache_path*, it is returned directly;
        otherwise embeddings are computed and saved.
        """
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(cached, list) and len(cached) == len(chunks):
                    return cached
            except Exception:
                pass

        embedder = self._get_embedder()
        if embedder is None:
            # No embedder — return dicts without embeddings
            return [{"text": c, "embedding": None} for c in chunks]

        try:
            vectors = embedder.encode(chunks, convert_to_numpy=True).tolist()
        except Exception as exc:
            logger.warning("RAGService: embedding failed (%s); returning empty vectors.", exc)
            return [{"text": c, "embedding": None} for c in chunks]

        records = [{"text": c, "embedding": v} for c, v in zip(chunks, vectors)]
        try:
            cache_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.warning("RAGService: failed to write embedding cache (%s).", exc)
        return records

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def _retrieve(
        self, query: str, records: list[dict], top_k: int = 3
    ) -> list[str]:
        """Return the top-*k* chunk texts most similar to *query*."""
        embedder = self._get_embedder()
        if embedder is None or not records or records[0]["embedding"] is None:
            # Fallback: keyword-based retrieval
            q_lower = query.lower()
            scored = [
                (sum(w in r["text"].lower() for w in q_lower.split()), r["text"])
                for r in records
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            return [t for _, t in scored[:top_k] if t]

        try:
            q_vec = embedder.encode([query], convert_to_numpy=True)[0].tolist()
        except Exception:
            return [r["text"] for r in records[:top_k]]

        scored = [
            (_cosine_similarity(q_vec, r["embedding"]), r["text"])
            for r in records
            if r.get("embedding")
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:top_k]]

    # ------------------------------------------------------------------
    # Regex extraction pass
    # ------------------------------------------------------------------

    @staticmethod
    def _regex_extract(field_name: str, chunks: list[str]) -> tuple[str, float]:
        """
        Extract a field value from *chunks* using regex patterns.

        Returns ``(value, confidence)`` where confidence is in [0.0, 1.0].
        """
        patterns = _FIELD_PATTERNS.get(field_name, [])
        for chunk in chunks:
            for pat in patterns:
                m = re.search(pat, chunk, re.IGNORECASE | re.MULTILINE)
                if m:
                    val = _clean_value(m.group(1))
                    if val:
                        return val, 0.85
        return "", 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_fields(self, document_id: str, text: str) -> list[dict[str, Any]]:
        """
        Extract address-book fields from *text* using RAG.

        Returns a list of dicts with keys:
        ``field_name``, ``field_value``, ``confidence``, ``rag_retrieved``.
        """
        # 1. Save RAG text file
        rag_path = self.save_rag_text(document_id, text)
        cache_path = rag_path.with_suffix(".embeddings.json")

        # 2. Chunk the text
        chunks = self._chunk_text(text)
        if not chunks:
            return self._empty_fields()

        # 3. Embed chunks (or load from cache)
        records = self._embed_chunks(chunks, cache_path)

        # 4. For each field, retrieve relevant chunks and extract value
        results: list[dict[str, Any]] = []
        for field_name in PRIMARY_FIELDS:
            query = f"{field_name}: "
            top_chunks = self._retrieve(query, records, top_k=5)
            value, confidence = self._regex_extract(field_name, top_chunks)

            # If retrieval didn't help, try full-text scan as fallback
            if not value:
                value, confidence = self._regex_extract(field_name, chunks)

            results.append(
                {
                    "field_name": field_name,
                    "field_value": value,
                    "confidence": round(confidence, 4),
                    "rag_retrieved": top_chunks[:2],  # for debugging
                }
            )

        return results

    @staticmethod
    def _empty_fields() -> list[dict[str, Any]]:
        return [
            {
                "field_name": f,
                "field_value": "",
                "confidence": 0.0,
                "rag_retrieved": [],
            }
            for f in PRIMARY_FIELDS
        ]

    def list_rag_files(self) -> list[dict[str, Any]]:
        """Return metadata for all RAG text files in *rag_dir*."""
        files = []
        for p in sorted(self.rag_dir.glob("RAG*.txt")):
            stat = p.stat()
            doc_id: str | None = None
            try:
                first_lines = p.read_text(encoding="utf-8", errors="ignore")[:200]
                m = re.search(r"# document_id:\s*(.+)", first_lines)
                if m:
                    doc_id = m.group(1).strip()
            except Exception:
                pass
            files.append(
                {
                    "filename": p.name,
                    "path": str(p),
                    "document_id": doc_id,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.utcfromtimestamp(stat.st_ctime).isoformat(),
                }
            )
        return files
