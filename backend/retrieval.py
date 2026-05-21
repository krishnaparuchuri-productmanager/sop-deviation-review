"""
retrieval.py — SOP loader, section-level chunker, and TF-IDF search index.

Responsibilities:
  1. Load all .md files from data/sop/ at import time (or on first call).
  2. Split each SOP by ## section headers — each chunk keeps its header intact.
  3. Attach metadata (sop_id, section_title, section_number, source_file) to every chunk.
  4. Build a TF-IDF index over all chunk texts.
  5. Expose search_sop(query, top_k) returning ranked chunks with metadata.

No external vector database is used — sklearn TfidfVectorizer + cosine similarity only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------------------------------------------------------------------------
# Path resolution — works whether called from project root or backend/
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_BACKEND_DIR = _THIS_FILE.parent          # .../backend/
_PROJECT_ROOT = _BACKEND_DIR.parent       # .../sop-deviation-review/
# Data is bundled inside backend/data/ so it's available in the Docker image.
# Fall back to project-root data/ when running locally without the copy.
_SOP_DIR = (
    _BACKEND_DIR / "data" / "sop"
    if (_BACKEND_DIR / "data" / "sop").exists()
    else _PROJECT_ROOT / "data" / "sop"
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class SOPChunk:
    """A single section from a SOP file, with metadata for citation."""
    chunk_id:       str          # e.g. "deviation_control__3"
    sop_id:         str          # filename stem, e.g. "deviation_control"
    source_file:    str          # e.g. "deviation_control.md"
    section_number: str          # e.g. "3" (empty string for the preamble)
    section_title:  str          # full ## header line, e.g. "## 3. Deviation Classification"
    text:           str          # full chunk text including the header line
    word_count:     int = field(init=False)

    def __post_init__(self) -> None:
        self.word_count = len(self.text.split())

    def as_dict(self) -> dict:
        """Return a plain dict for JSON serialisation."""
        return {
            "chunk_id":       self.chunk_id,
            "sop_id":         self.sop_id,
            "source_file":    self.source_file,
            "section_number": self.section_number,
            "section_title":  self.section_title,
            "text":           self.text,
            "word_count":     self.word_count,
        }


@dataclass
class SearchResult:
    """A ranked retrieval result returned by search_sop()."""
    chunk:          SOPChunk
    score:          float        # cosine similarity, 0.0–1.0

    def as_dict(self) -> dict:
        return {**self.chunk.as_dict(), "score": round(float(self.score), 4)}


# ---------------------------------------------------------------------------
# Section splitter
# ---------------------------------------------------------------------------
_SECTION_HEADER_RE = re.compile(r"^(## .+)$", re.MULTILINE)


def _split_by_sections(content: str, sop_id: str, source_file: str) -> List[SOPChunk]:
    """
    Split a markdown SOP document into chunks at every ## header.

    The document preamble (everything before the first ## header) becomes
    chunk index 0 labelled "Preamble". Each subsequent ## section becomes
    its own chunk with the header line retained as the first line of text.

    Args:
        content:     Full markdown file content.
        sop_id:      Filename stem used as the SOP identifier.
        source_file: Filename for citation display.

    Returns:
        List of SOPChunk objects, one per section.
    """
    chunks: List[SOPChunk] = []

    # Find all ## header positions
    header_matches = list(_SECTION_HEADER_RE.finditer(content))

    # --- Preamble (everything before the first ## header) ---
    preamble_end = header_matches[0].start() if header_matches else len(content)
    preamble_text = content[:preamble_end].strip()
    if preamble_text:
        chunks.append(
            SOPChunk(
                chunk_id=f"{sop_id}__0",
                sop_id=sop_id,
                source_file=source_file,
                section_number="",
                section_title="Preamble",
                text=preamble_text,
            )
        )

    # --- One chunk per ## section ---
    for idx, match in enumerate(header_matches):
        header_line = match.group(1).strip()   # e.g. "## 3. Deviation Classification"
        section_start = match.start()
        section_end = (
            header_matches[idx + 1].start()
            if idx + 1 < len(header_matches)
            else len(content)
        )
        chunk_text = content[section_start:section_end].strip()

        # Extract leading section number from "## 3. Title" or "## 3.1 Title"
        num_match = re.match(r"^## (\d+(?:\.\d+)?)", header_line)
        section_number = num_match.group(1) if num_match else str(idx + 1)

        chunks.append(
            SOPChunk(
                chunk_id=f"{sop_id}__{section_number.replace('.', '_')}",
                sop_id=sop_id,
                source_file=source_file,
                section_number=section_number,
                section_title=header_line,
                text=chunk_text,
            )
        )

    return chunks


# ---------------------------------------------------------------------------
# SOP loader
# ---------------------------------------------------------------------------
def load_sops(sop_dir: Path | None = None) -> List[SOPChunk]:
    """
    Load every .md file in sop_dir and return a flat list of SOPChunks.

    Args:
        sop_dir: Override the default data/sop/ directory. Used in tests.

    Returns:
        All chunks from all SOP files, in file-then-section order.

    Raises:
        FileNotFoundError: If sop_dir does not exist or contains no .md files.
    """
    target_dir = sop_dir or _SOP_DIR

    if not target_dir.exists():
        raise FileNotFoundError(f"SOP directory not found: {target_dir}")

    md_files = sorted(target_dir.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No .md files found in {target_dir}")

    all_chunks: List[SOPChunk] = []
    for md_path in md_files:
        sop_id = md_path.stem          # e.g. "deviation_control"
        content = md_path.read_text(encoding="utf-8")
        file_chunks = _split_by_sections(content, sop_id, md_path.name)
        all_chunks.extend(file_chunks)

    return all_chunks


# ---------------------------------------------------------------------------
# TF-IDF index
# ---------------------------------------------------------------------------
class SOPIndex:
    """
    TF-IDF index over all SOP chunks. Built once at startup and reused.

    The vectorizer uses sublinear TF scaling and English stop-word removal
    to improve ranking of pharma domain terms over common function words.
    """

    def __init__(self, chunks: List[SOPChunk]) -> None:
        if not chunks:
            raise ValueError("Cannot build index from an empty chunk list.")

        self.chunks = chunks

        # Build the vectorizer over all chunk texts
        self._vectorizer = TfidfVectorizer(
            sublinear_tf=True,          # log(1+tf) dampens very frequent terms
            min_df=1,                   # include terms that appear in only 1 doc
            ngram_range=(1, 2),         # unigrams + bigrams for pharma phrases
            stop_words="english",
            strip_accents="unicode",
        )
        texts = [chunk.text for chunk in self.chunks]
        self._matrix = self._vectorizer.fit_transform(texts)  # shape: (n_chunks, n_terms)

    def search(self, query: str, top_k: int = 3) -> List[SearchResult]:
        """
        Return the top_k SOP chunks most relevant to query.

        Args:
            query:  Free-text deviation description or keyword query.
            top_k:  Maximum number of results to return. Capped at total chunks.

        Returns:
            List of SearchResult objects, sorted descending by cosine similarity.
            Returns an empty list if the query is blank.
        """
        query = query.strip()
        if not query:
            return []

        k = min(top_k, len(self.chunks))
        query_vec = self._vectorizer.transform([query])                    # (1, n_terms)
        scores = cosine_similarity(query_vec, self._matrix).flatten()     # (n_chunks,)

        # argsort ascending → reverse for descending, take top k
        top_indices = np.argsort(scores)[::-1][:k]

        results = [
            SearchResult(chunk=self.chunks[i], score=scores[i])
            for i in top_indices
            if scores[i] > 0.0   # omit zero-score chunks (no term overlap at all)
        ]
        return results


# ---------------------------------------------------------------------------
# Module-level singleton — built once on first call, reused on subsequent calls
# ---------------------------------------------------------------------------
_index: SOPIndex | None = None


def _get_index(sop_dir: Path | None = None) -> SOPIndex:
    """Return the cached index, building it on first call."""
    global _index
    if _index is None:
        chunks = load_sops(sop_dir)
        _index = SOPIndex(chunks)
    return _index


def reset_index() -> None:
    """Force the index to be rebuilt on next call. Used in tests."""
    global _index
    _index = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def search_sop(
    query: str,
    top_k: int = 3,
    sop_dir: Path | None = None,
) -> List[dict]:
    """
    Search all SOP chunks for content relevant to the given query.

    Args:
        query:   Plain-text deviation description or keywords.
        top_k:   Number of top results to return (default 3).
        sop_dir: Override SOP directory path (used in tests).

    Returns:
        List of dicts, each containing:
            chunk_id, sop_id, source_file, section_number,
            section_title, text, word_count, score (float 0–1).
        Sorted by score descending. Empty list if no relevant chunks found.

    Example:
        >>> results = search_sop("critical deviation classification escalation")
        >>> results[0]["source_file"]
        'deviation_control.md'
    """
    index = _get_index(sop_dir)
    results = index.search(query, top_k=top_k)
    return [r.as_dict() for r in results]


def get_all_chunks(sop_dir: Path | None = None) -> List[dict]:
    """Return all indexed chunks as dicts. Useful for debugging and inspection."""
    index = _get_index(sop_dir)
    return [c.as_dict() for c in index.chunks]
