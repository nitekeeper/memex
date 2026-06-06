"""Graph population — deterministic, LLM-free, dependency-light.

GraphRAG's pipeline starts from a graph. The Memex relation graph is empty
by default (the Librarian writes semantic edges only when it finds them, and
on a fresh Brain there are none), so community detection over `relations`
would cluster nothing. This module seeds the graph from the embedding space:
for each document with an embedding, it connects the document to its top-K
most-similar neighbors (cosine >= threshold) with a DISTINCT
`rel_type='similar_to'` edge whose `confidence` is the cosine score.

Design choices:
  - **Distinct rel_type.** `similar_to` edges are kept separate from
    Librarian-authored semantic relations (cites, synthesizes, references,
    …) so a graph rebuild never clobbers or is clobbered by human/LLM
    knowledge. Community detection reads ALL rel_types, but maintenance only
    rewrites `similar_to`.
  - **Deterministic.** No randomness. Ties broken by (cosine desc, index_id
    asc). Same documents+embeddings -> same edges.
  - **Idempotent.** Existing `similar_to` edges for a given source are
    cleared and rewritten on each run, so re-running converges rather than
    accumulating stale edges.
  - **Dependency-light.** Pure stdlib + `embeddings.cosine` (already a manual
    float scan). Full O(n^2) pairwise scan is fine at personal-Brain scale.
  - **Degrades gracefully.** <2 embedded docs -> no-op, no crash.

This is a DERIVED index-maintenance path, not a document-ingest bypass:
document writes still flow through the Librarian (spec §6 / M3). These edges
are rebuildable from `documents` at any time.
"""

from __future__ import annotations

import os

from scripts.db import get_connection, memex_home
from scripts.embeddings import cosine

SIMILAR_REL_TYPE = "similar_to"

_DEFAULT_KNN_K = 5
_DEFAULT_THRESHOLD = 0.5


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
    """Minimum cosine to draw an edge. Env override: MEMEX_GRAPH_SIM_THRESHOLD."""
    raw = os.environ.get("MEMEX_GRAPH_SIM_THRESHOLD")
    if raw is None:
        return _DEFAULT_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_THRESHOLD


def build_graph(k: int | None = None, threshold: float | None = None) -> dict:
    """(Re)build the `similar_to` k-NN graph over embedded documents.

    For every document carrying an embedding, compute cosine against every
    other embedded document, keep the top-`k` with cosine >= `threshold`, and
    write `relations` rows with rel_type='similar_to' and confidence=<cosine>.
    Edges are directed source->neighbor; the detector treats them as
    undirected (it symmetrizes weights).

    Args:
        k: neighbors per node (default env MEMEX_GRAPH_KNN_K or 5).
        threshold: minimum cosine (default env MEMEX_GRAPH_SIM_THRESHOLD or 0.5).

    Returns:
        {"considered": <embedded doc count>,
         "edges_written": <int>,
         "k": <int>, "threshold": <float>}.

    Degrades: <2 embedded docs -> edges_written=0, no crash. Idempotent:
    pre-existing `similar_to` edges are cleared before rewrite.
    """
    if k is None:
        k = _knn_k()
    if threshold is None:
        threshold = _threshold()

    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    try:
        rows = [
            (r["index_id"], r["embedding"])
            for r in conn.execute(
                "SELECT index_id, embedding FROM documents "
                "WHERE embedding IS NOT NULL ORDER BY index_id"
            )
        ]
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
        for src_id, src_blob in rows:
            scored: list[tuple[float, str]] = []
            for dst_id, dst_blob in rows:
                if dst_id == src_id:
                    continue
                try:
                    sim = cosine(src_blob, dst_blob)
                except ValueError:
                    # Dimension mismatch (mixed embedding models) — skip this
                    # pair rather than crashing the whole rebuild.
                    continue
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
