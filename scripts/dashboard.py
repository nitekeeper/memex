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
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

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
# HTTP layer — loopback-only, three fixed routes, no filesystem serving.
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

    def do_GET(self) -> None:  # http.server dispatch hook
        route = urlparse(self.path).path
        if route in ("/", "/index.html"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/api/summary":
            try:
                payload = json.dumps(build_summary(), ensure_ascii=False, default=str)
                self._send(200, payload.encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:  # surface a clean JSON error, never a stack trace page
                body = json.dumps({"error": str(exc)}).encode("utf-8")
                self._send(500, body, "application/json; charset=utf-8")
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
</style>
</head>
<body>
<header>
  <h1>Memex<span class="dot">·</span>dashboard</h1>
  <span class="home" id="home"></span>
  <span class="spacer"></span>
  <label class="toggle"><input type="checkbox" id="auto"> auto-refresh (30s)</label>
  <span class="meta" id="gen"></span>
  <button id="refresh">Refresh</button>
</header>
<main>
  <div id="err"></div>
  <div class="kpis" id="kpis"></div>
  <div id="sections"></div>
  <footer>Memex read-only overview · served from <code id="hostf"></code></footer>
</main>
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
load();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
