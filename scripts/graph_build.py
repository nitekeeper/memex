"""Graph population — deterministic, LLM-free, key-free, dependency-light.

GraphRAG's pipeline starts from a graph. The Memex relation graph is empty
by default (the Librarian writes semantic edges only when it finds them, and
on a fresh Brain there are none), so community detection over `relations`
would cluster nothing. This module seeds the graph from the documents'
**text** alone: for each document it connects the document to its top-K
most-similar neighbors by a **lexical** similarity over the `searchable`
field (Jaccard over a normalized token-set), drawing a DISTINCT
`rel_type='similar_to'` edge whose `confidence` is the similarity score.

Why lexical, not embeddings? An embedding-kNN seed requires an embedding
provider (OpenAI/Voyage API key, or a local torch/sentence-transformers
model). On a Brain with no provider every document's `embedding` is NULL, so
the embedding path produced ZERO edges and the whole GraphRAG pipeline shipped
inert. Lexical similarity over the already-stored `searchable` text needs no
provider, no API key, and no extra dependency — it works on a fresh Brain out
of the box. Embeddings remain an OPTIONAL enhancement for the *flat* hybrid
ask; the GraphRAG path no longer requires them.

Design choices:
  - **Distinct rel_type.** `similar_to` edges are kept separate from
    Librarian-authored semantic relations (cites, synthesizes, references,
    …) so a graph rebuild never clobbers or is clobbered by human/LLM
    knowledge. Community detection reads ALL rel_types, but maintenance only
    rewrites `similar_to`.
  - **Deterministic.** No randomness. Ties broken by (similarity desc,
    index_id asc). Same documents+text -> same edges, run after run.
  - **Idempotent.** Existing `similar_to` edges for a given source are
    cleared and rewritten on each run, so re-running converges rather than
    accumulating stale edges.
  - **Key-free + dependency-light.** Pure stdlib (`re` + set ops). Full
    O(n^2) pairwise scan is fine at personal-Brain scale.
  - **Degrades gracefully.** <2 docs with non-empty text -> no-op, no crash.

This is a DERIVED index-maintenance path, not a document-ingest bypass:
document writes still flow through the Librarian (spec §6 / M3). These edges
are rebuildable from `documents` at any time.
"""

from __future__ import annotations

import os
import re

from scripts.db import get_connection, memex_home

SIMILAR_REL_TYPE = "similar_to"

_DEFAULT_KNN_K = 5
# Lexical Jaccard overlap is much sparser than cosine in a unit embedding
# space, so the default threshold is lower than the old cosine 0.5. 0.1 means
# "the two documents share at least ~10% of their combined vocabulary", which
# on the text-rich kaizen run-minutes corpus yields meaningful, non-trivial
# edges without connecting near-unrelated docs.
_DEFAULT_THRESHOLD = 0.1

# Tokens shorter than this are dropped before similarity scoring — single
# letters and most punctuation-fragments carry no topical signal.
_MIN_TOKEN_LEN = 2

# A tiny, deterministic stoplist of ultra-common English function words. Kept
# intentionally small (pure stdlib, no NLTK): just enough to stop every pair of
# documents looking "similar" because they both contain "the"/"and"/"of".
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
    }
)

_TOKEN_RE = re.compile(r"\w+")


def _tokenize(text: str | None) -> frozenset[str]:
    """Normalize `text` to a deterministic set of significant tokens.

    Lowercase, split on `\\w+`, drop very-short tokens and stopwords. Returns a
    set (Jaccard is over distinct vocabulary, so multiplicity is ignored). A
    set keeps the metric stable and the O(n^2) scan cheap.
    """
    if not text:
        return frozenset()
    tokens = (t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= _MIN_TOKEN_LEN)
    return frozenset(t for t in tokens if t not in _STOPWORDS)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity: intersection size / union size, in [0.0, 1.0].

    Empty sets -> 0.0.
    """
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    union = len(a) + len(b) - inter
    return inter / union


def _knn_k() -> int:
    """Top-K neighbors per node. Env override: MEMEX_GRAPH_KNN_K."""
    raw = os.environ.get("MEMEX_GRAPH_KNN_K")
    if raw is None:
        return _DEFAULT_KNN_K
    try:
        k = int(raw)
    except ValueError:
        return _DEFAULT_KNN_K
    return max(1, k)


def _threshold() -> float:
    """Minimum lexical similarity to draw an edge.

    Env override: MEMEX_GRAPH_SIM_THRESHOLD (default 0.1). Tuned for Jaccard
    lexical overlap, which is sparser than embedding cosine — lower this to
    draw more (noisier) edges, raise it for a tighter graph.
    """
    raw = os.environ.get("MEMEX_GRAPH_SIM_THRESHOLD")
    if raw is None:
        return _DEFAULT_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_THRESHOLD


def build_graph(k: int | None = None, threshold: float | None = None) -> dict:
    """(Re)build the `similar_to` k-NN graph from document TEXT (no embeddings).

    For every document with non-empty `searchable` text, compute a lexical
    Jaccard similarity against every other such document, keep the top-`k`
    with similarity >= `threshold`, and write `relations` rows with
    rel_type='similar_to' and confidence=<similarity>. Edges are directed
    source->neighbor; the detector treats them as undirected (it symmetrizes
    weights).

    No embedding provider, API key, or extra dependency is required — the graph
    is built from the `searchable` text already stored on each document, so it
    works on a Brain with NULL embeddings.

    Args:
        k: neighbors per node (default env MEMEX_GRAPH_KNN_K or 5).
        threshold: minimum lexical similarity (default env
            MEMEX_GRAPH_SIM_THRESHOLD or 0.1).

    Returns:
        {"considered": <doc-with-text count>,
         "edges_written": <int>,
         "k": <int>, "threshold": <float>}.

    Degrades: <2 docs with usable text -> edges_written=0, no crash. Idempotent:
    pre-existing `similar_to` edges are cleared before rewrite.
    """
    if k is None:
        k = _knn_k()
    if threshold is None:
        threshold = _threshold()

    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    try:
        # Tokenize every document's text. Documents whose searchable text
        # yields no significant tokens are excluded (they cannot be similar to
        # anything) — this is the lexical analogue of the old "embedding IS NOT
        # NULL" filter.
        rows: list[tuple[str, frozenset[str]]] = []
        for r in conn.execute("SELECT index_id, searchable FROM documents ORDER BY index_id"):
            tokens = _tokenize(r["searchable"])
            if tokens:
                rows.append((r["index_id"], tokens))

        summary = {
            "considered": len(rows),
            "edges_written": 0,
            "k": k,
            "threshold": threshold,
        }
        if len(rows) < 2:
            # Nothing to connect. Still clear any stale similar_to edges so a
            # shrunk corpus doesn't leave dangling derived edges.
            conn.execute("DELETE FROM relations WHERE rel_type = ?", (SIMILAR_REL_TYPE,))
            conn.commit()
            return summary

        # Wipe prior derived edges; rebuild from scratch (idempotent).
        conn.execute("DELETE FROM relations WHERE rel_type = ?", (SIMILAR_REL_TYPE,))

        edges_written = 0
        for src_id, src_tokens in rows:
            scored: list[tuple[float, str]] = []
            for dst_id, dst_tokens in rows:
                if dst_id == src_id:
                    continue
                sim = _jaccard(src_tokens, dst_tokens)
                if sim >= threshold:
                    scored.append((sim, dst_id))
            # Deterministic ordering: highest similarity first, then index_id
            # ascending to break ties stably.
            scored.sort(key=lambda t: (-t[0], t[1]))
            for sim, dst_id in scored[:k]:
                conn.execute(
                    "INSERT OR REPLACE INTO relations "
                    "(from_index_id, to_index_id, rel_type, confidence) VALUES (?, ?, ?, ?)",
                    (src_id, dst_id, SIMILAR_REL_TYPE, float(sim)),
                )
                edges_written += 1
        conn.commit()
        summary["edges_written"] = edges_written
        return summary
    finally:
        conn.close()
