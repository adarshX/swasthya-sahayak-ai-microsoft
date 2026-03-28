"""
Lightweight RAG (Retrieval-Augmented Generation) for health documents.
=====================================================================
Uses TF-IDF + cosine similarity — no FAISS, no embeddings, no external infra.
Loads .md files from backend/health_docs/, chunks them, and retrieves the most
relevant chunks for a given query.

Usage:
    from rag import rag_retrieve
    chunks = rag_retrieve("pneumonia in child with fast breathing", top_k=3)
    # Returns list of (text, source_file, score) tuples
"""

import os
import re
from pathlib import Path
from typing import Optional

# scikit-learn for TF-IDF (lightweight, no GPU needed)
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HEALTH_DOCS_DIR = Path(__file__).parent / "health_docs"
CHUNK_SIZE = 500       # characters per chunk
CHUNK_OVERLAP = 100    # overlap between chunks
DEFAULT_TOP_K = 3

# ---------------------------------------------------------------------------
# Global state (initialized once on first query)
# ---------------------------------------------------------------------------
_chunks: list[dict] = []          # {"text": ..., "source": ...}
_vectorizer: Optional[object] = None
_tfidf_matrix = None
_initialized = False


def _load_and_chunk_docs() -> list[dict]:
    """Load all .md files from health_docs/ and chunk them."""
    chunks = []
    if not HEALTH_DOCS_DIR.exists():
        return chunks

    for md_file in sorted(HEALTH_DOCS_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        source = md_file.stem

        # Split by sections (## headings) first, then chunk within sections
        sections = re.split(r'\n(?=## )', text)
        for section in sections:
            section = section.strip()
            if not section:
                continue

            # If section is small enough, keep as one chunk
            if len(section) <= CHUNK_SIZE:
                chunks.append({"text": section, "source": source})
            else:
                # Sliding window chunking
                words = section.split()
                current_chunk = []
                current_len = 0
                for word in words:
                    current_chunk.append(word)
                    current_len += len(word) + 1
                    if current_len >= CHUNK_SIZE:
                        chunk_text = " ".join(current_chunk)
                        chunks.append({"text": chunk_text, "source": source})
                        # Overlap: keep last N chars worth of words
                        overlap_words = []
                        overlap_len = 0
                        for w in reversed(current_chunk):
                            if overlap_len + len(w) + 1 > CHUNK_OVERLAP:
                                break
                            overlap_words.insert(0, w)
                            overlap_len += len(w) + 1
                        current_chunk = overlap_words
                        current_len = overlap_len

                # Remaining words
                if current_chunk:
                    chunks.append({"text": " ".join(current_chunk), "source": source})

    return chunks


def _initialize():
    """Build TF-IDF index from health docs. Called once on first query."""
    global _chunks, _vectorizer, _tfidf_matrix, _initialized

    if _initialized:
        return

    _chunks = _load_and_chunk_docs()
    if not _chunks or not SKLEARN_AVAILABLE:
        _initialized = True
        return

    texts = [c["text"] for c in _chunks]
    _vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=5000,
        ngram_range=(1, 2),
    )
    _tfidf_matrix = _vectorizer.fit_transform(texts)
    _initialized = True


def rag_retrieve(query: str, top_k: int = DEFAULT_TOP_K) -> list[tuple[str, str, float]]:
    """
    Retrieve the most relevant health document chunks for a query.

    Returns list of (chunk_text, source_filename, similarity_score) tuples,
    sorted by relevance (highest first).
    """
    _initialize()

    if not _chunks or not SKLEARN_AVAILABLE or _vectorizer is None:
        return []

    query_vec = _vectorizer.transform([query])
    similarities = cosine_similarity(query_vec, _tfidf_matrix).flatten()

    # Get top-k indices
    top_indices = similarities.argsort()[-top_k:][::-1]

    results = []
    for idx in top_indices:
        score = float(similarities[idx])
        if score > 0.0:  # Only include if some relevance
            results.append((_chunks[idx]["text"], _chunks[idx]["source"], score))

    return results


def rag_context_string(query: str, top_k: int = DEFAULT_TOP_K) -> str:
    """
    Convenience: returns a formatted string of retrieved chunks ready
    to inject into an LLM prompt.
    """
    results = rag_retrieve(query, top_k)
    if not results:
        return ""

    parts = []
    for text, source, score in results:
        parts.append(f"[Source: {source}]\n{text}")
    return "\n\n---\n\n".join(parts)


def get_doc_stats() -> dict:
    """Return stats about the loaded health document corpus."""
    _initialize()
    return {
        "total_chunks": len(_chunks),
        "total_docs": len(set(c["source"] for c in _chunks)) if _chunks else 0,
        "sklearn_available": SKLEARN_AVAILABLE,
        "docs_dir": str(HEALTH_DOCS_DIR),
        "docs_dir_exists": HEALTH_DOCS_DIR.exists(),
    }
