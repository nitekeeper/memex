# Capture Skill v0 — Design Spec

**Date:** 2026-05-10
**Product:** Memex
**Status:** Approved — ready for implementation plan

---

## Goal

Build the `capture` skill: an AI skill that writes or updates a project-wiki page from a session, conforming to `docs/WIKI_PAGE_FORMAT.md`.

---

## File layout

```
skills/capture/
  SKILL.md        # ≤100 lines — the procedure
  REFERENCE.md    # format field reference; pulled in only when needed
```

No `EXAMPLES.md` for v0. Following `wiki:tdd-for-skill-authoring`: write only what baseline testing reveals is needed. Add examples after the first refactor cycle.

---

## Skill description (the trigger text)

> Use when the user wants to capture a concept, decision, or summary as a project-wiki page — either on demand during a session ("capture this as a wiki entry") or at session end to review and propose pages from the conversation. Also use when the user invokes `/capture`. Do NOT use for ingesting external sources (use `meta:ingest-source`) or for staleness checking (use `sync`).

---

## Mode detection

The skill uses a single entry point with two modes detected from invocation intent:

- **On-demand mode** — user provides a topic, title, draft, or points to something in conversation. Common case (~80% of invocations). Documented first in `SKILL.md`.
- **Session-end mode** — user invokes at session end with no specific topic ("what should we capture?", "let's close out", `/capture` with no args). Documented second.

Both modes share the same approval gate and commit logic.

---

## On-demand mode (common case)

**Trigger:** user provides a topic, title, or draft — or points to a decision/concept from the conversation.

**Procedure:**

1. **Extract content.** From user input and/or conversation context, derive: `id` (namespaced slug `<project>:<type>:<slug>`), `title`, `slug`, `tags`, `status` (always `draft` on first write), `describes-files` (if code-tracking), and `body`.

2. **Check for existing page.** Look for `.ai/wiki/<slug>.md` in the target project.
   - If not found: prepare a creation plan.
   - If found: read it and prepare a diff description (what would change: fields, body sections).

3. **Show approval gate.** One compact block before any write:
   ```
   Will write: .ai/wiki/<slug>.md
   Title: <title>
   Status: draft  |  Tags: [...]
   ~<N> lines
   [NEW] or [UPDATE: <summary of changes>]
   Approve? (yes / edit / skip)
   ```

4. **On approval:** write the file conforming to `docs/WIKI_PAGE_FORMAT.md`.
   - Set `created` and `updated` to today's date.
   - Set `synced-at-commit` only if `describes-files` is non-empty; leave null otherwise.

5. **Validate.** Run `python scripts/rebuild.py .ai/` — if it errors, show the error and stop. Do not commit. Leave the file in place for inspection.

6. **Auto-commit.** `wiki: capture <slug> — <title>`

---

## Session-end mode

**Trigger:** user invokes at session end with no specific topic.

**Procedure:**

1. **Review conversation.** Identify: decisions made, patterns identified, constraints locked, concepts named and defined. Skip anything already wiki-ified or too ephemeral to be useful next session.

2. **Propose a batch list.** Show all candidates before touching any file:
   ```
   Found N candidates to capture:
   1. .ai/wiki/<slug>.md — "<title>" [NEW]
   2. .ai/wiki/<slug>.md — "<title>" [UPDATE: <summary of changes>]
   Approve all / approve individually / skip?
   ```

3. **On "approve all":** run on-demand steps 1–5 for each page in sequence. Each page gets its own approval gate (batch approval covers the list; individual gates cover content).

4. **On "approve individually":** show the per-page gate for each candidate; user approves or skips each.

5. **One commit for the session-end run** (not per page): `wiki: capture session — <N> pages`

---

## Error handling

| Situation | Behavior |
|---|---|
| `rebuild.py` fails after write | Show error, do not commit. Leave file in place for inspection. |
| `id` collision (same id, different path) | Flag before writing: "id `x:wiki:y` already exists at a different path — resolve before capturing." |
| Missing required frontmatter fields | Prompt user for the missing value before showing the gate. Never guess `id`. |
| User says "edit" at the gate | Re-enter extraction step with user's correction; show gate again. |

---

## REFERENCE.md content

Pulled in only when the agent needs field details during a capture:

- Full frontmatter field table (required + standard-optional + extension fields) — sourced from `docs/WIKI_PAGE_FORMAT.md`
- Lifecycle state definitions (`draft` / `approved` / `archived`)
- `id` naming convention: `<project>:<type>:<slug>`, immutable after creation, never reuse deleted slugs
- Commit message formats:
  - Single: `wiki: capture <slug> — <title>`
  - Batch: `wiki: capture session — <N> pages`

`SKILL.md` links to `REFERENCE.md` with: "For field definitions and id conventions, see `REFERENCE.md`."

---

## Design decisions and rationale

| Decision | Rationale |
|---|---|
| Single skill, intent-detected modes | One entry point the user always reaches with `/capture`; no flags to remember. Common case first. |
| Approval gate before every write | From `wiki:approval-gate-with-escape-hatches`: unguarded writes are the primary failure mode in AI-maintained knowledge systems. |
| `status: draft` always on first write | Curation state must be explicit human decision. AI never self-approves. |
| `rebuild.py` validation before commit | Rebuild script is the format contract enforcer — if it rejects the page, the commit doesn't happen. |
| Auto-commit (no prompt) | Decided during brainstorming: reduces friction after the approval gate has already been the control point. |
| One commit for session-end batch | Keeps git history clean; the commit message lists the count. |
| No `EXAMPLES.md` for v0 | `wiki:tdd-for-skill-authoring`: add examples after baseline testing reveals which cases need illustration. |

---

## What this spec does NOT cover (deferred)

- `!! capture` escape hatch (bypasses per-page gate, runs deduplication check) — deferred to refactor cycle after baseline testing
- `sync` skill (staleness detection) — Plan 3 of 3
- `search` skill — separate skill
- Targeting a project other than the current working directory — v0 always writes to `.ai/wiki/` in the current project
