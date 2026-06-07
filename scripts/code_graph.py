"""Code-navigation graph store + bounded query layer — deterministic, LLM-free.

memex is the STORE + QUERY layer for a code-navigation graph. The EXTRACTOR is
EXTERNAL: graphify (tree-sitter + networkx, code-only) is run by the CONSUMER
with `graphify update <path> --no-cluster` (AST-only, no API key). memex never
imports tree-sitter / networkx / graspologic — it ingests graphify's
`graph.json` with stdlib `json` into a SEPARATE SQLite DB
(`~/.memex/code_graph.db`) and serves bounded queries. Consumers: kaizen
(pre-cycle recon) and atelier subagents.

Design / why this module exists
-------------------------------
- **Separate DB, keyed by repo identity.** The graph lives in `code_graph.db`,
  never in `index.db`, and rows are keyed by the repo IDENTITY string
  (``owner/repo``) rather than a clone path. That makes the store survive
  ephemeral clones and repo moves across machines (WSL ↔ macOS).
- **Pure deterministic store.** No LLM anywhere. graphify's content-derived
  node ids are stored VERBATIM, so re-ingesting the same code converges instead
  of duplicating.
- **Bounded queries, locations not bodies.** Every query returns rows /
  source-locations only — never file bodies — and BFS expansion is capped
  (`max_nodes`) as a token-budget analog. All ORDER BYs are deterministic so
  tests are stable.

Idempotency / the anti-graphify-merge guard
-------------------------------------------
graphify's own ``update --no-cluster`` is NON-idempotent: re-running it merges
duplicate edges (observed 1459 → 2765 → 4071 → 5377 across four runs). memex
fixes this at ingest: each per-file fragment is upserted under a
DELETE-then-INSERT-with-ON-CONFLICT discipline, so the node/edge row counts stay
CONSTANT across repeated ingests of the same graph.

Invalidation
------------
- ``ingest_fragment`` DELETEs a file's nodes first (cascade removes that file's
  OWNED edges via the (repo, source) FK), then re-inserts nodes + edges. This
  makes a re-ingest of one changed file correct in place.
- ``invalidate_file`` additionally deletes INBOUND edges that pointed at the
  symbols the file used to own — closing the gap graphify leaves when a symbol
  is renamed/deleted in a file while an *unchanged* neighbor still references
  the old id.
- ``prune_dangling_edges`` is the integrity sweep: it removes any edge whose
  source OR target node is absent.

Edge → node FK tradeoff (chosen design)
---------------------------------------
The edges table carries a composite FK on ``(repo, source) → nodes(repo, id)``
ONLY. The ``(repo, target)`` endpoint is deliberately NOT a FK. graphify is
ingested file-by-file, and a cross-file edge's target may live in a file not yet
ingested in the same full-graph pass — a target FK would make fragment ordering
brittle and break ingest robustness. We keep the source FK (so cascade-on-node-
delete correctly removes a file's owned edges — the priority), and enforce
target integrity via the dangling-edge sweep + ``invalidate_file``'s explicit
inbound-edge deletion. Correctness of invalidation AND robust ingest are both
satisfied; the only cost is that a momentarily-dangling target edge can exist
between fragment inserts within a single transaction, which the sweep cleans.

OPTIONAL convenience
--------------------
``extract_and_ingest`` shells out to ``graphify`` via subprocess for callers who
want a one-step path. It degrades gracefully (clear error, no crash) if graphify
is not on PATH and is NOT exercised by any test.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 — only used by the optional extract_and_ingest convenience
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.db import get_connection, memex_home

# Outbound relations that constitute a "dependency" of a node.
_DEPENDENCY_RELATIONS = ("imports", "imports_from", "uses", "calls")
_CALLS_RELATION = "calls"

# Default BFS output cap — a token-budget analog so a hub node cannot return an
# unbounded neighborhood to the consumer's context.
_DEFAULT_MAX_NODES = 200


def code_graph_db_path() -> str:
    """Absolute path to the code-navigation graph store (separate from index.db)."""
    return str(memex_home() / "code_graph.db")


def _connect():
    """Open the code_graph store with Memex pragmas (FK enforcement ON)."""
    return get_connection(code_graph_db_path())


def _ensure_schema(conn) -> None:
    """Apply db/code_graph.sql to `conn` (re-entrant; safe to call repeatedly).

    Lets ingest work against a bare DB without requiring a prior install run —
    useful for tests and for first-touch ingest. The install path also provisions
    + registers the store; this is the in-process safety net.
    """
    from scripts.paths import DB_DIR

    conn.executescript((DB_DIR / "code_graph.sql").read_text(encoding="utf-8"))
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_graph(graph: dict | str | Path) -> dict:
    """Coerce a graph argument into a dict.

    Accepts an already-parsed dict, a path (str/Path) to a graph.json file, or a
    raw JSON string. graphify emits ``{"nodes": [...], "links": [...]}``; the
    edge array key is ``links`` in current graphify, ``edges`` in older output —
    both are accepted by the readers below, so no normalization is needed here.
    """
    if isinstance(graph, dict):
        return graph
    if isinstance(graph, Path):
        return json.loads(graph.read_text(encoding="utf-8"))
    if isinstance(graph, str):
        # A filesystem path or a raw JSON blob. A raw JSON blob starts with '{'
        # (or whitespace then '{') and can be longer than the OS path limit, so
        # only probe the filesystem when the string plausibly looks like a path.
        stripped = graph.lstrip()
        if not stripped.startswith(("{", "[")):
            try:
                candidate = Path(graph)
                if candidate.is_file():
                    return json.loads(candidate.read_text(encoding="utf-8"))
            except OSError:
                pass
        return json.loads(graph)
    raise TypeError(f"graph must be dict, str, or Path; got {type(graph).__name__}")


def _edges_of(graph: dict) -> list[dict]:
    """Return the edge list, accepting both the new `links` and legacy `edges` keys."""
    if "links" in graph and graph["links"] is not None:
        return list(graph["links"])
    if "edges" in graph and graph["edges"] is not None:
        return list(graph["edges"])
    return []


def _nodes_of(graph: dict) -> list[dict]:
    return list(graph.get("nodes") or [])


def _node_source_file(node: dict) -> str | None:
    return node.get("source_file")


def _edge_source_file(edge: dict) -> str | None:
    return edge.get("source_file")


def _upsert_node(conn, repo: str, node: dict) -> None:
    conn.execute(
        "INSERT INTO nodes (repo, id, label, file_type, source_file, source_location) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(repo, id) DO UPDATE SET "
        "label=excluded.label, file_type=excluded.file_type, "
        "source_file=excluded.source_file, source_location=excluded.source_location",
        (
            repo,
            node["id"],
            node.get("label"),
            node.get("file_type"),
            node.get("source_file"),
            node.get("source_location"),
        ),
    )


def _upsert_edge(conn, repo: str, edge: dict) -> None:
    conn.execute(
        "INSERT INTO edges (repo, source, target, relation, confidence, "
        "confidence_score, weight, source_file, source_location, context) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(repo, source, target, relation) DO UPDATE SET "
        "confidence=excluded.confidence, confidence_score=excluded.confidence_score, "
        "weight=excluded.weight, source_file=excluded.source_file, "
        "source_location=excluded.source_location, context=excluded.context",
        (
            repo,
            edge["source"],
            edge["target"],
            edge["relation"],
            edge.get("confidence"),
            edge.get("confidence_score"),
            edge.get("weight"),
            edge.get("source_file"),
            edge.get("source_location"),
            edge.get("context"),
        ),
    )


def _upsert_repo_row(conn, repo: str, *, built_at_commit: str | None, needs_update: int) -> None:
    conn.execute(
        "INSERT INTO repos (repo, built_at_commit, needs_update, updated_at, schema_version) "
        "VALUES (?, ?, ?, ?, 1) "
        "ON CONFLICT(repo) DO UPDATE SET "
        "built_at_commit=excluded.built_at_commit, needs_update=excluded.needs_update, "
        "updated_at=excluded.updated_at",
        (repo, built_at_commit, needs_update, _now()),
    )


def _ensure_repo_row(conn, repo: str) -> None:
    """Ensure a parent repos row exists so node FK(repo) is satisfiable."""
    row = conn.execute("SELECT 1 FROM repos WHERE repo = ?", (repo,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO repos (repo, built_at_commit, needs_update, updated_at, schema_version) "
            "VALUES (?, NULL, 0, ?, 1)",
            (repo, _now()),
        )


def ingest_fragment(conn, repo: str, source_file: str | None, nodes: list, edges: list) -> dict:
    """Idempotently (re)ingest the nodes + edges OWNED by one ``source_file``.

    Strategy: DELETE the file's existing nodes first — the (repo, source) FK
    cascade removes the edges that file owns — then upsert the fresh nodes and
    edges. This makes a re-ingest of one changed file land in place (no
    duplication) and fixes graphify's non-idempotent merge. The caller owns the
    transaction boundary; this function does not commit.

    Returns ``{"source_file", "nodes", "edges"}`` counts for this fragment.
    """
    _ensure_repo_row(conn, repo)
    # Clear this file's prior nodes; cascade clears its owned (source-side) edges.
    conn.execute("DELETE FROM nodes WHERE repo = ? AND source_file IS ?", (repo, source_file))
    # Defensive: also clear any lingering edges whose owning file is this one but
    # whose source node was (incorrectly) owned by another file. Keeps re-ingest
    # of a fragment byte-clean.
    conn.execute("DELETE FROM edges WHERE repo = ? AND source_file IS ?", (repo, source_file))
    for node in nodes:
        _upsert_node(conn, repo, node)
    for edge in edges:
        _upsert_edge(conn, repo, edge)
    return {"source_file": source_file, "nodes": len(nodes), "edges": len(edges)}


def _group_by_source_file(items: list, source_file_fn) -> dict:
    """Group items by their source_file (preserving a deterministic key order)."""
    grouped: dict = {}
    for item in items:
        key = source_file_fn(item)
        grouped.setdefault(key, []).append(item)
    return grouped


def ingest_graph(
    repo: str, graph: dict | str | Path, *, built_at_commit: str | None = None
) -> dict:
    """Full-graph ingest of a graphify ``graph.json`` for ``repo`` (idempotent).

    Nodes and edges are grouped by ``source_file`` and each file is upserted via
    :func:`ingest_fragment` inside a SINGLE transaction. Because cross-file edges
    may reference a target node owned by another file, ALL nodes are inserted
    before ANY edges (per the edge→node FK tradeoff documented in the module
    docstring: target endpoints are not FK-constrained, so cross-fragment target
    references are tolerated and integrity is enforced by the dangling sweep).

    Re-ingesting the SAME graph yields IDENTICAL row counts (the anti-graphify-
    non-idempotent-merge guarantee).

    Returns a summary dict ``{"repo", "nodes", "edges", "files"}``.
    """
    data = _load_graph(graph)
    nodes = _nodes_of(data)
    edges = _edges_of(data)

    conn = _connect()
    try:
        _ensure_schema(conn)
        _upsert_repo_row(conn, repo, built_at_commit=built_at_commit, needs_update=0)

        nodes_by_file = _group_by_source_file(nodes, _node_source_file)
        edges_by_file = _group_by_source_file(edges, _edge_source_file)

        # Clear every touched file's prior rows, then insert ALL nodes first
        # (across files), then ALL edges — so cross-file target references resolve.
        touched_files = set(nodes_by_file) | set(edges_by_file)
        for sf in touched_files:
            conn.execute("DELETE FROM nodes WHERE repo = ? AND source_file IS ?", (repo, sf))
            conn.execute("DELETE FROM edges WHERE repo = ? AND source_file IS ?", (repo, sf))
        for node in nodes:
            _upsert_node(conn, repo, node)
        for edge in edges:
            _upsert_edge(conn, repo, edge)
        # Integrity sweep: drop any edge whose endpoint did not materialize.
        _prune_dangling_edges(conn, repo)
        conn.commit()

        n_nodes = conn.execute(
            "SELECT COUNT(*) AS n FROM nodes WHERE repo = ?", (repo,)
        ).fetchone()["n"]
        n_edges = conn.execute(
            "SELECT COUNT(*) AS n FROM edges WHERE repo = ?", (repo,)
        ).fetchone()["n"]
        return {
            "repo": repo,
            "nodes": n_nodes,
            "edges": n_edges,
            "files": len(touched_files),
        }
    finally:
        conn.close()


def invalidate_file(repo: str, source_file: str | None) -> dict:
    """Invalidate one file: drop its nodes (cascade its owned edges) AND drop
    INBOUND edges pointing at the symbols that file used to own.

    The inbound-edge deletion is the part graphify cannot do for you: when a
    symbol is renamed or deleted, an unchanged neighbor file may still carry an
    edge into the now-gone id. We collect the file's node ids first, delete the
    nodes (cascading the file's source-side edges), then delete any edge whose
    target is one of those collected ids. Finally a dangling sweep cleans up.

    Returns ``{"repo", "source_file", "nodes_deleted", "inbound_edges_deleted"}``.
    """
    conn = _connect()
    try:
        _ensure_schema(conn)
        owned_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM nodes WHERE repo = ? AND source_file IS ?", (repo, source_file)
            )
        ]
        cur = conn.execute(
            "DELETE FROM nodes WHERE repo = ? AND source_file IS ?", (repo, source_file)
        )
        nodes_deleted = cur.rowcount
        inbound_deleted = 0
        for node_id in owned_ids:
            c = conn.execute("DELETE FROM edges WHERE repo = ? AND target = ?", (repo, node_id))
            inbound_deleted += c.rowcount
        _prune_dangling_edges(conn, repo)
        conn.commit()
        return {
            "repo": repo,
            "source_file": source_file,
            "nodes_deleted": nodes_deleted,
            "inbound_edges_deleted": inbound_deleted,
        }
    finally:
        conn.close()


def _prune_dangling_edges(conn, repo: str) -> int:
    """Delete edges whose source OR target node is absent. Returns count deleted.

    Does not commit (caller owns the transaction).
    """
    cur = conn.execute(
        "DELETE FROM edges WHERE repo = ? AND ("
        "source NOT IN (SELECT id FROM nodes WHERE repo = ?) OR "
        "target NOT IN (SELECT id FROM nodes WHERE repo = ?))",
        (repo, repo, repo),
    )
    return cur.rowcount


def prune_dangling_edges(repo: str) -> dict:
    """Integrity sweep: remove edges with a missing endpoint node for ``repo``."""
    conn = _connect()
    try:
        _ensure_schema(conn)
        deleted = _prune_dangling_edges(conn, repo)
        conn.commit()
        return {"repo": repo, "edges_deleted": deleted}
    finally:
        conn.close()


def set_needs_update(repo: str, flag: bool) -> dict:
    """Mark a repo's graph as stale (or fresh). Freshness is also tracked via the
    ``built_at_commit`` column — a consumer compares it to HEAD to decide whether
    to re-extract."""
    conn = _connect()
    try:
        _ensure_schema(conn)
        _ensure_repo_row(conn, repo)
        conn.execute(
            "UPDATE repos SET needs_update = ?, updated_at = ? WHERE repo = ?",
            (1 if flag else 0, _now(), repo),
        )
        conn.commit()
        row = conn.execute(
            "SELECT repo, built_at_commit, needs_update, updated_at FROM repos WHERE repo = ?",
            (repo,),
        ).fetchone()
        return dict(row) if row else {"repo": repo, "needs_update": 1 if flag else 0}
    finally:
        conn.close()


def repo_status(repo: str) -> dict | None:
    """Return the repos row (freshness metadata) for ``repo``, or None."""
    conn = _connect()
    try:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT repo, built_at_commit, needs_update, updated_at, schema_version "
            "FROM repos WHERE repo = ?",
            (repo,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── Query surface (bounded; returns rows/locations, never file bodies) ───────


def where_is(repo: str, name: str) -> list[dict]:
    """Locate nodes whose label matches ``name`` (exact first, then substring).

    Returns id/label/source_file/source_location dicts. Deterministic order:
    exact-match rank, then label, then id.
    """
    conn = _connect()
    try:
        _ensure_schema(conn)
        like = f"%{name}%"
        rows = conn.execute(
            "SELECT id, label, source_file, source_location, "
            "  CASE WHEN label = ? THEN 0 ELSE 1 END AS rank "
            "FROM nodes WHERE repo = ? AND (label = ? OR label LIKE ?) "
            "ORDER BY rank, label, id",
            (name, repo, name, like),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "label": r["label"],
                "source_file": r["source_file"],
                "source_location": r["source_location"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def callers(repo: str, node_id: str) -> list[dict]:
    """Return the source nodes that CALL ``node_id`` (edges target=node, relation='calls').

    Deterministic order by source id.
    """
    conn = _connect()
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT e.source AS id, n.label AS label, n.source_file AS source_file, "
            "n.source_location AS source_location, e.relation AS relation "
            "FROM edges e LEFT JOIN nodes n ON n.repo = e.repo AND n.id = e.source "
            "WHERE e.repo = ? AND e.target = ? AND e.relation = ? "
            "ORDER BY e.source",
            (repo, node_id, _CALLS_RELATION),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def dependencies(repo: str, node_id: str) -> list[dict]:
    """Return outbound dependencies of ``node_id`` (imports/imports_from/uses/calls).

    Deterministic order by relation, then target id.
    """
    conn = _connect()
    try:
        _ensure_schema(conn)
        placeholders = ", ".join("?" for _ in _DEPENDENCY_RELATIONS)
        # nosec B608 - placeholders are '?' literals; all values parameterized.
        rows = conn.execute(
            "SELECT e.target AS id, n.label AS label, n.source_file AS source_file, "
            "n.source_location AS source_location, e.relation AS relation "
            "FROM edges e LEFT JOIN nodes n ON n.repo = e.repo AND n.id = e.target "
            f"WHERE e.repo = ? AND e.source = ? AND e.relation IN ({placeholders}) "  # nosec B608
            "ORDER BY e.relation, e.target",
            (repo, node_id, *_DEPENDENCY_RELATIONS),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def neighbors(
    repo: str,
    node_id: str,
    *,
    relation: str | None = None,
    depth: int = 1,
    max_nodes: int = _DEFAULT_MAX_NODES,
) -> dict:
    """Bounded, deterministic BFS around ``node_id`` (undirected over edges).

    Expands up to ``depth`` hops, capping the visited-node set at ``max_nodes``
    (a token-budget analog). If ``relation`` is given, only edges of that
    relation are traversed. Returns
    ``{"root", "depth", "truncated", "nodes": [...], "edges": [...]}`` where
    nodes are id/label/source_file/source_location dicts in id order and edges
    are the traversed edge triples.
    """
    conn = _connect()
    try:
        _ensure_schema(conn)
        visited: set[str] = {node_id}
        edge_keys: set[tuple] = set()
        edges_out: list[dict] = []
        frontier = [node_id]
        truncated = False

        for _ in range(max(0, depth)):
            next_frontier: list[str] = []
            # Deterministic frontier expansion: process current frontier in
            # sorted order, and within each node take neighbors in id order.
            for current in sorted(frontier):
                # Two fully-literal queries (no string building around the SQL),
                # selected by whether a relation filter is requested. All values
                # are parameterized.
                if relation is None:
                    rows = conn.execute(
                        "SELECT source, target, relation, confidence, confidence_score, weight "
                        "FROM edges WHERE repo = ? AND (source = ? OR target = ?) "
                        "ORDER BY source, target, relation",
                        (repo, current, current),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT source, target, relation, confidence, confidence_score, weight "
                        "FROM edges WHERE repo = ? AND (source = ? OR target = ?) "
                        "AND relation = ? ORDER BY source, target, relation",
                        (repo, current, current, relation),
                    ).fetchall()
                for r in rows:
                    other = r["target"] if r["source"] == current else r["source"]
                    key = (r["source"], r["target"], r["relation"])
                    if key not in edge_keys:
                        edge_keys.add(key)
                        edges_out.append(
                            {
                                "source": r["source"],
                                "target": r["target"],
                                "relation": r["relation"],
                                "confidence": r["confidence"],
                                "confidence_score": r["confidence_score"],
                                "weight": r["weight"],
                            }
                        )
                    if other not in visited:
                        if len(visited) >= max_nodes:
                            truncated = True
                            continue
                        visited.add(other)
                        next_frontier.append(other)
            frontier = next_frontier
            if not frontier:
                break

        node_rows = []
        for nid in sorted(visited):
            r = conn.execute(
                "SELECT id, label, source_file, source_location FROM nodes "
                "WHERE repo = ? AND id = ?",
                (repo, nid),
            ).fetchone()
            if r is not None:
                node_rows.append(dict(r))
            else:
                # A neighbor reachable via a (still-dangling) edge; surface the id.
                node_rows.append(
                    {"id": nid, "label": None, "source_file": None, "source_location": None}
                )
        edges_out.sort(key=lambda e: (e["source"], e["target"], e["relation"]))
        return {
            "root": node_id,
            "depth": depth,
            "truncated": truncated,
            "nodes": node_rows,
            "edges": edges_out,
        }
    finally:
        conn.close()


def module_map(repo: str, source_file: str | None) -> dict:
    """Map one file: its nodes plus the edges touching them (intra- + inter-file).

    Returns ``{"repo", "source_file", "nodes", "intra_edges", "inter_edges"}``.
    ``intra_edges`` have both endpoints owned by this file; ``inter_edges`` reach
    out to (or in from) another file. Deterministic ordering throughout.
    """
    conn = _connect()
    try:
        _ensure_schema(conn)
        node_rows = conn.execute(
            "SELECT id, label, file_type, source_file, source_location FROM nodes "
            "WHERE repo = ? AND source_file IS ? ORDER BY id",
            (repo, source_file),
        ).fetchall()
        file_ids = {r["id"] for r in node_rows}
        nodes_out = [dict(r) for r in node_rows]

        if not file_ids:
            return {
                "repo": repo,
                "source_file": source_file,
                "nodes": [],
                "intra_edges": [],
                "inter_edges": [],
            }

        placeholders = ", ".join("?" for _ in file_ids)
        ordered_ids = sorted(file_ids)
        # nosec B608 - placeholders are '?' literals; all values parameterized.
        edge_rows = conn.execute(
            "SELECT source, target, relation, weight FROM edges "
            f"WHERE repo = ? AND (source IN ({placeholders}) OR target IN ({placeholders})) "  # nosec B608
            "ORDER BY source, target, relation",
            (repo, *ordered_ids, *ordered_ids),
        ).fetchall()
        intra: list[dict] = []
        inter: list[dict] = []
        for r in edge_rows:
            d = {
                "source": r["source"],
                "target": r["target"],
                "relation": r["relation"],
                "weight": r["weight"],
            }
            if r["source"] in file_ids and r["target"] in file_ids:
                intra.append(d)
            else:
                inter.append(d)
        return {
            "repo": repo,
            "source_file": source_file,
            "nodes": nodes_out,
            "intra_edges": intra,
            "inter_edges": inter,
        }
    finally:
        conn.close()


# ── Optional convenience: shell out to the external graphify extractor ───────


class GraphifyUnavailableError(RuntimeError):
    """graphify is not installed / not on PATH. The extractor is external; memex
    only stores + queries. Install graphify and re-run, or ingest a graph.json
    produced elsewhere via ``ingest_graph``."""


def extract_and_ingest(repo: str, repo_path: str | Path, *, built_at_commit: str | None = None):
    """OPTIONAL one-step convenience: run graphify on ``repo_path`` (AST-only,
    ``--no-cluster``), ingest the resulting throwaway graph.json, discard it.

    Degrades gracefully: raises :class:`GraphifyUnavailableError` with operator
    guidance if graphify is not on PATH — it never crashes the caller and is NOT
    required by any test. memex itself imports nothing from graphify; this just
    drives the external binary as a subprocess.
    """
    graphify_bin = shutil.which("graphify")
    if graphify_bin is None:
        raise GraphifyUnavailableError(
            "graphify is not on PATH. The code-graph EXTRACTOR is external "
            "(AST-only, no API key). Install graphify, then re-run; or produce a "
            "graph.json elsewhere and call code_graph.ingest_graph(repo, path)."
        )
    repo_path = Path(repo_path)
    with tempfile.TemporaryDirectory(prefix="memex-codegraph-") as tmp:
        out = Path(tmp) / "graph.json"
        # Fixed argv list (no shell) with an absolute resolved binary path.
        subprocess.run(  # nosec B603 — fixed argv, resolved binary, no shell
            [graphify_bin, "update", str(repo_path), "--no-cluster", "--output", str(out)],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if not out.is_file():
            raise GraphifyUnavailableError(
                f"graphify ran but produced no graph.json at {out}. Cannot ingest."
            )
        return ingest_graph(repo, out, built_at_commit=built_at_commit)


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 4 and sys.argv[1] == "ingest":
        summary = ingest_graph(sys.argv[2], sys.argv[3])
        print(json.dumps(summary, indent=2))
    elif len(sys.argv) >= 4 and sys.argv[1] == "where-is":
        print(json.dumps(where_is(sys.argv[2], sys.argv[3]), indent=2))
    else:
        print(
            "usage:\n"
            "  python -m scripts.code_graph ingest <owner/repo> <graph.json>\n"
            "  python -m scripts.code_graph where-is <owner/repo> <name>",
            file=sys.stderr,
        )
        sys.exit(2)
