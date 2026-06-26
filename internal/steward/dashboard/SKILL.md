---
name: memex:steward:dashboard
description: Launch a local, read-only web dashboard summarizing everything stored in Memex — per-store row counts, the federated index (documents by domain/store/author, relations, embedding coverage, ingestion timeline), knowledge communities, Brain captures, the code-navigation graph, and the agent registry — plus keyword document search, a click-to-read content overlay, and an interactive 3D knowledge-graph view (Obsidian-style) at /graph. Stdlib HTTP server, binds 127.0.0.1, never writes to any store.
---

# memex:steward:dashboard

A read-only observability surface the Data Steward exposes: it opens every
registered store (plus the fixed-path `code_graph.db`) **read-only**, aggregates
a cross-store summary, and serves a single self-contained HTML page over a
loopback-only stdlib HTTP server. It writes to nothing, so it is **not** a
Librarian write-path bypass (spec §6 / M3 govern document *writes*; this is pure
read-side reporting).

## When to use

- The user asks to *see / visualize / get an overview / dashboard of* what is
  stored in Memex.
- A quick health glance before/after a large ingest, audit, or release.
- For a deep integrity audit (orphans, broken relations, schema drift) use
  `memex:steward:audit` instead — this skill is a friendly overview, not an
  integrity checker.

## Inputs

- `--port` — bind port (default `8765`; auto-increments if busy, up to +20).
- `--host` — bind host (default `127.0.0.1`). Non-loopback hosts require
  `--allow-non-local` (the dashboard exposes your Memex contents).
- `--no-open` — do not auto-open a browser (use in headless/SSH sessions).
- `--once` — print the summary JSON to stdout and exit (no server). Use this for
  scripting, smoke checks, or when a browser is unavailable.

## Invocation

The implementation is `scripts/dashboard.py` (stdlib only — `http.server` +
`sqlite3` + `json`; no third-party deps). Run it as a module with the plugin
root on `PYTHONPATH`. `<PLUGIN_ROOT>` is the path resolved in `memex:run` Step 0.2.

**Serve the dashboard** (long-running — start it in the background and report the
URL to the user; it prints `Memex dashboard → http://127.0.0.1:<port>/`):

```bash
PYTHONPATH="<PLUGIN_ROOT>" python3 -m scripts.dashboard --no-open --port 8765
```

Then tell the user to open the printed `http://127.0.0.1:<port>/` URL. Stop it
with Ctrl-C (or kill the background job).

**One-shot JSON snapshot** (no server — for a quick textual summary):

```bash
PYTHONPATH="<PLUGIN_ROOT>" python3 -m scripts.dashboard --once
```

## Routes served

| Route | Returns |
|---|---|
| `GET /` | the self-contained dashboard page (keyword **search box** + a **◉ 3D graph** link). Deep links: `?q=<keyword>` prefills+runs the search, `?doc=<index_id>` opens a document. |
| `GET /graph` | an interactive **3D knowledge-graph** viewer (Obsidian-style) — documents as nodes, relations as edges, colored by community; orbit / zoom / search / **click a node to open its content**. Dependency-free vanilla JS + canvas (no Three.js/CDN, under the same CSP). |
| `GET /api/summary` | the cross-store summary as JSON (recomputed live each request) |
| `GET /api/graph` | the index knowledge graph as JSON `{nodes, links, truncated}` (read-only; dangling/self edges dropped; capped at 900 nodes) |
| `GET /api/search?q=` | keyword search over the federated index (FTS5, LIKE fallback) → `{results, count, truncated, query}` |
| `GET /api/doc?id=` | one document's full record + best-effort content fetched from its source store by `index_id` → `{title, domain, store, content, content_source, content_truncated, …}` |
| `GET /healthz` | `{"ok":true}` liveness probe |

Both the dashboard search list and a 3D-graph node click open a shared, read-only
**content overlay** that renders the document body via `textContent` only (no
HTML injection from stored/ingested text).

## Safety contract

- **Read-only.** Every store is opened with SQLite `mode=ro`; no write path.
- **Loopback by default.** Binds `127.0.0.1`; refuses a non-local bind without
  `--allow-non-local`.
- **No filesystem serving.** Only the three fixed routes above respond; there is
  no static-file handler, so no path-traversal surface.
- **No untrusted templating.** The page carries zero server-side interpolation;
  all data crosses as JSON and is rendered client-side via `textContent`, so a
  stored document title containing markup cannot become script (CSP also set).
- **Degrades gracefully.** A missing store/table/column renders as empty rather
  than erroring — a freshly bootstrapped install (no `code_graph.db`) is fine.
