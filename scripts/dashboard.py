"""Memex overview dashboard — a read-only, cross-store summary served locally.

This module is the deterministic backing for ``memex:steward:dashboard``. It

  1. opens every registered store **read-only** and aggregates a JSON-serializable
     summary of what Memex is holding (documents, relations, communities, brain
     captures, the code-navigation graph, the agent registry, and per-store row
     counts), and
  2. serves a single self-contained HTML page plus a ``/api/summary`` JSON
     endpoint over a **loopback-only** stdlib HTTP server.

Design constraints (mirroring the rest of memex):

  * **Stdlib only.** No Flask/FastAPI/jinja — ``http.server`` + ``sqlite3`` +
    ``json``. Memex never imports heavy deps.
  * **Read-only.** Every store is opened with ``mode=ro``; the dashboard never
    writes to any DB, so it is *not* a Librarian write-path bypass (spec §6 /
    M3 govern document *writes*; this is pure observability).
  * **Loopback by default.** The server binds ``127.0.0.1`` and refuses a
    non-local bind unless ``--allow-non-local`` is passed explicitly.
  * **No untrusted templating.** The HTML is a static asset with zero
    server-side interpolation; all data crosses to the browser as JSON and is
    rendered via ``textContent`` (never ``innerHTML`` of data), so a document
    title containing markup cannot become script.
  * **Defensive aggregation.** A missing store, missing table, or empty table
    degrades to ``None``/``[]`` rather than crashing — a freshly bootstrapped
    install (no atelier.db, no code_graph.db) renders cleanly.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scripts import registry
from scripts.db import memex_home, require_bootstrap, safe_identifier

# Hosts we consider "local" — a non-local bind exposes the (read-only, but
# potentially sensitive) contents of your Memex to the network, so it requires
# an explicit opt-in.
# An empty host string is deliberately NOT here: socket.bind(("", port)) means
# INADDR_ANY (0.0.0.0 — all interfaces), the opposite of loopback. serve()
# normalizes "" to 127.0.0.1 before this check so a blank host can never slip
# past the --allow-non-local guard.
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

DEFAULT_PORT = 8765


# ---------------------------------------------------------------------------
# Read-only SQLite helpers (all defensive — never raise on a missing object).
# ---------------------------------------------------------------------------
def _ro_connect(path: str | Path) -> sqlite3.Connection | None:
    """Open a registered store strictly read-only. None if the file is absent or
    cannot be opened (a broken / permission-denied store degrades, never crashes)."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5.0)
    except (sqlite3.Error, OSError):
        return None
    con.row_factory = sqlite3.Row
    return con


def _user_tables(con: sqlite3.Connection) -> list[str]:
    """Real user tables (excludes sqlite internal tables). Empty on any error —
    e.g. a corrupt or locked store — so the summary degrades instead of aborting."""
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    except sqlite3.Error:
        return []
    return [r[0] for r in rows]


def _count(con: sqlite3.Connection, table: str) -> int | None:
    try:
        t = safe_identifier(table)
    except ValueError:
        return None
    try:
        return con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]  # nosec B608 - identifier whitelist-validated
    except sqlite3.Error:
        return None


def _groups(
    con: sqlite3.Connection,
    table: str,
    col: str,
    *,
    limit: int | None = None,
) -> list[dict]:
    """``SELECT col, COUNT(*) ... GROUP BY col ORDER BY count DESC`` — defensive."""
    try:
        t = safe_identifier(table)
        c = safe_identifier(col)
    except ValueError:
        return []
    sql = f'SELECT "{c}" AS k, COUNT(*) AS n FROM "{t}" GROUP BY "{c}" ORDER BY n DESC'  # nosec B608 - identifiers whitelist-validated
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    try:
        return [
            {"key": (r["k"] if r["k"] is not None else "—"), "count": r["n"]}
            for r in con.execute(sql)
        ]
    except sqlite3.Error:
        return []


def _row(con: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Row | None:
    try:
        return con.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None


def _human_bytes(n: int | None) -> str:
    if not n:
        return "0 B"
    step = 1024.0
    val = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if val < step:
            return f"{val:.0f} {unit}" if unit == "B" else f"{val:.1f} {unit}"
        val /= step
    return f"{val:.1f} PB"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Per-store summary sections.
# ---------------------------------------------------------------------------
def _stores_section(records: list[dict]) -> list[dict]:
    """Generic per-store view: file size, schema version, per-table row counts.

    Covers EVERY registered store — including consumer stores memex does not
    own (e.g. atelier.db) — without assuming any schema.
    """
    out: list[dict] = []
    for rec in records:
        path = Path(rec["path"])
        entry = {
            "name": rec["name"],
            "path": str(path),
            "schema_version": rec.get("schema_version"),
            "registered_at": rec.get("registered_at"),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "size_human": _human_bytes(path.stat().st_size if path.exists() else 0),
            "tables": [],
            "total_rows": 0,
        }
        con = _ro_connect(path)
        if con is not None:
            try:
                total = 0
                for tbl in _user_tables(con):
                    n = _count(con, tbl)
                    entry["tables"].append({"name": tbl, "rows": n})
                    if isinstance(n, int):
                        total += n
                entry["total_rows"] = total
            finally:
                con.close()
        out.append(entry)
    return out


def _index_section(path: str | Path) -> dict | None:
    """Federated Index (~/.memex/index.db): documents, relations, communities."""
    con = _ro_connect(path)
    if con is None:
        return None
    try:
        cov = _row(
            con,
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded "
            "FROM documents",
        )
        span = _row(con, "SELECT MIN(created_at) AS lo, MAX(created_at) AS hi FROM documents")
        timeline: list[dict] = []
        try:
            timeline = [
                {"date": r["d"], "count": r["n"]}
                for r in con.execute(
                    "SELECT substr(created_at,1,10) AS d, COUNT(*) AS n "
                    "FROM documents GROUP BY d ORDER BY d ASC"
                )
            ]
        except sqlite3.Error:
            timeline = []
        reports: list[dict] = []
        try:
            reports = [
                {
                    "level": r["level"],
                    "title": r["title"],
                    "rating": r["rating"],
                    "size": r["size"],
                }
                for r in con.execute(
                    "SELECT cr.level AS level, cr.title AS title, cr.rating AS rating, "
                    "c.size AS size FROM community_reports cr "
                    "LEFT JOIN communities c ON c.community_id = cr.community_id "
                    "ORDER BY cr.rating DESC LIMIT 12"
                )
            ]
        except sqlite3.Error:
            reports = []
        return {
            "documents_total": _count(con, "documents"),
            "by_domain": _groups(con, "documents", "domain"),
            "by_store": _groups(con, "documents", "store"),
            "by_table": _groups(con, "documents", "table_name"),
            "by_author": _groups(con, "documents", "created_by", limit=12),
            "embedding_total": (cov["total"] if cov else None),
            "embedding_embedded": (cov["embedded"] if cov else None),
            "relations_total": _count(con, "relations"),
            "relations_by_type": _groups(con, "relations", "rel_type"),
            "communities_total": _count(con, "communities"),
            "communities_by_level": _groups(con, "communities", "level"),
            "community_reports_total": _count(con, "community_reports"),
            "top_reports": reports,
            "oldest": (span["lo"] if span else None),
            "newest": (span["hi"] if span else None),
            "timeline": timeline,
        }
    finally:
        con.close()


def _brain_section(path: str | Path) -> dict | None:
    """Brain default store (article.db): articles, captures, syntheses."""
    con = _ro_connect(path)
    if con is None:
        return None
    try:
        cap_span = _row(con, "SELECT MIN(created_at) AS lo, MAX(created_at) AS hi FROM captures")
        return {
            "articles": _count(con, "articles"),
            "captures": _count(con, "captures"),
            "syntheses": _count(con, "syntheses"),
            "captures_oldest": (cap_span["lo"] if cap_span else None),
            "captures_newest": (cap_span["hi"] if cap_span else None),
        }
    finally:
        con.close()


def _agents_section(path: str | Path) -> dict | None:
    """Universal role/agent registry (agents.db)."""
    con = _ro_connect(path)
    if con is None:
        return None
    try:
        per_role: list[dict] = []
        try:
            per_role = [
                {"key": r["name"], "count": r["n"]}
                for r in con.execute(
                    "SELECT r.name AS name, COUNT(a.id) AS n FROM roles r "
                    "LEFT JOIN agents a ON a.role_id = r.id "
                    "GROUP BY r.id HAVING n > 0 ORDER BY n DESC LIMIT 12"
                )
            ]
        except sqlite3.Error:
            per_role = []
        return {
            "roles_total": _count(con, "roles"),
            "agents_total": _count(con, "agents"),
            "agents_per_role": per_role,
        }
    finally:
        con.close()


def _codegraph_section(path: str | Path) -> dict | None:
    """Code-navigation graph (code_graph.db) — separate store, per-repo rollup."""
    con = _ro_connect(path)
    if con is None:
        return None
    try:
        per_repo: list[dict] = []
        try:
            per_repo = [
                {
                    "repo": r["repo"],
                    "nodes": r["nn"],
                    "edges": r["ne"],
                    "needs_update": bool(r["needs_update"]),
                    "built_at_commit": r["built_at_commit"],
                }
                for r in con.execute(
                    "SELECT r.repo AS repo, r.needs_update AS needs_update, "
                    "r.built_at_commit AS built_at_commit, "
                    "(SELECT COUNT(*) FROM nodes n WHERE n.repo = r.repo) AS nn, "
                    "(SELECT COUNT(*) FROM edges e WHERE e.repo = r.repo) AS ne "
                    "FROM repos r ORDER BY nn DESC"
                )
            ]
        except sqlite3.Error:
            per_repo = []
        return {
            "repos_total": _count(con, "repos"),
            "nodes_total": _count(con, "nodes"),
            "edges_total": _count(con, "edges"),
            "per_repo": per_repo,
            "edges_by_relation": _groups(con, "edges", "relation", limit=15),
            "nodes_by_file_type": _groups(con, "nodes", "file_type", limit=10),
        }
    finally:
        con.close()


def _load_raw_registry() -> dict:
    """Raw registry.json (includes the ``__embedding_model__`` config blob that
    ``registry.list_stores()`` filters out)."""
    p = memex_home() / "registry.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def build_summary() -> dict:
    """Aggregate the full cross-store summary. Read-only; never mutates a store.

    Raises ``MemexNotInitializedError`` if Memex is not bootstrapped.
    """
    require_bootstrap()
    home = memex_home()
    records = registry.list_stores()
    by_name = {r["name"]: r for r in records}
    raw = _load_raw_registry()

    index = _index_section(by_name["index"]["path"]) if "index" in by_name else None
    brain = _brain_section(by_name["article"]["path"]) if "article" in by_name else None
    agents = _agents_section(by_name["agents"]["path"]) if "agents" in by_name else None

    # code_graph.db (v2.9.0) is a SEPARATE, fixed-path store — it is NOT in the
    # registry, so resolve it directly under memex_home and surface it as an
    # (unregistered) store in the overview when present on disk.
    code_graph_path = home / "code_graph.db"
    code_graph = _codegraph_section(code_graph_path)
    known_paths = {str(Path(r["path"])) for r in records}
    all_records = list(records)
    if code_graph_path.exists() and str(code_graph_path) not in known_paths:
        all_records.append(
            {
                "name": "code_graph",
                "path": str(code_graph_path),
                "schema_version": None,
                "registered_at": None,
            }
        )
    stores = _stores_section(all_records)

    totals = {
        "stores": len(all_records),
        "total_rows": sum(s["total_rows"] for s in stores),
        "documents": (index or {}).get("documents_total") or 0,
        "relations": (index or {}).get("relations_total") or 0,
        "communities": (index or {}).get("communities_total") or 0,
        "captures": (brain or {}).get("captures") or 0,
        "articles": (brain or {}).get("articles") or 0,
        "agents": (agents or {}).get("agents_total") or 0,
        "roles": (agents or {}).get("roles_total") or 0,
        "code_repos": (code_graph or {}).get("repos_total") or 0,
        "code_nodes": (code_graph or {}).get("nodes_total") or 0,
        "code_edges": (code_graph or {}).get("edges_total") or 0,
    }

    return {
        "generated_at": _now_iso(),
        "memex_home": str(memex_home()),
        "embedding_model": raw.get("__embedding_model__"),
        "totals": totals,
        "stores": stores,
        "index": index,
        "brain": brain,
        "agents": agents,
        "code_graph": code_graph,
    }


# ---------------------------------------------------------------------------
# Knowledge-graph projection — documents as nodes, relations as edges, colored
# by community. This is the Obsidian-graph analog (the federated index), served
# to the 3D viewer at /graph. Read-only and defensive like build_summary.
# ---------------------------------------------------------------------------
# Capped low because the viewer's force layout is O(n²) on the browser main
# thread (no WebGL/worker). ~900 keeps both the pre-layout burst and per-frame
# settling smooth; larger graphs are truncated (surfaced via the `truncated`
# flag). A personal knowledge index is typically in the hundreds.
_GRAPH_MAX_NODES = 900


def _node_label(row: sqlite3.Row) -> str:
    """A short human label for a document node: prefer the explicit key, then a
    title-ish field from JSON metadata, then domain:row_id. Capped in length."""
    key = row["key"]
    if key:
        return str(key)[:80]
    md = row["metadata"]
    if md:
        try:
            data = json.loads(md)
            if isinstance(data, dict):
                for field in ("title", "name", "topic"):
                    val = data.get(field)
                    if val:
                        return str(val)[:80]
        except (ValueError, TypeError):
            pass
    base = row["domain"] or row["table_name"] or "node"
    return f"{base}:{row['row_id']}"[:80]


def build_graph(max_nodes: int = _GRAPH_MAX_NODES) -> dict:
    """Build the federated-index knowledge graph as ``{nodes, links, truncated}``.

    Nodes are `documents`; links are `relations` whose BOTH endpoints are in the
    returned node set (dangling/self-referential edges are dropped). Read-only;
    degrades to an empty graph if the index store or a table is missing.
    """
    require_bootstrap()
    records = {r["name"]: r for r in registry.list_stores()}
    empty = {"nodes": [], "links": [], "truncated": False}
    if "index" not in records:
        return empty
    con = _ro_connect(records["index"]["path"])
    if con is None:
        return empty
    try:
        # Community membership at the base level → node color groups.
        community: dict[str, str] = {}
        try:
            for r in con.execute(
                "SELECT index_id, community_id FROM community_members WHERE level = 0"
            ):
                community[r["index_id"]] = r["community_id"]
        except sqlite3.Error:
            community = {}

        try:
            rows = con.execute(
                "SELECT index_id, key, domain, table_name, row_id, metadata "
                "FROM documents ORDER BY created_at, index_id LIMIT ?",  # index_id tiebreaker → stable truncation
                (max_nodes + 1,),
            ).fetchall()
        except sqlite3.Error:
            return empty

        truncated = len(rows) > max_nodes
        rows = rows[:max_nodes]
        ids = {r["index_id"] for r in rows}
        nodes = [
            {
                "id": r["index_id"],
                "label": _node_label(r),
                "domain": r["domain"],
                "community": community.get(r["index_id"]),
            }
            for r in rows
        ]

        links = []
        try:
            for r in con.execute(
                "SELECT from_index_id, to_index_id, rel_type, confidence FROM relations"
            ):
                src, dst = r["from_index_id"], r["to_index_id"]
                if src != dst and src in ids and dst in ids:
                    links.append(
                        {
                            "source": src,
                            "target": dst,
                            "type": r["rel_type"],
                            "confidence": r["confidence"],
                        }
                    )
        except sqlite3.Error:
            links = []

        return {"nodes": nodes, "links": links, "truncated": truncated}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Keyword search + document content. Search runs over the federated index
# (FTS5 over `documents.searchable`, with a LIKE fallback). Content is fetched
# from the SOURCE store by `index_id` (the universal join key) since
# `searchable` is tokenized, not the original body. All read-only.
# ---------------------------------------------------------------------------
_SEARCH_LIMIT = 50
_MAX_CONTENT = 500_000  # cap on content CHARACTERS shipped to the browser per document
# Source columns that hold human-readable content, in display priority.
_CONTENT_COLS = ["body", "content", "text", "summary", "decisions", "description", "notes", "topic"]


def _search_result(r: sqlite3.Row) -> dict:
    return {
        "id": r["index_id"],
        "title": _node_label(r),
        "domain": r["domain"],
        "store": r["store"],
        "snippet": (r["snip"] or "").strip() if r["snip"] is not None else "",
    }


def _fts_search(con: sqlite3.Connection, q: str, limit: int) -> list | None:
    """FTS5 prefix search. Returns rows, or None if FTS is unavailable (caller
    falls back to LIKE). Tokens are reduced to word chars, so the bound MATCH
    string can never carry FTS5 query-syntax metacharacters."""
    tokens = re.findall(r"\w+", q.lower())
    if not tokens:
        return None  # nothing tokenizable → let build_search fall through to LIKE
    match = " ".join(f"{t}*" for t in tokens)
    try:
        return con.execute(
            "SELECT d.index_id AS index_id, d.key AS key, d.domain AS domain, d.store AS store, "
            "d.table_name AS table_name, d.row_id AS row_id, d.metadata AS metadata, "
            "snippet(documents_fts, 0, '[', ']', '…', 12) AS snip "
            "FROM documents_fts JOIN documents d ON d.rowid = documents_fts.rowid "
            "WHERE documents_fts MATCH ? ORDER BY rank LIMIT ?",
            (match, limit),
        ).fetchall()
    except sqlite3.Error:
        return None


def _like_search(con: sqlite3.Connection, q: str, limit: int) -> list:
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pat = f"%{esc}%"
    try:
        return con.execute(
            "SELECT index_id, key, domain, store, table_name, row_id, metadata, "
            "substr(searchable, 1, 180) AS snip FROM documents "
            "WHERE searchable LIKE ? ESCAPE '\\' OR key LIKE ? ESCAPE '\\' "
            "ORDER BY created_at DESC LIMIT ?",
            (pat, pat, limit),
        ).fetchall()
    except sqlite3.Error:
        return []


def build_search(q: str, limit: int = _SEARCH_LIMIT) -> dict:
    """Keyword search across the federated index. Read-only."""
    require_bootstrap()
    q = (q or "").strip()
    base = {"results": [], "count": 0, "truncated": False, "query": q}
    if not q:
        return base
    records = {r["name"]: r for r in registry.list_stores()}
    if "index" not in records:
        return base
    con = _ro_connect(records["index"]["path"])
    if con is None:
        return base
    try:
        rows = _fts_search(con, q, limit + 1)
        if rows is None:
            rows = _like_search(con, q, limit + 1)
        truncated = len(rows) > limit
        results = [_search_result(r) for r in rows[:limit]]
        return {"results": results, "count": len(results), "truncated": truncated, "query": q}
    finally:
        con.close()


def _extract_content(srow: sqlite3.Row) -> list[tuple[str, str]]:
    keys = set(srow.keys())
    parts = []
    for col in _CONTENT_COLS:
        if col in keys:
            val = srow[col]
            if isinstance(val, str) and val.strip():
                parts.append((col, val))
    return parts


def _capped(text: str) -> tuple[str, bool]:
    """Truncate to _MAX_CONTENT characters; report whether truncation happened."""
    return (text[:_MAX_CONTENT], True) if len(text) > _MAX_CONTENT else (text, False)


def _fetch_content(records: dict, d: sqlite3.Row) -> tuple[str, str, bool]:
    """Best-effort document body from the source store, joined by index_id.
    Returns (text, source, truncated) where source is 'source'|'searchable'|'none'."""
    store, table, index_id = d["store"], d["table_name"], d["index_id"]
    if store in records:
        try:
            tname = safe_identifier(table)
        except ValueError:
            tname = None
        scon = _ro_connect(records[store]["path"]) if tname else None
        if scon is not None:
            try:
                cols = [r[1] for r in scon.execute(f'PRAGMA table_info("{tname}")')]  # nosec B608 - identifier validated
                srow = None
                if "index_id" in cols:
                    srow = _row(scon, f'SELECT * FROM "{tname}" WHERE index_id = ?', (index_id,))  # nosec B608 - identifier validated
                elif "id" in cols:
                    srow = _row(scon, f'SELECT * FROM "{tname}" WHERE id = ?', (d["row_id"],))  # nosec B608 - identifier validated
                if srow is not None:
                    parts = _extract_content(srow)
                    if parts:
                        text = (
                            parts[0][1]
                            if len(parts) == 1
                            else "\n\n".join(f"## {label}\n{body}" for label, body in parts)
                        )
                        capped, truncated = _capped(text)
                        return capped, "source", truncated
            except sqlite3.Error:
                pass
            finally:
                scon.close()
    sval = d["searchable"]
    if sval:
        capped, truncated = _capped(str(sval))
        return capped, "searchable", truncated
    return "(no stored content for this document)", "none", False


def build_doc(index_id: str) -> dict:
    """Full record + best-effort content for one document. Read-only."""
    require_bootstrap()
    index_id = (index_id or "").strip()
    if not index_id:
        return {"error": "missing document id"}
    records = {r["name"]: r for r in registry.list_stores()}
    if "index" not in records:
        return {"error": "index store not available"}
    con = _ro_connect(records["index"]["path"])
    if con is None:
        return {"error": "index store not available"}
    try:
        d = _row(
            con,
            "SELECT index_id, key, domain, store, table_name, row_id, created_by, created_at, "
            "metadata, searchable FROM documents WHERE index_id = ?",
            (index_id,),
        )
        if d is None:
            return {"error": "document not found"}
        meta = None
        if d["metadata"]:
            try:
                meta = json.loads(d["metadata"])
            except (ValueError, TypeError):
                meta = d["metadata"]
        content, source, truncated = _fetch_content(records, d)
        return {
            "id": d["index_id"],
            "title": _node_label(d),
            "domain": d["domain"],
            "store": d["store"],
            "table_name": d["table_name"],
            "created_by": d["created_by"],
            "created_at": d["created_at"],
            "metadata": meta,
            "content": content,
            "content_source": source,
            "content_truncated": truncated,
        }
    finally:
        con.close()


# ---------------------------------------------------------------------------
# HTTP layer — loopback-only, fixed routes, no filesystem serving.
# ---------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    server_version = "MemexDashboard"
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; connect-src 'self'; "
            "base-uri 'none'; form-action 'none'",
        )
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, builder) -> None:
        """Serialize ``builder()`` to JSON; emit a clean 500 JSON on any error
        (never a stack-trace page)."""
        try:
            payload = json.dumps(builder(), ensure_ascii=False, default=str)
            self._send(200, payload.encode("utf-8"), "application/json; charset=utf-8")
        except Exception as exc:
            # Detail goes to the operator's stderr only; the response stays generic
            # so a --allow-non-local bind can't echo internal paths to the network.
            print(f"[dashboard] request failed: {exc}", file=sys.stderr)
            body = json.dumps({"error": "internal error"}).encode("utf-8")
            self._send(500, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # http.server dispatch hook
        parsed = urlparse(self.path)
        route = parsed.path
        if route in ("/", "/index.html"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/graph":
            self._send(200, GRAPH_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/api/summary":
            self._send_json(build_summary)
        elif route == "/api/graph":
            self._send_json(build_graph)
        elif route == "/api/search":
            q = parse_qs(parsed.query).get("q", [""])[0]
            self._send_json(lambda: build_search(q))
        elif route == "/api/doc":
            doc_id = parse_qs(parsed.query).get("id", [""])[0]
            self._send_json(lambda: build_doc(doc_id))
        elif route == "/healthz":
            self._send(200, b'{"ok":true}', "application/json; charset=utf-8")
        else:
            self._send(404, b'{"error":"not found"}', "application/json; charset=utf-8")

    def do_HEAD(self) -> None:  # http.server dispatch hook
        self.do_GET()

    def log_message(self, *args) -> None:  # quiet by default; --verbose re-enables
        if getattr(self.server, "verbose", False):
            super().log_message(*args)


def _make_server(
    host: str,
    port: int,
    *,
    bind_retries: int = 20,
    allow_non_local: bool = False,
    verbose: bool = False,
) -> ThreadingHTTPServer:
    """Bind a loopback-guarded server, scanning forward from ``port`` for a free
    one. Raises ``SystemExit`` on a disallowed non-local host or when no port in
    the scan range is free. Returns the already-bound server.

    Split out from ``serve()`` (which then blocks on ``serve_forever``) so the
    host guard and the port-scan are unit-testable without a blocking call.
    """
    # Normalize before the guard: "" would otherwise pass as "local" yet bind
    # 0.0.0.0 (all interfaces). Treat a blank host as loopback.
    host = host or "127.0.0.1"
    if host not in _LOOPBACK_HOSTS and not allow_non_local:
        raise SystemExit(
            f"Refusing to bind non-local host {host!r}: the dashboard exposes your "
            f"Memex contents. Pass --allow-non-local to override (use with care)."
        )

    last_err: OSError | None = None
    for candidate in range(port, port + max(1, bind_retries)):
        try:
            httpd = ThreadingHTTPServer((host, candidate), _Handler)
            break
        except OSError as exc:  # port in use → try the next one
            last_err = exc
    else:
        raise SystemExit(
            f"Could not bind {host} on ports {port}..{port + bind_retries - 1}: {last_err}"
        )

    httpd.verbose = verbose  # type: ignore[attr-defined]
    return httpd


def _display_url(host: str, port: int) -> str:
    """Human-facing URL for the bound server, with IPv6 literals bracketed."""
    host = host or "127.0.0.1"
    disp = f"[{host}]" if ":" in host else host
    return f"http://{disp}:{port}/"


def serve(
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    *,
    open_browser: bool = True,
    bind_retries: int = 20,
    allow_non_local: bool = False,
    verbose: bool = False,
) -> None:
    """Start the dashboard server (blocking until Ctrl-C)."""
    host = host or "127.0.0.1"
    httpd = _make_server(
        host, port, bind_retries=bind_retries, allow_non_local=allow_non_local, verbose=verbose
    )
    url = _display_url(host, httpd.server_address[1])
    print(f"Memex dashboard → {url}")
    print("Press Ctrl-C to stop.")
    if open_browser:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:  # headless / no browser registered — URL already printed
            print("(could not auto-open a browser — open the URL above manually)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Memex dashboard.")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.dashboard",
        description="Serve (or print) a read-only summary of everything stored in Memex.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="bind port (default 8765)")
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    parser.add_argument(
        "--allow-non-local",
        action="store_true",
        help="permit binding a non-loopback host (exposes Memex to the network)",
    )
    parser.add_argument("--verbose", action="store_true", help="log each HTTP request")
    parser.add_argument(
        "--once",
        action="store_true",
        help="print the summary JSON to stdout and exit (no server)",
    )
    args = parser.parse_args(argv)

    if args.once:
        print(json.dumps(build_summary(), indent=2, ensure_ascii=False, default=str))
        return 0

    serve(
        host=args.host,
        port=args.port,
        open_browser=not args.no_open,
        allow_non_local=args.allow_non_local,
        verbose=args.verbose,
    )
    return 0


# ---------------------------------------------------------------------------
# Shared document-content overlay — injected into BOTH the dashboard and the 3D
# graph at the OVERLAY_* placeholders. openDoc(id) fetches /api/doc and renders
# the body via textContent only (no innerHTML of data → no XSS from stored text).
# ---------------------------------------------------------------------------
_OVERLAY_CSS = r"""
  .doc-backdrop { position:fixed; inset:0; background:rgba(2,5,10,.66); display:none; z-index:60; }
  .doc-backdrop.open { display:flex; align-items:flex-start; justify-content:center; }
  .doc-modal { margin-top:5vh; width:min(840px,92vw); max-height:88vh; background:#0d1117; color:#e6edf3;
    border:1px solid #2b3340; border-radius:12px; box-shadow:0 16px 60px #000c; display:flex; flex-direction:column; overflow:hidden; }
  .doc-head { display:flex; align-items:flex-start; gap:12px; padding:14px 16px; border-bottom:1px solid #2b3340; }
  .doc-title { font-size:16px; font-weight:650; word-break:break-word; }
  .doc-meta { color:#8b949e; font-size:12px; margin-top:3px; font-family:ui-monospace,Menlo,monospace; word-break:break-word; }
  .doc-head-btns { margin-left:auto; display:flex; gap:6px; flex:0 0 auto; }
  .doc-close, .doc-toggle { background:#1c2330; color:#e6edf3; border:1px solid #2b3340; border-radius:6px;
    height:30px; line-height:1; cursor:pointer; }
  .doc-close { width:30px; font-size:18px; }
  .doc-toggle { padding:0 10px; font-size:12px; }
  .doc-close:hover, .doc-toggle:hover { border-color:#58a6ff; }
  .doc-srcnote { color:#8b949e; font-size:11px; padding:8px 16px 0; font-style:italic; }
  .doc-body { overflow:auto; padding:12px 16px 16px; }
  /* raw view (<pre class=doc-raw>) */
  .doc-raw { margin:0; white-space:pre-wrap; word-break:break-word; font:13px/1.55 ui-monospace,Menlo,Consolas,monospace; color:#c9d1d9; }
  /* rendered markdown */
  .doc-md { font:14px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; color:#d6dde5; }
  .doc-md h1,.doc-md h2,.doc-md h3,.doc-md h4,.doc-md h5,.doc-md h6 { line-height:1.3; margin:1.1em 0 .5em; color:#e6edf3; }
  .doc-md h1 { font-size:1.55em; border-bottom:1px solid #2b3340; padding-bottom:.25em; }
  .doc-md h2 { font-size:1.32em; border-bottom:1px solid #2b3340; padding-bottom:.2em; }
  .doc-md h3 { font-size:1.15em; } .doc-md h4 { font-size:1.02em; }
  .doc-md p { margin:.6em 0; } .doc-md *:first-child { margin-top:0; }
  .doc-md ul,.doc-md ol { margin:.5em 0; padding-left:1.5em; } .doc-md li { margin:.2em 0; }
  .doc-md a { color:#58a6ff; text-decoration:none; } .doc-md a:hover { text-decoration:underline; }
  .doc-md code { background:#161b22; border:1px solid #2b3340; border-radius:4px; padding:.08em .35em;
    font:.88em ui-monospace,Menlo,Consolas,monospace; color:#e6edf3; }
  .doc-md pre.md-pre, .doc-md pre.md-frontmatter { background:#161b22; border:1px solid #2b3340; border-radius:8px;
    padding:10px 12px; overflow:auto; margin:.7em 0; }
  .doc-md pre code { background:none; border:none; padding:0; font-size:.86em; color:#c9d1d9;
    white-space:pre; display:block; line-height:1.5; }
  .doc-md pre.md-frontmatter { color:#8b949e; font:.82em ui-monospace,Menlo,Consolas,monospace; white-space:pre-wrap; }
  .doc-md blockquote { margin:.6em 0; padding:.1em .9em; border-left:3px solid #2b3340; color:#9aa4af; }
  .doc-md hr { border:none; border-top:1px solid #2b3340; margin:1em 0; }
  .doc-md strong { color:#e6edf3; } .doc-md em { font-style:italic; }
  .doc-md table { border-collapse:collapse; margin:.7em 0; display:block; overflow:auto; max-width:100%; }
  .doc-md th,.doc-md td { border:1px solid #2b3340; padding:5px 10px; text-align:left; vertical-align:top; }
  .doc-md th { background:#161b22; font-weight:650; color:#e6edf3; }
"""

_OVERLAY_MARKUP = r"""
<div class="doc-backdrop" id="docOverlay">
  <div class="doc-modal" role="dialog" aria-modal="true" aria-labelledby="docTitle">
    <div class="doc-head">
      <div>
        <div class="doc-title" id="docTitle"></div>
        <div class="doc-meta" id="docMeta"></div>
      </div>
      <div class="doc-head-btns">
        <button class="doc-toggle" id="docToggle" title="Toggle rendered / raw">raw</button>
        <button class="doc-close" id="docClose" aria-label="Close">&times;</button>
      </div>
    </div>
    <div class="doc-srcnote" id="docSrcNote"></div>
    <div class="doc-body"><div id="docContent" class="doc-md"></div></div>
  </div>
</div>
"""

_OVERLAY_JS = r"""
// --- safe Markdown renderer: builds DOM nodes (textContent / createElement /
// sanitized hrefs / whitelisted elements). Raw HTML in the source is NEVER
// parsed — it lands as inert text — so an adversarial ingested body cannot XSS.
function _mdSanitizeHref(url) {
  const u = String(url).trim();
  if (/^(https?:|mailto:)/i.test(u)) return u;          // safe schemes
  if (/^[/#]/.test(u) || /^\.{1,2}\//.test(u)) return u; // relative / anchor
  return null;                                           // reject javascript:, data:, etc.
}
function _mdInline(parent, text) {
  text = String(text);
  // Bound inline parsing: the regex can backtrack quadratically on a pathological
  // single run (e.g. a 500k-char body of '['), so very long buffers render as
  // plain text instead of freezing the tab.
  if (text.length > 20000) { parent.appendChild(document.createTextNode(text)); return; }
  // Code spans first (their contents are literal), then bold, italic, links.
  const re = /(`+)([^`]+?)\1|\*\*([^*]+?)\*\*|\*([^*\s][^*]*?)\*|\[([^\]]+)\]\(([^)\s]+)\)/;
  let rest = text;
  while (rest.length) {
    const m = re.exec(rest);
    if (!m) { parent.appendChild(document.createTextNode(rest)); break; }
    if (m.index > 0) parent.appendChild(document.createTextNode(rest.slice(0, m.index)));
    if (m[1] !== undefined) { const c = document.createElement("code"); c.textContent = m[2]; parent.appendChild(c); }
    else if (m[3] !== undefined) { const s = document.createElement("strong"); _mdInline(s, m[3]); parent.appendChild(s); }
    else if (m[4] !== undefined) { const e = document.createElement("em"); _mdInline(e, m[4]); parent.appendChild(e); }
    else { const href = _mdSanitizeHref(m[6]);
      if (href) { const a = document.createElement("a"); a.textContent = m[5]; a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer"; parent.appendChild(a); }
      else { parent.appendChild(document.createTextNode(m[0])); } }
    rest = rest.slice(m.index + m[0].length);
  }
}
function renderMarkdown(container, text, depth) {
  depth = depth || 0;
  container.textContent = "";
  if (depth > 8) {  // cap blockquote nesting so an adversarial `>>>>…` body can't overflow the stack
    const p = document.createElement("p"); p.textContent = String(text); container.appendChild(p); return;
  }
  const lines = String(text).replace(/\r\n?/g, "\n").split("\n");
  let i = 0;
  // leading YAML frontmatter → muted block
  if (/^---\s*$/.test(lines[0] || "")) {
    let j = 1;
    while (j < lines.length && !/^---\s*$/.test(lines[j])) j++;
    if (j < lines.length) {
      const fm = document.createElement("pre"); fm.className = "md-frontmatter";
      fm.textContent = lines.slice(1, j).join("\n"); container.appendChild(fm); i = j + 1;
    }
  }
  while (i < lines.length) {
    const line = lines[i];
    const fence = line.match(/^\s{0,3}(```+|~~~+)/);
    if (fence) {
      const mark = fence[1][0]; i++; const buf = [];
      while (i < lines.length && !(new RegExp("^\\s{0,3}[" + mark + "]{3,}\\s*$").test(lines[i]))) { buf.push(lines[i]); i++; }
      i++;
      const pre = document.createElement("pre"); pre.className = "md-pre";
      const code = document.createElement("code"); code.textContent = buf.join("\n");
      pre.appendChild(code); container.appendChild(pre); continue;
    }
    if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) { container.appendChild(document.createElement("hr")); i++; continue; }
    const h = line.match(/^\s{0,3}(#{1,6})\s+(.*)$/);
    if (h) { const el = document.createElement("h" + h[1].length); _mdInline(el, h[2].replace(/\s+#+\s*$/, "")); container.appendChild(el); i++; continue; }
    if (/^\s{0,3}>/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s{0,3}>/.test(lines[i])) { buf.push(lines[i].replace(/^\s{0,3}>\s?/, "")); i++; }
      const bq = document.createElement("blockquote"); renderMarkdown(bq, buf.join("\n"), depth + 1); container.appendChild(bq); continue;
    }
    if (/^\s{0,3}([-*+]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s{0,3}\d+[.)]\s+/.test(line);
      const itemRe = ordered ? /^\s{0,3}\d+[.)]\s+/ : /^\s{0,3}[-*+]\s+/;  // a marker-family switch ends the list
      const list = document.createElement(ordered ? "ol" : "ul");
      while (i < lines.length && itemRe.test(lines[i])) {
        const li = document.createElement("li"); _mdInline(li, lines[i].replace(itemRe, "")); list.appendChild(li); i++;
      }
      container.appendChild(list); continue;
    }
    // GFM pipe table: a header row containing a pipe, then a |---|---| delimiter row.
    if (line.indexOf("|") !== -1 && i + 1 < lines.length
        && /^\s{0,3}\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/.test(lines[i + 1])) {
      const splitRow = (s) => s.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const table = document.createElement("table");
      const thead = document.createElement("thead"); const htr = document.createElement("tr");
      splitRow(line).forEach((c) => { const th = document.createElement("th"); _mdInline(th, c); htr.appendChild(th); });
      thead.appendChild(htr); table.appendChild(thead);
      i += 2;
      const tbody = document.createElement("tbody");
      while (i < lines.length && lines[i].indexOf("|") !== -1 && !/^\s*$/.test(lines[i])) {
        const tr = document.createElement("tr");
        splitRow(lines[i]).forEach((c) => { const td = document.createElement("td"); _mdInline(td, c); tr.appendChild(td); });
        tbody.appendChild(tr); i++;
      }
      table.appendChild(tbody); container.appendChild(table); continue;
    }
    if (/^\s*$/.test(line)) { i++; continue; }
    const buf = [line]; i++;
    while (i < lines.length && !/^\s*$/.test(lines[i])
        && !/^\s{0,3}(#{1,6}\s|>|([-*+]|\d+[.)])\s|```|~~~)/.test(lines[i])
        && !/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(lines[i])) { buf.push(lines[i]); i++; }
    const p = document.createElement("p"); _mdInline(p, buf.join("\n")); container.appendChild(p);
  }
}

let _docPrevFocus = null, _docRaw = "", _docRawMode = false;
function _docRenderBody() {
  const body = document.getElementById("docContent");
  body.textContent = "";
  if (_docRawMode) {
    body.classList.remove("doc-md");
    const pre = document.createElement("pre"); pre.className = "doc-raw"; pre.textContent = _docRaw; body.appendChild(pre);
  } else { body.classList.add("doc-md"); renderMarkdown(body, _docRaw); }
  document.getElementById("docToggle").textContent = _docRawMode ? "rendered" : "raw";
}
async function openDoc(id) {
  const ov = document.getElementById("docOverlay");
  const title = document.getElementById("docTitle");
  const meta = document.getElementById("docMeta");
  const note = document.getElementById("docSrcNote");
  _docPrevFocus = document.activeElement;  // restore focus on close (a11y)
  _docRawMode = false;
  title.textContent = "Loading…"; meta.textContent = ""; note.textContent = "";
  document.getElementById("docContent").textContent = "";
  ov.classList.add("open");
  document.getElementById("docClose").focus();
  try {
    const r = await fetch("/api/doc?id=" + encodeURIComponent(id), { cache: "no-store" });
    const d = await r.json();
    if (d.error) { title.textContent = "Not available"; _docRaw = d.error; _docRenderBody(); return; }
    title.textContent = d.title || d.id;
    meta.textContent = [d.domain, d.store, d.created_at, d.created_by].filter(Boolean).join("  ·  ");
    note.textContent = d.content_source === "searchable"
      ? "showing indexed text — original source body unavailable"
      : d.content_source === "none" ? "no stored content for this document"
      : d.content_truncated ? "showing the first part — document exceeds the display limit" : "";
    _docRaw = d.content || "(empty)";
    _docRenderBody();
    document.querySelector("#docOverlay .doc-body").scrollTop = 0;
  } catch (e) { title.textContent = "Error"; _docRaw = "Could not load document: " + e.message; _docRenderBody(); }
}
function closeDoc() {
  document.getElementById("docOverlay").classList.remove("open");
  if (_docPrevFocus && _docPrevFocus.focus) _docPrevFocus.focus();
}
document.getElementById("docToggle").addEventListener("click", () => { _docRawMode = !_docRawMode; _docRenderBody(); });
document.getElementById("docClose").addEventListener("click", closeDoc);
document.getElementById("docOverlay").addEventListener("click", (e) => { if (e.target.id === "docOverlay") closeDoc(); });
document.addEventListener("keydown", (e) => {
  if (!document.getElementById("docOverlay").classList.contains("open")) return;
  if (e.key === "Escape") closeDoc();
  else if (e.key === "Tab") { e.preventDefault(); document.getElementById("docClose").focus(); }  // trap focus in the dialog
});
"""


# ---------------------------------------------------------------------------
# The single-page dashboard. Static asset, no server-side interpolation — all
# data arrives via fetch('/api/summary') and is rendered with textContent.
# ---------------------------------------------------------------------------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Memex — knowledge dashboard</title>
<style>
  :root {
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2330; --border:#2b3340;
    --fg:#e6edf3; --muted:#8b949e; --accent:#58a6ff; --accent2:#bc8cff;
    --good:#3fb950; --warn:#d29922; --bar:#388bfd; --bar2:#a371f7;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--bg); color:var(--fg);
    font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  }
  header {
    position:sticky; top:0; z-index:5; background:rgba(13,17,23,.92);
    backdrop-filter:blur(6px); border-bottom:1px solid var(--border);
    padding:14px 24px; display:flex; align-items:center; gap:16px; flex-wrap:wrap;
  }
  header h1 { font-size:18px; margin:0; letter-spacing:.3px; }
  header h1 .dot { color:var(--accent2); }
  header .home { color:var(--muted); font-size:12px; font-family:ui-monospace,Menlo,monospace; }
  header .spacer { flex:1; }
  header .meta { color:var(--muted); font-size:12px; }
  button {
    background:var(--panel2); color:var(--fg); border:1px solid var(--border);
    border-radius:6px; padding:6px 12px; cursor:pointer; font-size:13px;
  }
  button:hover { border-color:var(--accent); }
  .btn-link {
    background:var(--panel2); color:var(--fg); border:1px solid var(--border);
    border-radius:6px; padding:6px 12px; font-size:13px; text-decoration:none;
  }
  .btn-link:hover { border-color:var(--accent2); color:var(--accent2); }
  label.toggle { color:var(--muted); font-size:12px; display:flex; align-items:center; gap:6px; cursor:pointer; }
  main { padding:24px; max-width:1280px; margin:0 auto; }
  .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:24px; }
  .kpi { background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
  .kpi .v { font-size:26px; font-weight:650; }
  .kpi .l { color:var(--muted); font-size:12px; margin-top:2px; text-transform:uppercase; letter-spacing:.5px; }
  section { margin-bottom:28px; }
  section > h2 { font-size:15px; margin:0 0 12px; padding-bottom:6px; border-bottom:1px solid var(--border); color:var(--fg); }
  section > h2 .c { color:var(--muted); font-weight:400; font-size:13px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; }
  .card { background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
  .card h3 { margin:0 0 10px; font-size:13px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; font-weight:600; }
  .bar { display:flex; align-items:center; gap:8px; margin:5px 0; }
  .bar .name { width:42%; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:13px; }
  .bar .track { flex:1; background:var(--panel2); border-radius:4px; height:14px; overflow:hidden; }
  .bar .fill { height:100%; background:linear-gradient(90deg,var(--bar),var(--bar2)); border-radius:4px; min-width:2px; }
  .bar .n { width:54px; text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; font-size:12px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--border); }
  th { color:var(--muted); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.4px; }
  td.num,th.num { text-align:right; font-variant-numeric:tabular-nums; }
  td.mono { font-family:ui-monospace,Menlo,monospace; font-size:12px; color:var(--muted); word-break:break-all; }
  .pill { display:inline-block; padding:1px 7px; border-radius:999px; font-size:11px; border:1px solid var(--border); color:var(--muted); }
  .pill.warn { color:var(--warn); border-color:var(--warn); }
  .pill.good { color:var(--good); border-color:var(--good); }
  .spark { display:flex; align-items:flex-end; gap:2px; height:60px; margin-top:6px; }
  .spark .b { flex:1; background:linear-gradient(180deg,var(--bar2),var(--bar)); border-radius:2px 2px 0 0; min-height:2px; }
  .spark .b:hover { filter:brightness(1.3); }
  .muted { color:var(--muted); }
  .empty { color:var(--muted); font-style:italic; padding:8px 0; }
  #err { display:none; background:#3d1418; border:1px solid #f85149; color:#ffa198; padding:10px 14px; border-radius:8px; margin-bottom:16px; }
  footer { color:var(--muted); font-size:12px; text-align:center; padding:24px 0; }
  .searchwrap { margin-bottom:20px; }
  #docsearch { width:100%; background:var(--panel); color:var(--fg); border:1px solid var(--border); border-radius:8px; padding:11px 13px; font-size:14px; }
  #docsearch:focus { outline:none; border-color:var(--accent); }
  #docresults { display:none; }
  #docresults.open { display:block; margin-top:8px; background:var(--panel); border:1px solid var(--border); border-radius:8px; max-height:52vh; overflow:auto; }
  .dres-head { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.5px; padding:8px 12px; border-bottom:1px solid var(--border); }
  .dres-empty { color:var(--muted); padding:12px; font-style:italic; }
  .dres-row { padding:9px 12px; border-bottom:1px solid var(--border); cursor:pointer; }
  .dres-row:last-child { border-bottom:none; }
  .dres-row:hover { background:var(--panel2); }
  .dres-title { font-size:13px; font-weight:600; }
  .dres-sub { color:var(--muted); font-size:11px; margin-top:1px; }
  .dres-snip { color:#aab2bd; font-size:12px; margin-top:3px; max-height:34px; overflow:hidden; }
  /*OVERLAY_CSS*/
</style>
</head>
<body>
<header>
  <h1>Memex<span class="dot">·</span>dashboard</h1>
  <span class="home" id="home"></span>
  <span class="spacer"></span>
  <label class="toggle"><input type="checkbox" id="auto"> auto-refresh (30s)</label>
  <span class="meta" id="gen"></span>
  <a class="btn-link" href="/graph">◉ 3D graph</a>
  <button id="refresh">Refresh</button>
</header>
<main>
  <div class="searchwrap">
    <input id="docsearch" type="text" placeholder="🔍  search documents by keyword…" autocomplete="off" spellcheck="false">
    <div id="docresults"></div>
  </div>
  <div id="err"></div>
  <div class="kpis" id="kpis"></div>
  <div id="sections"></div>
  <footer>Memex read-only overview · served from <code id="hostf"></code></footer>
</main>
<!--OVERLAY_MARKUP-->
<script>
"use strict";
const $ = (id) => document.getElementById(id);
function el(tag, attrs, kids) {
  const n = document.createElement(tag);
  if (attrs) for (const k in attrs) {
    if (k === "class") n.className = attrs[k];
    else if (k === "style") n.style.cssText = attrs[k];
    else n.setAttribute(k, attrs[k]);
  }
  (kids || []).forEach((c) => n.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
  return n;
}
const num = (x) => (x == null ? "—" : Number(x).toLocaleString());

function bars(items, opts) {
  opts = opts || {};
  if (!items || !items.length) return el("div", { class: "empty" }, ["No data yet."]);
  const max = Math.max.apply(null, items.map((i) => i.count || 0)) || 1;
  const wrap = el("div", {}, []);
  items.forEach((i) => {
    const pct = Math.max(2, Math.round(((i.count || 0) / max) * 100));
    wrap.appendChild(el("div", { class: "bar" }, [
      el("span", { class: "name", title: String(i.key) }, [String(i.key)]),
      el("span", { class: "track" }, [el("span", { class: "fill", style: "width:" + pct + "%" }, [])]),
      el("span", { class: "n" }, [num(i.count)]),
    ]));
  });
  return wrap;
}
function card(title, body) {
  return el("div", { class: "card" }, [el("h3", {}, [title]), body]);
}
function section(title, count, kids) {
  const h = [el("span", {}, [title])];
  if (count != null) h.push(el("span", { class: "c" }, ["  " + count]));
  return el("section", {}, [el("h2", {}, h), ...kids]);
}
function kpi(v, l) {
  return el("div", { class: "kpi" }, [el("div", { class: "v" }, [num(v)]), el("div", { class: "l" }, [l])]);
}

function render(d) {
  $("home").textContent = d.memex_home || "";
  $("gen").textContent = d.generated_at ? "as of " + d.generated_at.replace("T", " ").replace("+00:00", " UTC") : "";
  $("hostf").textContent = location.host;
  const t = d.totals || {};

  const kpis = $("kpis");
  kpis.textContent = "";
  [["documents", "Indexed docs"], ["relations", "Relations"], ["communities", "Communities"],
   ["captures", "Brain captures"], ["agents", "Agents"], ["roles", "Roles"],
   ["code_nodes", "Code nodes"], ["code_edges", "Code edges"], ["stores", "Stores"],
   ["total_rows", "Total rows"]].forEach(([k, l]) => kpis.appendChild(kpi(t[k], l)));

  const S = $("sections");
  S.textContent = "";

  // Federated Index
  const ix = d.index;
  if (ix) {
    const cov = (ix.embedding_total)
      ? Math.round((ix.embedding_embedded || 0) / ix.embedding_total * 100) : 0;
    const grid = el("div", { class: "grid" }, [
      card("Documents by domain", bars(ix.by_domain)),
      card("Documents by source store", bars(ix.by_store)),
      card("Documents by table", bars(ix.by_table)),
      card("Top authors", bars(ix.by_author)),
      card("Relations by type", bars(ix.relations_by_type)),
      card("Embedding coverage", el("div", {}, [
        el("div", { class: "bar" }, [
          el("span", { class: "name" }, ["embedded"]),
          el("span", { class: "track" }, [el("span", { class: "fill", style: "width:" + Math.max(2, cov) + "%" }, [])]),
          el("span", { class: "n" }, [cov + "%"]),
        ]),
        el("div", { class: "muted", style: "font-size:12px;margin-top:6px" },
          [num(ix.embedding_embedded) + " of " + num(ix.embedding_total) + " documents carry a vector"]),
      ])),
    ]);
    const kids = [grid];
    if (ix.timeline && ix.timeline.length) {
      const max = Math.max.apply(null, ix.timeline.map((x) => x.count)) || 1;
      const spark = el("div", { class: "spark" },
        ix.timeline.slice(-40).map((x) => el("div", {
          class: "b", style: "height:" + Math.max(2, Math.round(x.count / max * 100)) + "%",
          title: x.date + ": " + x.count,
        }, [])));
      kids.push(card("Ingestion timeline (" + (ix.oldest || "").slice(0, 10) + " → " + (ix.newest || "").slice(0, 10) + ")", spark));
    }
    S.appendChild(section("Federated index", num(ix.documents_total) + " documents", kids));
  }

  // Knowledge communities
  if (ix && ix.top_reports && ix.top_reports.length) {
    const tb = el("table", {}, [el("tr", {}, [
      el("th", {}, ["Lvl"]), el("th", {}, ["Community report"]),
      el("th", { class: "num" }, ["Members"]), el("th", { class: "num" }, ["Rating"]),
    ])]);
    ix.top_reports.forEach((r) => tb.appendChild(el("tr", {}, [
      el("td", {}, [el("span", { class: "pill" }, ["L" + r.level])]),
      el("td", {}, [String(r.title || "—")]),
      el("td", { class: "num" }, [num(r.size)]),
      el("td", { class: "num" }, [r.rating == null ? "—" : Number(r.rating).toFixed(1)]),
    ])));
    S.appendChild(section("Knowledge communities", num(ix.communities_total) + " detected", [card("Top reports by rating", tb)]));
  }

  // Brain
  const b = d.brain;
  if (b) {
    S.appendChild(section("Brain (article store)", null, [el("div", { class: "grid" }, [
      card("Counts", el("div", {}, [
        bars([{ key: "captures", count: b.captures || 0 }, { key: "articles", count: b.articles || 0 }, { key: "syntheses", count: b.syntheses || 0 }]),
        b.captures_newest ? el("div", { class: "muted", style: "font-size:12px;margin-top:8px" },
          ["captures span " + (b.captures_oldest || "").slice(0, 10) + " → " + (b.captures_newest || "").slice(0, 10)]) : el("span", {}, []),
      ])),
    ])]));
  }

  // Code graph
  const cg = d.code_graph;
  if (cg && cg.repos_total) {
    const tb = el("table", {}, [el("tr", {}, [
      el("th", {}, ["Repo"]), el("th", { class: "num" }, ["Nodes"]),
      el("th", { class: "num" }, ["Edges"]), el("th", {}, ["State"]),
    ])]);
    (cg.per_repo || []).forEach((r) => tb.appendChild(el("tr", {}, [
      el("td", { class: "mono" }, [String(r.repo)]),
      el("td", { class: "num" }, [num(r.nodes)]),
      el("td", { class: "num" }, [num(r.edges)]),
      el("td", {}, [el("span", { class: "pill " + (r.needs_update ? "warn" : "good") }, [r.needs_update ? "stale" : "fresh"])]),
    ])));
    S.appendChild(section("Code-navigation graph", num(cg.repos_total) + " repos · " + num(cg.nodes_total) + " nodes · " + num(cg.edges_total) + " edges", [
      el("div", { class: "grid" }, [
        card("Repositories", tb),
        card("Edges by relation", bars(cg.edges_by_relation)),
        card("Nodes by file type", bars(cg.nodes_by_file_type)),
      ]),
    ]));
  }

  // Agents registry
  const a = d.agents;
  if (a) {
    S.appendChild(section("Agent registry", num(a.agents_total) + " agents · " + num(a.roles_total) + " roles", [
      card("Agents per role (populated)", bars(a.agents_per_role)),
    ]));
  }

  // Stores overview
  if (d.stores && d.stores.length) {
    const tb = el("table", {}, [el("tr", {}, [
      el("th", {}, ["Store"]), el("th", {}, ["Schema"]), el("th", { class: "num" }, ["Tables"]),
      el("th", { class: "num" }, ["Rows"]), el("th", { class: "num" }, ["Size"]), el("th", {}, ["Path"]),
    ])]);
    d.stores.forEach((s) => tb.appendChild(el("tr", {}, [
      el("td", {}, [String(s.name)]),
      el("td", {}, [el("span", { class: "pill" }, [String(s.schema_version || "—")])]),
      el("td", { class: "num" }, [num((s.tables || []).length)]),
      el("td", { class: "num" }, [num(s.total_rows)]),
      el("td", { class: "num" }, [s.size_human || "—"]),
      el("td", { class: "mono", title: s.path }, [s.path]),
    ])));
    const extra = [];
    if (d.embedding_model) {
      const m = d.embedding_model;
      extra.push(el("div", { class: "muted", style: "font-size:12px;margin-top:10px" },
        ["Embedding model: " + (m.provider || "?") + " / " + (m.model || "?") + " (dim " + (m.dim != null ? m.dim : "?") + ")"]));
    }
    S.appendChild(section("Stores", num(d.totals.stores) + " on this machine", [card("Per-store row counts", el("div", {}, [tb, ...extra]))]));
  }
}

let timer = null;
async function load() {
  try {
    const r = await fetch("/api/summary", { cache: "no-store" });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    $("err").style.display = "none";
    render(d);
  } catch (e) {
    const box = $("err");
    box.style.display = "block";
    box.textContent = "Could not load summary: " + e.message;
  }
}
$("refresh").addEventListener("click", load);
$("auto").addEventListener("change", (e) => {
  if (timer) { clearInterval(timer); timer = null; }
  if (e.target.checked) timer = setInterval(load, 30000);
});

// ---- document keyword search ----
const dsi = $("docsearch"), dres = $("docresults");
let dsTimer = null;
dsi.addEventListener("input", () => { clearTimeout(dsTimer); dsTimer = setTimeout(runSearch, 180); });
// Collapse the results when clicking anywhere outside the search box/list, or on
// Escape (when no document overlay is open); re-open on focus if a query remains.
document.addEventListener("click", (e) => { if (!e.target.closest(".searchwrap")) dres.classList.remove("open"); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !document.getElementById("docOverlay").classList.contains("open")) dres.classList.remove("open");
});
dsi.addEventListener("focus", () => { if (dsi.value.trim() && dres.children.length) dres.classList.add("open"); });
async function runSearch() {
  const q = dsi.value.trim();
  if (!q) { dres.textContent = ""; dres.classList.remove("open"); return; }
  try {
    const r = await fetch("/api/search?q=" + encodeURIComponent(q), { cache: "no-store" });
    renderResults(await r.json());
  } catch (e) { dres.classList.add("open"); dres.textContent = ""; dres.appendChild(el("div", { class: "dres-empty" }, ["search failed: " + e.message])); }
}
function renderResults(d) {
  if (d.query !== undefined && d.query !== dsi.value.trim()) return;  // stale response — input moved on
  dres.textContent = ""; dres.classList.add("open");
  if (d.error) { dres.appendChild(el("div", { class: "dres-empty" }, [d.error])); return; }
  if (!d.results || !d.results.length) { dres.appendChild(el("div", { class: "dres-empty" }, ["no matches for “" + d.query + "”"])); return; }
  dres.appendChild(el("div", { class: "dres-head" }, [d.count + (d.truncated ? "+" : "") + " result" + (d.count === 1 ? "" : "s")]));
  d.results.forEach((x) => {
    const row = el("div", { class: "dres-row" }, [
      el("div", { class: "dres-title" }, [x.title || x.id]),
      el("div", { class: "dres-sub" }, [(x.domain || "—") + " · " + (x.store || "")]),
    ]);
    if (x.snippet) row.appendChild(el("div", { class: "dres-snip" }, [x.snippet]));
    row.addEventListener("click", () => openDoc(x.id));
    dres.appendChild(row);
  });
}
/*OVERLAY_JS*/
// Deep links: ?q=<keyword> prefills + runs the search; ?doc=<index_id> opens a document.
const _params = new URLSearchParams(location.search);
if (_params.get("q")) { dsi.value = _params.get("q"); runSearch(); }
if (_params.get("doc")) openDoc(_params.get("doc"));
load();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# The 3D knowledge-graph viewer (/graph). Self-contained: a vanilla-JS force
# simulation in 3D rendered to a 2D canvas with perspective projection + camera
# orbit — no Three.js / WebGL / CDN, so it stays under the default-src 'none'
# CSP and ships no vendored blobs. Data via fetch('/api/graph').
# ---------------------------------------------------------------------------
GRAPH_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Memex — knowledge graph (3D)</title>
<style>
  :root { --bg:#0a0d12; --fg:#e6edf3; --muted:#8b949e; --accent:#58a6ff; --accent2:#bc8cff; --border:#2b3340; --panel:rgba(22,27,34,.82); }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; overflow:hidden; background:var(--bg); color:var(--fg);
    font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
  #c { position:fixed; inset:0; display:block; cursor:grab; touch-action:none; }
  #c.drag { cursor:grabbing; }
  .panel { position:fixed; background:var(--panel); backdrop-filter:blur(8px);
    border:1px solid var(--border); border-radius:10px; padding:10px 12px; }
  .top-left { top:14px; left:14px; }
  .top-right { top:14px; right:14px; display:flex; flex-direction:column; gap:8px; align-items:stretch; }
  .bottom-left { bottom:14px; left:14px; max-width:240px; max-height:46vh; overflow:auto; }
  .title { font-size:15px; font-weight:650; }
  .title .dim, .dim { color:var(--muted); font-weight:400; }
  .back { color:var(--accent); text-decoration:none; font-size:12px; }
  .back:hover { text-decoration:underline; }
  #stats { font-size:12px; margin-top:2px; }
  .top-right input[type=text], .top-right input:not([type]) { background:#0d1117; color:var(--fg);
    border:1px solid var(--border); border-radius:6px; padding:5px 8px; font-size:12px; width:180px; }
  .top-right label { display:flex; gap:6px; align-items:center; color:var(--muted); font-size:12px; cursor:pointer; }
  .top-right button { background:#1c2330; color:var(--fg); border:1px solid var(--border);
    border-radius:6px; padding:5px 8px; font-size:12px; cursor:pointer; }
  .top-right button:hover { border-color:var(--accent); }
  #legend .row { display:flex; align-items:center; gap:7px; margin:3px 0; font-size:12px; }
  #legend .sw { width:11px; height:11px; border-radius:3px; flex:0 0 auto; }
  #legend .name { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  #legend h4 { margin:0 0 6px; font-size:11px; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); }
  .tip { position:fixed; pointer-events:none; background:#000d; border:1px solid var(--border);
    border-radius:6px; padding:6px 9px; font-size:12px; max-width:300px; display:none; z-index:9; }
  .tip .l { font-weight:600; } .tip .m { color:var(--muted); font-size:11px; }
  .err { position:fixed; top:14px; left:50%; transform:translateX(-50%); background:#3d1418;
    border:1px solid #f85149; color:#ffa198; padding:10px 14px; border-radius:8px; display:none; }
  .loading { position:fixed; inset:0; display:flex; align-items:center; justify-content:center; color:var(--muted); }
  .hint { position:fixed; bottom:14px; right:14px; color:var(--muted); font-size:11px; opacity:.8; }
  /*OVERLAY_CSS*/
</style>
</head>
<body>
<canvas id="c"></canvas>
<div class="panel top-left">
  <a href="/" class="back">&larr; dashboard</a>
  <div class="title">Knowledge graph <span class="dim">&middot; 3D</span></div>
  <div id="stats" class="dim"></div>
</div>
<div class="panel top-right">
  <input id="search" type="text" placeholder="search nodes…" autocomplete="off" spellcheck="false">
  <div id="matchinfo" class="dim" style="font-size:11px;min-height:14px"></div>
  <label><input type="checkbox" id="spin" checked> auto-rotate</label>
  <label><input type="checkbox" id="labels"> node labels</label>
  <button id="reset">reset view</button>
</div>
<div class="panel bottom-left" id="legend"></div>
<div class="tip" id="tip"></div>
<div class="err" id="err"></div>
<div class="loading" id="loading">loading graph…</div>
<div class="hint">drag to orbit · scroll to zoom · click a node to open it</div>
<!--OVERLAY_MARKUP-->
<script>
"use strict";
const PALETTE = ["#58a6ff","#bc8cff","#3fb950","#d29922","#f0883e","#ff7b72","#39c5cf",
  "#db61a2","#a5d6ff","#ffab70","#7ee787","#e3b341"];
const GREY = "#5a6472";
const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
const tip = document.getElementById("tip");
let W = 0, H = 0, DPR = 1;
let nodes = [], links = [], byId = new Map(), adj = new Map();
let alpha = 1, settled = false;
let hovered = null, selected = null, matched = null;
const cam = { theta: 0.6, phi: 0.35, dist: 600, tx: 0, ty: 0, tz: 0 };
let radius = 200;

function colorFor(community) {
  if (!community) return GREY;
  let h = 0;
  for (let i = 0; i < community.length; i++) h = (h * 31 + community.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
function focal() { return Math.min(W, H) || 800; }

function resize() {
  DPR = Math.min(window.devicePixelRatio || 1, 2);
  W = window.innerWidth; H = window.innerHeight;
  canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR);
  canvas.style.width = W + "px"; canvas.style.height = H + "px";
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}
window.addEventListener("resize", resize);

function project(p) {
  const x = p.x - cam.tx, y = p.y - cam.ty, z = p.z - cam.tz;
  const ct = Math.cos(cam.theta), st = Math.sin(cam.theta);
  const x1 = x * ct + z * st;
  const z1 = -x * st + z * ct;
  const cp = Math.cos(cam.phi), sp = Math.sin(cam.phi);
  const y1 = y * cp - z1 * sp;
  const z2 = y * sp + z1 * cp;
  const zc = z2 + cam.dist;
  if (zc < 1) return null;
  const f = focal();
  return { sx: W / 2 + (x1 * f) / zc, sy: H / 2 - (y1 * f) / zc, depth: zc, scale: f / zc };
}

function step() {
  const n = nodes.length;
  const REP = 26000, SPRING = 0.015, REST = 42, CENTER = 0.018, DAMP = 0.84;
  for (let i = 0; i < n; i++) {
    const a = nodes[i];
    for (let j = i + 1; j < n; j++) {
      const b = nodes[j];
      let dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
      let d2 = dx * dx + dy * dy + dz * dz;
      if (d2 < 0.01) { dx = (Math.random() - 0.5); dy = (Math.random() - 0.5); dz = (Math.random() - 0.5); d2 = 0.5; }
      const f = (REP * alpha) / d2;
      const inv = 1 / Math.sqrt(d2);
      const fx = dx * inv * f, fy = dy * inv * f, fz = dz * inv * f;
      a.vx += fx; a.vy += fy; a.vz += fz;
      b.vx -= fx; b.vy -= fy; b.vz -= fz;
    }
  }
  for (const l of links) {
    const a = l.s, b = l.t;
    const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
    const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.01;
    const f = ((dist - REST) * SPRING * alpha) / dist;
    a.vx += dx * f; a.vy += dy * f; a.vz += dz * f;
    b.vx -= dx * f; b.vy -= dy * f; b.vz -= dz * f;
  }
  let maxr = 1;
  for (const a of nodes) {
    a.vx -= a.x * CENTER * alpha; a.vy -= a.y * CENTER * alpha; a.vz -= a.z * CENTER * alpha;
    a.vx *= DAMP; a.vy *= DAMP; a.vz *= DAMP;
    if (!a.fixed) { a.x += a.vx; a.y += a.vy; a.z += a.vz; }
    const r = Math.hypot(a.x, a.y, a.z); if (r > maxr) maxr = r;
  }
  radius = maxr;
  alpha *= 0.985;
  if (alpha < 0.004) { alpha = 0; settled = true; }
}

function fit() {
  cam.dist = Math.max(radius * 2.5, 60);
  cam.tx = cam.ty = cam.tz = 0;
}

function draw() {
  ctx.clearRect(0, 0, W, H);
  for (const a of nodes) { const pr = project(a); a._p = pr; }
  // links
  ctx.lineWidth = 1;
  for (const l of links) {
    const pa = l.s._p, pb = l.t._p;
    if (!pa || !pb) continue;
    const hot = selected ? (l.s === selected || l.t === selected)
              : hovered ? (l.s === hovered || l.t === hovered) : false;
    const depth = (pa.depth + pb.depth) / 2;
    let al = Math.max(0.05, Math.min(0.5, 220 / depth));
    if (selected || hovered) al = hot ? 0.85 : al * 0.25;
    ctx.strokeStyle = hot ? "rgba(188,140,255," + al + ")" : "rgba(140,150,165," + al + ")";
    ctx.beginPath(); ctx.moveTo(pa.sx, pa.sy); ctx.lineTo(pb.sx, pb.sy); ctx.stroke();
  }
  // nodes back-to-front
  const order = nodes.filter(a => a._p).sort((u, v) => v._p.depth - u._p.depth);
  const labelOn = document.getElementById("labels").checked;
  const selAdj = selected ? adj.get(selected.id) : null;  // hoist once per frame (avoid per-node Map.get)
  const hovAdj = hovered ? adj.get(hovered.id) : null;
  for (const a of order) {
    const p = a._p;
    const r = Math.max(1.5, Math.min(40, (3 + 2.5 * Math.log2(a.deg + 1)) * p.scale));
    let dim = 1;
    if (selected) dim = (a === selected || selAdj.has(a.id)) ? 1 : 0.18;
    else if (hovered) dim = (a === hovered || hovAdj.has(a.id)) ? 1 : 0.28;
    if (matched && !matched.has(a.id)) dim = Math.min(dim, 0.12);
    const da = Math.max(0.25, Math.min(1, 260 / p.depth)) * dim;
    ctx.globalAlpha = da;
    ctx.beginPath(); ctx.arc(p.sx, p.sy, r, 0, 6.2832);
    ctx.fillStyle = a.color; ctx.fill();
    ctx.globalAlpha = Math.min(1, da + 0.2);
    ctx.lineWidth = (a === hovered || a === selected) ? 2 : 1;
    ctx.strokeStyle = (a === hovered || a === selected) ? "#fff" : "rgba(0,0,0,.55)";
    ctx.stroke();
    a._r = r;
  }
  ctx.globalAlpha = 1;
  // labels
  ctx.font = "12px -apple-system,Segoe UI,Roboto,sans-serif";
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  const labelSet = new Set();
  if (hovered) { labelSet.add(hovered); for (const id of adj.get(hovered.id)) labelSet.add(byId.get(id)); }
  if (selected) { labelSet.add(selected); for (const id of adj.get(selected.id)) labelSet.add(byId.get(id)); }
  if (labelOn) {
    const small = nodes.length <= 120;  // small graphs: genuinely label every node
    let budget = small ? nodes.length : 70;
    for (const a of order) { if (budget <= 0) break; if (a._p && (small || a._p.scale > 0.5)) { labelSet.add(a); budget--; } }
  }
  for (const a of labelSet) {
    if (!a._p) continue;
    const x = a._p.sx + (a._r || 4) + 4, y = a._p.sy;
    ctx.fillStyle = "rgba(0,0,0,.65)";
    const w = ctx.measureText(a.label).width;
    ctx.fillRect(x - 2, y - 8, w + 4, 16);
    ctx.fillStyle = (a === hovered || a === selected) ? "#fff" : "#c9d1d9";
    ctx.fillText(a.label, x, y);
  }
}

let raf = 0;
function pairCount() { const n = nodes.length; return n > 1 ? (n * (n - 1)) / 2 : 1; }
// Bound per-frame physics by a fixed pair-op budget (each step() is O(n²/2)) so
// settling stays ~60fps-safe regardless of node count, not a fixed node threshold.
function stepsPerFrame() { return Math.max(1, Math.min(4, Math.floor(300000 / pairCount()))); }
function loop() {
  if (!settled) { const s = stepsPerFrame(); for (let k = 0; k < s; k++) step(); }
  if (document.getElementById("spin").checked && !dragging && !hovered) cam.theta += 0.0023;
  if (selected) { cam.tx = selected.x; cam.ty = selected.y; cam.tz = selected.z; }  // keep focus centered as the node drifts
  // Constant inner floor (not radius*k): orphan nodes inflate `radius`, so a
  // radius-tied floor would block zooming into the connected cluster.
  cam.dist = Math.max(20, Math.min(radius * 12, cam.dist));
  draw();
  raf = requestAnimationFrame(loop);
}

// ---- interaction ----
let dragging = false, dragStart = null, moved = false;
const pointers = new Map();
let pinchDist = 0;
function twoPointerDist() {
  const p = [...pointers.values()];
  return p.length < 2 ? 0 : Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y);
}
canvas.addEventListener("pointerdown", (e) => {
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  canvas.setPointerCapture(e.pointerId);
  if (pointers.size === 1) {
    dragging = true; moved = false; dragStart = { x: e.clientX, y: e.clientY };
    canvas.classList.add("drag");
  } else if (pointers.size === 2) { dragging = false; pinchDist = twoPointerDist(); }
});
canvas.addEventListener("pointermove", (e) => {
  if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pointers.size >= 2) {  // two-finger pinch-to-zoom
    const d = twoPointerDist();
    if (pinchDist > 0 && d > 0) cam.dist *= pinchDist / d;
    pinchDist = d;
    return;
  }
  if (dragging) {
    const dx = e.clientX - dragStart.x, dy = e.clientY - dragStart.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
    cam.theta += dx * 0.006;
    cam.phi = Math.max(-1.45, Math.min(1.45, cam.phi + dy * 0.006));
    dragStart = { x: e.clientX, y: e.clientY };
    return;
  }
  const hit = pick(e.clientX, e.clientY);
  hovered = hit;
  if (hit) {
    tip.style.display = "block";
    tip.style.left = Math.min(e.clientX + 14, W - 280) + "px";
    tip.style.top = (e.clientY + 14) + "px";
    tip.innerHTML = "";
    const l = document.createElement("div"); l.className = "l"; l.textContent = hit.label;
    const m = document.createElement("div"); m.className = "m";
    m.textContent = (hit.domain || "—") + " · degree " + hit.deg + (hit.community ? " · " + hit.community : "");
    tip.appendChild(l); tip.appendChild(m);
    canvas.style.cursor = "pointer";
  } else { tip.style.display = "none"; canvas.style.cursor = "grab"; }
});
function endPointer(e, canceled) {
  const wasDragging = dragging, didMove = moved;
  pointers.delete(e.pointerId);
  if (pointers.size < 2) pinchDist = 0;
  if (pointers.size === 1) {
    // Dropped from a two-finger pinch back to one finger — resume single-pointer
    // orbit from the remaining finger (moved=true so it isn't mistaken for a tap).
    const p = [...pointers.values()][0];
    dragging = true; moved = true; dragStart = { x: p.x, y: p.y };
    return;
  }
  if (pointers.size === 0) {
    // Only a genuine pointerup (not a browser-canceled gesture) is a tap-select.
    if (!canceled && wasDragging && !didMove) {
      const hit = pick(e.clientX, e.clientY);
      if (hit) {
        selected = hit; cam.tx = hit.x; cam.ty = hit.y; cam.tz = hit.z;
        cam.dist = Math.min(cam.dist, Math.max(60, radius * 0.6));  // pull camera in toward the focused node
        openDoc(hit.id);  // show the document's content in the overlay
      } else selected = null;
    }
    dragging = false; canvas.classList.remove("drag");
  }
}
canvas.addEventListener("pointerup", (e) => endPointer(e, false));
canvas.addEventListener("pointercancel", (e) => endPointer(e, true));
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  cam.dist *= (1 + Math.sign(e.deltaY) * 0.12);
}, { passive: false });

function pick(px, py) {
  let best = null, bd = 18 * 18;
  for (const a of nodes) {
    if (!a._p) continue;
    const dx = a._p.sx - px, dy = a._p.sy - py;
    const rr = Math.max(a._r || 3, 6);
    const d2 = dx * dx + dy * dy;
    if (d2 < Math.max(bd, rr * rr) && d2 < (best ? bd : 1e9)) { best = a; bd = d2; }
  }
  return best;
}

document.getElementById("reset").addEventListener("click", () => {
  cam.theta = 0.6; cam.phi = 0.35; selected = null; matched = null;
  document.getElementById("search").value = "";
  document.getElementById("matchinfo").textContent = "";
  fit(); alpha = Math.max(alpha, 0.3); settled = false;
});
document.getElementById("search").addEventListener("input", (e) => {
  const q = e.target.value.trim().toLowerCase();
  const info = document.getElementById("matchinfo");
  if (!q) { matched = null; info.textContent = ""; return; }
  const hits = new Set();
  for (const a of nodes) if (a.label.toLowerCase().includes(q)) hits.add(a.id);
  if (hits.size) { matched = hits; info.textContent = hits.size + " match" + (hits.size === 1 ? "" : "es"); }
  else { matched = null; info.textContent = "no matches"; }  // don't dim everything on zero matches
});

function showErr(msg) { const el = document.getElementById("err"); el.style.display = "block"; el.textContent = msg; }

function buildLegend() {
  const counts = new Map();
  for (const a of nodes) { const k = a.community || "(none)"; counts.set(k, (counts.get(k) || 0) + 1); }
  const top = [...counts.entries()].sort((u, v) => v[1] - u[1]).slice(0, 12);
  const el = document.getElementById("legend");
  el.innerHTML = "";
  const h = document.createElement("h4"); h.textContent = "Communities"; el.appendChild(h);
  for (const [k, c] of top) {
    const row = document.createElement("div"); row.className = "row";
    const sw = document.createElement("span"); sw.className = "sw";
    sw.style.background = k === "(none)" ? GREY : colorFor(k);
    const nm = document.createElement("span"); nm.className = "name"; nm.textContent = k + " (" + c + ")";
    row.appendChild(sw); row.appendChild(nm); el.appendChild(row);
  }
}

async function init() {
  resize();
  let data;
  try {
    const r = await fetch("/api/graph", { cache: "no-store" });
    data = await r.json();
    if (data.error) throw new Error(data.error);
    if (!Array.isArray(data.nodes) || !Array.isArray(data.links)) throw new Error("malformed graph payload");
  } catch (e) { document.getElementById("loading").style.display = "none"; showErr("Could not load graph: " + e.message); return; }
  document.getElementById("loading").style.display = "none";
  nodes = data.nodes.map((d) => ({
    id: d.id, label: d.label || d.id, domain: d.domain, community: d.community,
    color: colorFor(d.community), deg: 0,
    x: (Math.random() - 0.5) * 300, y: (Math.random() - 0.5) * 300, z: (Math.random() - 0.5) * 300,
    vx: 0, vy: 0, vz: 0,
  }));
  byId = new Map(nodes.map((n) => [n.id, n]));
  adj = new Map(nodes.map((n) => [n.id, new Set()]));
  links = [];
  for (const l of data.links) {
    const s = byId.get(l.source), t = byId.get(l.target);
    if (!s || !t) continue;
    links.push({ s, t, type: l.type });
    s.deg++; t.deg++; adj.get(s.id).add(t.id); adj.get(t.id).add(s.id);
  }
  const stats = document.getElementById("stats");
  stats.textContent = nodes.length + " nodes · " + links.length + " links" + (data.truncated ? " (truncated)" : "");
  if (!nodes.length) { showErr("No documents in the index yet — ingest or capture something first."); return; }
  buildLegend();
  // Pre-layout burst bounded by a fixed PAIR-OP budget (each step() is O(n²/2)),
  // so the synchronous on-load cost stays ~3M pair-ops regardless of node count.
  // A node-count floor would reintroduce a multi-second freeze near the cap.
  const burst = Math.max(8, Math.min(300, Math.round(3.0e6 / pairCount())));
  for (let k = 0; k < burst && !settled; k++) step();
  fit();
  loop();
}
/*OVERLAY_JS*/
init();
</script>
</body>
</html>
"""


# Inject the shared document-content overlay (CSS / markup / JS) into both pages
# at their placeholders — defined once above, used by the dashboard search list
# and the 3D graph's click-to-open.
def _inject_overlay(html: str) -> str:
    return (
        html.replace("/*OVERLAY_CSS*/", _OVERLAY_CSS)
        .replace("<!--OVERLAY_MARKUP-->", _OVERLAY_MARKUP)
        .replace("/*OVERLAY_JS*/", _OVERLAY_JS)
    )


INDEX_HTML = _inject_overlay(INDEX_HTML)
GRAPH_HTML = _inject_overlay(GRAPH_HTML)


if __name__ == "__main__":
    sys.exit(main())
