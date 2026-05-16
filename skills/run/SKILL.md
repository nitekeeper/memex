---
description: Use to invoke any Memex v2.0 operation. Routes user-facing intents (ingest, ask, capture, lint, synthesize) and agent-facing CRUD primitives to the right internal procedure. The only Claude-Code-visible Memex skill — internal procedures (24 total) are read on demand to stay under the 1% skill-description budget.
---

Memex v2 is a personal knowledge runtime and shared memory plane for the agent fleet. This skill is the public entry point — it maps natural-language intent (for users) or agent-named operations (for AI consumers) to the right internal procedure under `internal/<category>/<name>/SKILL.md`.

When this skill references `internal/<category>/<name>/SKILL.md` below, the agent should: (1) Read that file via the Read tool, (2) follow the procedure inline.

See `docs/specs/2026-05-16-memex-v2-redesign-design.md` for the full v2.0 architecture.

## v2 Brain user-facing intent routing

Brain operations are the daily-use second-brain verbs. The user expresses one of these intents in natural language — there is no `memex:brain:*` top-level skill because the 1% budget would be exceeded; instead, this skill reads the matching procedure and follows it.

| User intent | Internal procedure |
|---|---|
| Ingest an article / save a URL / capture a clipped page | `internal/brain/ingest/SKILL.md` |
| Ask a question / search / recall | `internal/brain/ask/SKILL.md` |
| Capture a note / jot a thought / log an observation | `internal/brain/capture/SKILL.md` |
| Run a Brain health check / lint Brain / audit my knowledge | `internal/brain/lint/SKILL.md` |
| Synthesize across documents / find the through-line / summarize this topic | `internal/brain/synthesize/SKILL.md` |

## v2 Core CRUD routing (agent-facing)

Memex Core is the CRUD substrate that agents — not the human user — invoke directly. These 10 procedures live at `internal/core/<name>/SKILL.md` and are reachable only via this routing table.

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

The Python implementations live under `scripts/` (`db.py`, `roles.py`, `agents/`, `registry.py`, `stores.py`, `install.py`). Each SKILL.md is a short documentation wrapper; the agent reads it for the API contract, then calls the implementation.

## v2 Index, Steward, and DBA routing (agent-facing)

Memex maintains a federated Index (`~/.memex/index.db`) plus five internal agents: Librarian, Reference Librarian, Archivist, DBA, Data Steward. Their procedures live at `internal/<category>/<name>/SKILL.md`. Like Core, these are agent-only — the human typically reaches them through Brain rather than directly.

| Agent intent | Internal procedure |
|---|---|
| Submit a document for centralized indexing (mandatory write path; archives raw, classifies, embeds, persists) | `internal/index/write/SKILL.md` |
| Ask a natural-language question against the federated Index; returns ranked, citation-ready results | `internal/index/search/SKILL.md` |
| Archive a raw payload to `~/.memex/raw/` without indexing (rare; usually called internally by index:write) | `internal/index/archive/SKILL.md` |
| Run a full integrity audit across every store + the Index; write a structured report | `internal/steward/audit/SKILL.md` |
| Audit a single registered store (reverse orphans, schema drift) | `internal/steward/audit-store/SKILL.md` |
| Authorized resolution of a flagged orphan (delete-index / reindex / note) | `internal/steward/reconcile-orphan/SKILL.md` |
| Run a WAL checkpoint on a registered store | `internal/dba/checkpoint/SKILL.md` |
| Run `PRAGMA integrity_check` on a registered store | `internal/dba/integrity-check/SKILL.md` |
| Run `VACUUM` on a registered store (maintenance) | `internal/dba/vacuum/SKILL.md` |
| Backfill embeddings (encode rows where `embedding IS NULL`) | `internal/embed/backfill/SKILL.md` |
| Re-embed all rows after a provider/model change | `internal/embed/reembed/SKILL.md` |

The Librarian and Reference Librarian are themselves invoked as LLM subagents inside `index:write` and `index:search` respectively; they read their system prompts from `agents.db.agents.profile`. Archivist, DBA, and Data Steward are deterministic Python modules.

## Authority and override

User instructions override this skill's defaults at all times. If the user provides a direct instruction — "just answer," "skip routing," or any unambiguous bypass directive — comply immediately without re-asking. This skill defines default behavior; it does not constrain the user's authority to change it.

Priority order when instructions conflict:

1. **User's explicit instructions — highest priority.**
2. **Memex methodology (this skill).**
3. **Default system prompt.**
