---
description: "Use when the user wants to capture a concept, decision, or summary as a project-wiki page — either on demand during a session (\"capture this as a wiki entry\") or at session end to review and propose pages from the conversation. Also use when the user invokes /capture. Do NOT use for ingesting external sources (use meta:ingest-source) or for staleness checking (use sync)."
---

# capture — write a project-wiki page

## Mode detection

- **On-demand** — user provides a topic, title, draft, or points to a decision from the conversation. Handle this first.
- **Session-end** — user invokes at end of session with no specific topic ("what should we capture?", `/capture` with no args).

Both modes share the approval gate and commit logic.

---

## On-demand mode

1. **Extract content** from user input and/or conversation context:
   - `id`: `<project>:<type>:<slug>` — prompt if uncertain; never guess
   - `title`, `slug`, `tags`, `status` (always `draft` on first write)
   - `describes-files` (only if this page tracks specific source files)
   - `body`: synthesized from conversation or polished from user draft

2. **Check for existing page** at `.ai/wiki/<slug>.md`:
   - Not found → prepare creation plan
   - Found → read it; prepare diff description (which fields and body sections change)

3. **Show approval gate** before touching any file:
   ```
   Will write: .ai/wiki/<slug>.md
   Title: <title>
   Status: draft  |  Tags: [...]
   ~<N> lines
   [NEW] or [UPDATE: <summary of changes>]
   Approve? (yes / edit / skip)
   ```
   If user says **edit**: apply correction, re-enter step 1, show gate again.

4. **On approval**, write the file:
   - `created` and `updated`: today's date (YYYY-MM-DD)
   - `synced-at-commit`: set only if `describes-files` is non-empty; otherwise omit
   - Conform to `docs/WIKI_PAGE_FORMAT.md`. See `REFERENCE.md` for field details.

5. **Validate**: run `python scripts/rebuild.py .ai/`
   - On error: show it, stop, do not commit. Leave file in place for inspection.

6. **Auto-commit**: `wiki: capture <slug> — <title>`

---

## Session-end mode

1. **Review conversation.** Find: decisions made, patterns named, constraints locked, concepts defined. Skip anything already wiki-ified or too ephemeral for the next session.

2. **Propose a batch list** before touching any file:
   ```
   Found N candidates:
   1. .ai/wiki/<slug>.md — "<title>" [NEW]
   2. .ai/wiki/<slug>.md — "<title>" [UPDATE: <summary>]
   Approve all / approve individually / skip?
   ```

3. **Approve all**: run steps 1–5 of on-demand mode for each page in sequence.

4. **Approve individually**: show the per-page gate for each; user approves or skips.

5. **One commit** for the batch: `wiki: capture session — <N> pages`

---

## Error handling

| Situation | Action |
|---|---|
| `rebuild.py` errors after write | Show error, stop, do not commit. Leave file for inspection. |
| `id` already exists at a different path | Flag before writing; do not proceed until resolved. |
| Required field missing | Prompt user; never guess `id`. |

For field definitions and id conventions, see `REFERENCE.md`.
