---
description: Use to invoke any Memex v2.0 operation. Routes user-facing intents (ingest, ask, capture, lint, synthesize, dashboard) and agent-facing CRUD primitives to the right internal procedure.
---

Memex v2 maps intent (user natural-language or agent-named) to internal procedures under `internal/<category>/<name>/SKILL.md`; full v2.0 architecture is in the per-layer acceptance docs (`docs/CORE.md`, `docs/INDEX.md`, `docs/BRAIN.md`, `docs/PACKAGING.md`) or via `memex:run ask`.

When this skill references `internal/<category>/<name>/SKILL.md` below, the agent should: (1) Read that file via the Read tool, (2) follow the procedure inline.

## Step 0 — Preflight

Step 0 runs BEFORE intent routing on every top-level `memex:run` invocation. It verifies (0.1) a usable Python interpreter, then (0.2) that `~/.memex/` is bootstrapped. Cold-path detail (install instructions, plugin-root discovery, the bootstrap prompt) lives in `skills/run/STEP0.md`.

### Step 0.1 — Verify Python ≥ 3.10 is available

Run via Bash, trying interpreters in order:

```bash
for cmd in python3 python "py -3"; do
  $cmd -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)' 2>/dev/null && {
    echo "PYTHON=$cmd"; exit 0
  }
done
exit 1
```

- **Exit 0** → capture `PYTHON=<token>`. Substitute the captured token unquoted wherever `python3` appears in Step 0.2 (e.g., `PYTHON=py -3` becomes `py -3 -m scripts.install` — `py` is the executable, `-3` is its arg).
- **Exit 1** → no interpreter ≥ 3.10. Read `skills/run/STEP0.md` and follow its "## Python install" section to detect the platform, show the matching install block, and output the required `Memex requires Python 3.10 or newer.` message. A missing Python always ends the turn — no routing, no fallback.

### Step 0.2 — Verify Memex is initialized

Resolve `<RESOLVED_HOME>`: `$MEMEX_HOME` if set, else `~/.memex/`. (The Python layer validates this is non-symlink and under `$HOME` unless `MEMEX_HOME_ALLOW_UNUSUAL=1` is set.)

Resolve `<RESOLVED_PLUGIN_ROOT>` by first **reading `~/.memex/config.json`**: if it contains a valid `plugin_root` field whose target exists AND whose `scripts/install.py` is a regular file AND whose `.claude-plugin/plugin.json` contains `"name": "memex"` → use it (subsequent invocations read directly from this file and skip discovery). Otherwise read `skills/run/STEP0.md` and follow its "## Plugin-root resolution" section ($PWD probe → $PATH probe → ask the user, then write the resolved path back to config.json). Per that section, successful discovery + write-back PROCEEDS to the five-path checks below; only a re-ask-once-then-STOP ends the turn.

Then check that all five paths exist:
- `<RESOLVED_HOME>/`
- `<RESOLVED_HOME>/registry.json`
- `<RESOLVED_HOME>/agents.db`
- `<RESOLVED_HOME>/index.db`
- `<RESOLVED_HOME>/article.db`

If all exist → proceed to routing.

If ANY path is missing, read `skills/run/STEP0.md` and follow its "## Bootstrap prompt" section to build the missing list, check for a v1 install, prompt for consent (`y`/`n`), and run the installer. Branch semantics from that section: on `n` (decline) or on install failure, end the turn — no routing, no summary; but on `y` with `EXIT=0` and all five paths now present, proceed to routing.

## v2 Brain user-facing intent routing

Brain operations are the daily-use second-brain verbs; the user expresses one in natural language and this skill reads the matching procedure and follows it.

| User intent | Internal procedure |
|---|---|
| Ingest an article / save a URL / capture a clipped page | `internal/brain/ingest/SKILL.md` |
| Ask a question / search / recall | `internal/brain/ask/SKILL.md` |
| Capture a note / jot a thought / log an observation | `internal/brain/capture/SKILL.md` |
| Run a Brain health check / lint Brain / audit my knowledge | `internal/brain/lint/SKILL.md` |
| Synthesize across documents / find the through-line / summarize this topic | `internal/brain/synthesize/SKILL.md` |
| Ask a thematic / corpus-wide question, or recall about an entity and its neighborhood (GraphRAG global/local) | `internal/brain/ask/SKILL.md` |
| Summarize a detected knowledge community / write a community report | `internal/brain/community-report/SKILL.md` |
| Rebuild the knowledge graph + communities + reports (GraphRAG maintenance) | `internal/brain/graph-rebuild/SKILL.md` |

## v2 Dashboard / overview (user-facing)

A read-only, at-a-glance summary of everything Memex is holding, served as a
local web page. This is observability, not an integrity audit — for orphan /
schema-drift detection route to `internal/steward/audit/SKILL.md` instead.

| User intent | Internal procedure |
|---|---|
| Show a dashboard / overview / summary of what's stored in Memex; visualize my knowledge base; launch the Memex dashboard | `internal/steward/dashboard/SKILL.md` |

## v2 Core CRUD routing (agent-facing)

Memex Core is the agent-facing CRUD substrate; these 10 procedures live at `internal/core/<name>/SKILL.md` and are reachable only via this routing table.

| Agent intent | Internal procedure |
|---|---|
| Provision a new SQLite store from a directory of `.sql` migrations | `internal/core/create-store/SKILL.md` |
| Apply additional migrations to an existing registered store | `internal/core/migrate/SKILL.md` |
| Read rows from a registered store (SELECT) | `internal/core/query/SKILL.md` |
| Insert a row into a non-document table | `internal/core/insert/SKILL.md` |
| Update a row by integer `id` PK | `internal/core/update/SKILL.md` |
| Delete a row by integer `id` PK | `internal/core/delete/SKILL.md` |
| Enumerate every registered store | `internal/core/list-stores/SKILL.md` |
| Register a new role in `agents.db.roles` | `internal/core/register-role/SKILL.md` |
| Register a new agent in `agents.db.agents` | `internal/core/register-agent/SKILL.md` |
| Fetch an agent's full profile by id | `internal/core/get-agent/SKILL.md` |

## v2 Index, Steward, and DBA routing (agent-facing)

Memex maintains a federated Index (`~/.memex/index.db`) plus five internal agents: Librarian, Reference Librarian, Archivist, DBA, Data Steward. Their procedures live at `internal/<category>/<name>/SKILL.md`. Like Core, these are agent-only — the human typically reaches them through Brain rather than directly.

| Agent intent | Internal procedure |
|---|---|
| Submit a document for centralized indexing (mandatory write path; archives raw, classifies, embeds, persists) | `internal/index/write/SKILL.md` |
| Ask a natural-language question against the federated Index; returns ranked, citation-ready results | `internal/index/search/SKILL.md` |
| Archive a raw payload to `~/.memex/raw/` without indexing (rare; usually called internally by index:write) | `internal/index/archive/SKILL.md` |
| Run a full integrity audit across every store + the Index; write a structured report | `internal/steward/audit/SKILL.md` |
| Audit a single registered store (reverse orphans, schema drift) | `internal/steward/audit-store/SKILL.md` |
| Authorized resolution of a flagged orphan (delete-index / repair / reindex / note) | `internal/steward/reconcile-orphan/SKILL.md` |
| Run a WAL checkpoint on a registered store | `internal/dba/checkpoint/SKILL.md` |
| Run `PRAGMA integrity_check` on a registered store | `internal/dba/integrity-check/SKILL.md` |
| Run `VACUUM` on a registered store (maintenance) | `internal/dba/vacuum/SKILL.md` |
| Backfill embeddings (encode rows where `embedding IS NULL`) | `internal/embed/backfill/SKILL.md` |
| Re-embed all rows after a provider/model change | `internal/embed/reembed/SKILL.md` |

## v2 Code-navigation graph routing (agent-facing)

Memex stores + serves a code-navigation graph in a SEPARATE store (`~/.memex/code_graph.db`), keyed by repo identity (`owner/repo`); the extractor is external (consumers run `graphify` and hand memex the `graph.json`).

| Agent intent | Internal procedure |
|---|---|
| Ingest a graphify `graph.json` for a repo into the code-navigation graph store (idempotent; per-file fragment upsert) | `internal/codegraph/ingest/SKILL.md` |
| Query the code-navigation graph: where_is / callers / dependencies / neighbors / module_map (bounded, locations not bodies) | `internal/codegraph/query/SKILL.md` |

## Authority and override

User instructions override this skill's defaults at all times. If the user provides a direct instruction — "just answer," "skip routing," or any unambiguous bypass directive — comply immediately without re-asking. This skill defines default behavior; it does not constrain the user's authority to change it.

Priority order when instructions conflict:

1. **User's explicit instructions — highest priority.**
2. **Memex methodology (this skill).**
3. **Default system prompt.**
