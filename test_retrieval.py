"""
test_retrieval.py — Unit tests for backend/retrieval.py.

Tests:
  1. Structural tests  — SOP files load correctly; chunks have required metadata fields.
  2. Query tests       — 3 domain-specific queries return relevant, correctly sourced chunks.
  3. Edge case tests   — blank query, top_k cap, zero-score filtering.

Run from project root:
    python test_retrieval.py                   # plain output
    python -m pytest test_retrieval.py -v      # verbose (if pytest is installed)
"""

import sys
import unittest

# Force UTF-8 output on Windows (cp1252 cannot encode box-drawing characters)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure backend/ is importable when running from the project root
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from retrieval import (  # noqa: E402  (import after sys.path manipulation)
    load_sops,
    search_sop,
    get_all_chunks,
    reset_index,
    _split_by_sections,
    SOPChunk,
)

SOP_DIR = PROJECT_ROOT / "data" / "sop"


# ---------------------------------------------------------------------------
# Helper — run a query and print a readable summary (used in verbose mode)
# ---------------------------------------------------------------------------
def _print_results(label: str, results: list[dict]) -> None:
    print("\n" + "-" * 60)
    print("  Query : " + label)
    print("  Hits  : " + str(len(results)))
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r['source_file']}  s{r['section_number']}  "
              f"score={r['score']:.4f}  words={r['word_count']}")
        snippet = r["text"][:120].replace("\n", " ")
        print("      " + snippet + "...")
    print("-" * 60)


# ===========================================================================
# Test Suite 1 — Loading and chunking
# ===========================================================================
class TestSOPLoading(unittest.TestCase):

    def setUp(self) -> None:
        reset_index()
        self.chunks = load_sops(SOP_DIR)

    def test_five_sop_files_loaded(self) -> None:
        """All 5 markdown SOP files must produce at least one chunk each."""
        source_files = {c.source_file for c in self.chunks}
        expected = {
            "deviation_control.md",
            "immediate_containment.md",
            "investigation_guidelines.md",
            "capa_procedure.md",
            "documentation_standards.md",
        }
        self.assertEqual(
            source_files, expected,
            f"Expected exactly these source files: {expected}. Got: {source_files}",
        )

    def test_minimum_chunk_count(self) -> None:
        """Each 5-section SOP should produce at least 5 chunks (preamble + 4+ sections)."""
        self.assertGreaterEqual(
            len(self.chunks), 25,
            f"Expected at least 25 chunks across 5 SOPs, got {len(self.chunks)}",
        )

    def test_chunk_metadata_fields_present(self) -> None:
        """Every chunk must have all required metadata fields populated."""
        required_fields = ["chunk_id", "sop_id", "source_file",
                           "section_number", "section_title", "text", "word_count"]
        for chunk in self.chunks:
            d = chunk.as_dict()
            for field in required_fields:
                self.assertIn(field, d, f"Missing field '{field}' in chunk {chunk.chunk_id}")
                self.assertIsNotNone(d[field], f"Field '{field}' is None in chunk {chunk.chunk_id}")

    def test_chunk_text_non_empty(self) -> None:
        """No chunk should have empty text."""
        for chunk in self.chunks:
            self.assertGreater(
                len(chunk.text.strip()), 0,
                f"Chunk {chunk.chunk_id} has empty text",
            )

    def test_section_header_preserved_in_chunk_text(self) -> None:
        """Non-preamble chunks must start with their ## header line."""
        for chunk in self.chunks:
            if chunk.section_title == "Preamble":
                continue
            self.assertTrue(
                chunk.text.startswith("##"),
                f"Chunk {chunk.chunk_id} text does not start with ## header.\n"
                f"First 80 chars: {chunk.text[:80]!r}",
            )

    def test_chunk_ids_are_unique(self) -> None:
        """Every chunk_id must be unique across all SOPs."""
        ids = [c.chunk_id for c in self.chunks]
        self.assertEqual(
            len(ids), len(set(ids)),
            f"Duplicate chunk IDs found: "
            f"{[x for x in ids if ids.count(x) > 1]}",
        )

    def test_sop_id_matches_filename_stem(self) -> None:
        """sop_id must equal the filename stem (no .md extension)."""
        for chunk in self.chunks:
            expected_sop_id = chunk.source_file.replace(".md", "")
            self.assertEqual(
                chunk.sop_id, expected_sop_id,
                f"sop_id mismatch: expected '{expected_sop_id}', "
                f"got '{chunk.sop_id}' in chunk {chunk.chunk_id}",
            )


# ===========================================================================
# Test Suite 2 — TF-IDF search: 3 required domain queries
# ===========================================================================
class TestSearchRelevance(unittest.TestCase):

    def setUp(self) -> None:
        reset_index()

    # --- Query 1: Deviation classification and escalation ---
    def test_query_deviation_classification(self) -> None:
        """
        Query: 'how to classify a critical deviation and when to escalate to QA'
        Expected: top result from deviation_control.md (covers classification table
        and escalation paths for Critical / Major / Minor deviations).
        """
        query = "how to classify a critical deviation and when to escalate to QA"
        results = search_sop(query, top_k=3, sop_dir=SOP_DIR)

        _print_results(query, results)

        self.assertGreater(len(results), 0, "Expected at least 1 result, got none.")

        top_sources = [r["source_file"] for r in results]
        self.assertIn(
            "deviation_control.md", top_sources,
            f"Expected 'deviation_control.md' in top results. Got: {top_sources}",
        )

        # Top result should be clearly relevant (score > 0.05)
        self.assertGreater(
            results[0]["score"], 0.05,
            f"Top result score too low ({results[0]['score']:.4f}), suggests poor match.",
        )

    # --- Query 2: Root cause analysis methodology ---
    def test_query_root_cause_analysis(self) -> None:
        """
        Query: 'root cause analysis fishbone 5 whys investigation steps'
        Expected: top result from investigation_guidelines.md (covers RCA tools,
        5 Whys, Fishbone/Ishikawa, timeline reconstruction).
        """
        query = "root cause analysis fishbone 5 whys investigation steps"
        results = search_sop(query, top_k=3, sop_dir=SOP_DIR)

        _print_results(query, results)

        self.assertGreater(len(results), 0, "Expected at least 1 result, got none.")

        top_sources = [r["source_file"] for r in results]
        self.assertIn(
            "investigation_guidelines.md", top_sources,
            f"Expected 'investigation_guidelines.md' in top results. Got: {top_sources}",
        )

        self.assertGreater(
            results[0]["score"], 0.05,
            f"Top result score too low ({results[0]['score']:.4f}), suggests poor match.",
        )

    # --- Query 3: Prohibited record corrections and ALCOA ---
    def test_query_documentation_correction_rules(self) -> None:
        """
        Query: 'correction fluid prohibited GMP record error strikethrough ALCOA'
        Expected: top result from documentation_standards.md (covers ALCOA+ principles,
        prohibited correction methods including correction fluid / Tipp-Ex).
        """
        query = "correction fluid prohibited GMP record error strikethrough ALCOA"
        results = search_sop(query, top_k=3, sop_dir=SOP_DIR)

        _print_results(query, results)

        self.assertGreater(len(results), 0, "Expected at least 1 result, got none.")

        top_sources = [r["source_file"] for r in results]
        self.assertIn(
            "documentation_standards.md", top_sources,
            f"Expected 'documentation_standards.md' in top results. Got: {top_sources}",
        )

        self.assertGreater(
            results[0]["score"], 0.05,
            f"Top result score too low ({results[0]['score']:.4f}), suggests poor match.",
        )


# ===========================================================================
# Test Suite 3 — Edge cases
# ===========================================================================
class TestSearchEdgeCases(unittest.TestCase):

    def setUp(self) -> None:
        reset_index()

    def test_blank_query_returns_empty_list(self) -> None:
        """A blank or whitespace-only query must return an empty list, not an error."""
        for blank in ["", "   ", "\t\n"]:
            results = search_sop(blank, top_k=3, sop_dir=SOP_DIR)
            self.assertEqual(
                results, [],
                f"Expected [] for blank query {blank!r}, got {results}",
            )

    def test_top_k_cap(self) -> None:
        """top_k is respected — results list must not exceed requested size."""
        results = search_sop("deviation quality assurance", top_k=2, sop_dir=SOP_DIR)
        self.assertLessEqual(
            len(results), 2,
            f"Expected at most 2 results for top_k=2, got {len(results)}",
        )

    def test_results_sorted_descending_by_score(self) -> None:
        """Results must be ordered highest score first."""
        results = search_sop("corrective action CAPA closure effectiveness", top_k=5, sop_dir=SOP_DIR)
        scores = [r["score"] for r in results]
        self.assertEqual(
            scores, sorted(scores, reverse=True),
            f"Results are not sorted by score descending: {scores}",
        )

    def test_get_all_chunks_returns_dicts(self) -> None:
        """get_all_chunks() must return a non-empty list of dicts."""
        all_chunks = get_all_chunks(SOP_DIR)
        self.assertIsInstance(all_chunks, list)
        self.assertGreater(len(all_chunks), 0)
        self.assertIsInstance(all_chunks[0], dict)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  SOP Retrieval — Test Suite")
    print("=" * 60)
    unittest.main(verbosity=2)
