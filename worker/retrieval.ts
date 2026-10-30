/**
 * retrieval.ts — TF-IDF SOP search (port of backend/retrieval.py).
 *
 * The index itself (vocabulary, idf, L2-normalised chunk vectors) is fitted by
 * scikit-learn in scripts/build_worker_data.py and shipped as data/sop_index.json.
 * This module only vectorises the query the way TfidfVectorizer.transform does
 * (lowercase, strip_accents="unicode", token_pattern \b\w\w+\b, English stop
 * words, 1–2 grams, sublinear tf, L2 norm) and ranks chunks by cosine similarity,
 * so results match the Python backend exactly.
 */

import index from "./data/sop_index.json";
import { pyRound } from "./util";

export interface SopChunk {
  chunk_id: string;
  sop_id: string;
  source_file: string;
  section_number: string;
  section_title: string;
  text: string;
  word_count: number;
  score: number;
}

interface SopIndex {
  stop_words: string[];
  vocabulary: Record<string, number>;
  idf: number[];
  chunks: Omit<SopChunk, "score">[];
  vectors: [number, number][][];
}

const IDX = index as unknown as SopIndex;
const STOP = new Set(IDX.stop_words);
const VOCAB = new Map(Object.entries(IDX.vocabulary));
// Dense chunk vectors keyed by term index, for fast dot products.
const CHUNK_VECTORS = IDX.vectors.map((pairs) => new Map(pairs));

// Python's (?u)\w: letters, digits (any script), connector punctuation, and marks.
const WORD_RUNS = /[\p{L}\p{N}\p{Mn}\p{Mc}\p{Pc}]{2,}/gu;

function analyze(text: string): string[] {
  // strip_accents="unicode": NFKD, then drop combining characters
  const doc = text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
  const tokens = (doc.match(WORD_RUNS) ?? []).filter((t) => !STOP.has(t));
  const grams = [...tokens];
  for (let i = 0; i + 1 < tokens.length; i++) grams.push(`${tokens[i]} ${tokens[i + 1]}`);
  return grams;
}

function vectorize(query: string): Map<number, number> {
  const tf = new Map<number, number>();
  for (const term of analyze(query)) {
    const i = VOCAB.get(term);
    if (i !== undefined) tf.set(i, (tf.get(i) ?? 0) + 1);
  }
  const vec = new Map<number, number>();
  let norm = 0;
  for (const [i, n] of tf) {
    const w = (1 + Math.log(n)) * IDX.idf[i];
    vec.set(i, w);
    norm += w * w;
  }
  norm = Math.sqrt(norm);
  if (norm > 0) for (const [i, w] of vec) vec.set(i, w / norm);
  return vec;
}

/** Return the top_k chunks most relevant to query, best first (search_sop). */
export function searchSop(query: string, topK = 3): SopChunk[] {
  query = query.trim();
  if (!query) return [];
  const q = vectorize(query);
  const scored = CHUNK_VECTORS.map((cv, i) => {
    let s = 0;
    for (const [term, w] of q) s += w * (cv.get(term) ?? 0);
    return { i, s };
  });
  // np.argsort(...)[::-1]: descending score; equal scores come out highest index first.
  scored.sort((a, b) => b.s - a.s || b.i - a.i);
  return scored
    .slice(0, Math.min(topK, scored.length))
    .filter(({ s }) => s > 0)
    .map(({ i, s }) => ({ ...IDX.chunks[i], score: pyRound(s, 4) }));
}
