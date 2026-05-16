---
description: Use when starting any session in a Memex-aware project — runs the session-start self-improvement queue pass and routes natural-language intent (capture, ask, review, sync, upgrade) to the right internal procedure.
---

Memex is a project-wiki and knowledge-management plugin. This skill is the public entry point — it (1) runs the session-start self-improvement pass and (2) maps user intent to the right internal procedure (read via the Read tool, follow inline).

## Internal procedures

Memex's domain operations live as plain markdown procedure files at `internal/<name>/SKILL.md`. These are NOT Claude Code slash commands — they are reachable only via the Read tool. Whenever this skill references `internal/<name>/SKILL.md` below, the agent should: (1) Read that file, (2) follow the procedure inline. The 9 internal procedures are `ask`, `capture`, `capture-lesson`, `propose-wiki-entry`, `review-lessons`, `review-wiki`, `self-improve`, `sync`, `upgrade`.

## Session-start ritual

At the start of every session, before responding to any user message, run this queue-processing pass:

1. **Review lessons (solo).** Read `internal/review-lessons/SKILL.md` and follow it. Scan `lessons/feedback/` then `lessons/inbox/` for `status: draft` lessons.
   - **Promote** if the lesson is factual, self-contained, and has a concrete how-to-apply.
   - **Defer** (leave as draft) if the lesson touches goals, priorities, design philosophy, or contradicts an existing approved wiki entry.
   - **Discard** if it duplicates something already in the wiki or is purely session-local.
   Apply actions directly — no approval gate. If either `lessons/feedback/` or `lessons/inbox/` does not exist, treat it as empty and proceed. A lesson file with no `status` field is treated as `draft`.

2. **Propose wiki entries (solo).** Read `internal/propose-wiki-entry/SKILL.md` and follow it. Convert all newly promoted lessons into draft wiki entries in `.ai/wiki/`. Apply directly — no approval gate. If a slug already exists in `.ai/wiki/`, skip that entry and note the conflict in the summary — do not overwrite.

3. **Sync.** Read `internal/sync/SKILL.md` and follow it. Run `python scripts/sync.py .ai/` from the Memex product root to surface stale wiki entries. If the script fails, set `Stale entries flagged: 0` in the summary and add a `Sync error: <error message>` line immediately below. Proceed to step 4 — do not abort.

4. **Show summary** using this exact format:

   ```
   Session-start self-improvement pass — YYYY-MM-DD
     Lessons reviewed: N
       Promoted: X
       Deferred (needs collaborative review): Y
       Discarded: Z
     Wiki entries proposed: M
     Wiki entry conflicts skipped: C
       - <slug> (already exists)
     Stale entries flagged: K
       - <title> (.ai/wiki/<slug>.md)
     Sync error: <error message>    ← sibling field, not a sub-item; only shown when sync fails; omit when sync succeeds
   ```

   If `K` is 0, show `Stale entries flagged: 0` and omit the bullet list.
   If `C` is 0, show `Wiki entry conflicts skipped: 0` and omit the bullet list.
   If both lesson directories were empty (or absent) and no lessons were promoted, show: `Session-start self-improvement pass — nothing in queue. Ready.`

5. **Commit all changes** from the pass in a single commit: `chore: session-start self-improvement pass — YYYY-MM-DD` (substitute today's date). If the pass produced no file changes, skip the commit and note "no changes committed" in the summary.

Then wait for the user's first message.

## Intent routing (during session)

After the session-start ritual, when the user expresses one of these intents, read the corresponding internal procedure and follow it:

| User intent | Internal procedure |
|---|---|
| Ask a question grounded in project knowledge | `internal/ask/SKILL.md` |
| Capture a concept/decision as a wiki entry | `internal/capture/SKILL.md` |
| Capture a lesson from the current session | `internal/capture-lesson/SKILL.md` |
| Review draft lessons | `internal/review-lessons/SKILL.md` |
| Convert promoted lessons to wiki entries | `internal/propose-wiki-entry/SKILL.md` |
| Review wiki entries for curation | `internal/review-wiki/SKILL.md` |
| Check wiki staleness against source files | `internal/sync/SKILL.md` |
| Upgrade memex itself | `internal/upgrade/SKILL.md` |
| Run the end-of-session self-improvement loop | `internal/self-improve/SKILL.md` |

The `internal/self-improve/SKILL.md` procedure bundles `capture-lesson` + `review-lessons` + `propose-wiki-entry` for end-of-session use.

## v2 Core CRUD routing (agent-facing — not for end users)

Memex v2 introduces a CRUD substrate (Plan 1) that agents — not the human user — invoke directly. These 10 procedures live at `internal/core/<name>/SKILL.md` and are reachable only via this routing table.

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

The Python implementations live under `scripts/` (`db.py`, `roles.py`, `agents.py`, `registry.py`, `stores.py`, `install.py`). Each SKILL.md is a short documentation wrapper; the agent reads it for the API contract, then calls the implementation.

Plan 2 (Index + 5 internal agents) and Plan 3 (Brain) will add further routing rows here as they land — `internal/index/...`, `internal/brain/...`, `internal/steward/...`, `internal/dba/...`.

## v2 Index, Steward, and DBA routing (agent-facing)

Plan 2 introduces the federated Index (`~/.memex/index.db`) plus five Memex-internal agents: Librarian, Reference Librarian, Archivist, DBA, Data Steward. Their procedures live at `internal/<category>/<name>/SKILL.md` and are invoked through the table below. Like Core, these are agent-only — the human typically reaches them through Brain (Plan 3) rather than directly.

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

The Librarian and Reference Librarian are themselves invoked as LLM subagents inside `index:write` and `index:search` respectively; they read their system prompts from `agents.db.agents.profile`. Archivist, DBA, and Data Steward are deterministic Python modules.

## v2 Brain user-facing intent routing

Plan 3 adds the Memex Brain — the opinionated second-brain layer. Unlike Core / Index / Steward / DBA (which are agent-facing), these 5 procedures are the **daily entry points for the human user**. They live at `internal/brain/<name>/SKILL.md` and are reached via natural-language intent expressed to `memex:run`. The user does NOT invoke `memex:brain:ingest` (or any sibling) as a top-level slash command — those names are not registered in `plugin.json`. Instead the user says e.g. "ingest this article" and `memex:run` routes to the corresponding procedure below.

| User intent | Internal procedure |
|---|---|
| Ingest an article / save a URL / capture a clipped page / add a source to my Brain | `internal/brain/ingest/SKILL.md` |
| Ask a question / search my Brain / recall something I read | `internal/brain/ask/SKILL.md` |
| Capture a note / jot a thought / log an observation | `internal/brain/capture/SKILL.md` |
| Run a Brain health check / lint Brain / audit my knowledge | `internal/brain/lint/SKILL.md` |
| Synthesize across documents / find the through-line / summarize this topic | `internal/brain/synthesize/SKILL.md` |

The Python implementations live in `scripts/brain.py`. Each SKILL.md is a short documentation wrapper; `memex:run` reads it on demand for the procedure contract, then calls the implementation.

## Authority and override

User instructions override this skill's defaults at all times. If the user provides a direct instruction — "skip the session-start pass," "just answer," or any unambiguous bypass directive — comply immediately without re-asking. This skill defines default behavior; it does not constrain the user's authority to change it.

Priority order when instructions conflict:

1. **User's explicit instructions — highest priority.**
2. **Memex methodology (this skill).**
3. **Default system prompt.**
