# Memex User Guide

**Version:** v0.1.0  
**Audience:** AI agents and developers using Memex in a project

---

## What Memex is

Memex gives any project a persistent, searchable wiki — written and maintained by AI agents, with exact git-commit staleness detection and a lesson-capture loop.

The primary user is the **AI working on the project**. The human approves entries; the AI authors and retrieves them. Every write requires an explicit approval gate — nothing is written silently.

---

## Prerequisites

- Claude Code (or any AI agent that can invoke skills)
- Python 3.9+
- Git
- `pip install python-frontmatter`

---

## Installation

### Step 1 — Copy skills

Copy the contents of `skills/` into your Claude Code skills directory. Each skill lives in its own subdirectory with a `SKILL.md` and `REFERENCE.md`.

### Step 2 — Place scripts

Copy `scripts/` and `db/` to a stable location accessible from your project. The recommended pattern is a sibling directory:

```
projects/
  my-project/        ← your project
  memex/             ← Memex install
    scripts/
    db/
```

Record the Memex path in your project's `CLAUDE.md`:

```
Memex scripts: python C:\path\to\memex\scripts\rebuild.py .ai/
```

### Step 3 — Create project directories

```bash
mkdir -p .ai/wiki lessons/inbox lessons/feedback lessons/promoted
```

### Step 4 — Gitignore the DB

```bash
echo ".ai/memex.db" >> .gitignore
```

The DB is a derived artifact — it is rebuilt from markdown on demand and must not be committed.

### Step 5 — Build the initial index

```bash
python /path/to/memex/scripts/rebuild.py .ai/
```

This creates `.ai/memex.db`. Run this command any time wiki files are added or changed outside of a Memex skill session.

---

## Project structure

A Memex-enabled project contains:

```
.ai/
  wiki/          ← wiki entries (one .md file per entry)
  memex.db       ← derived SQLite index (gitignored)
  ACTIVE.md      ← current focus pointer (optional)
lessons/
  inbox/         ← AI-captured lessons awaiting review
  feedback/      ← user-direct corrections (higher priority)
  promoted/      ← lessons approved and moved here after review
```

---

## The two loops

Memex runs two complementary loops:

### Wiki loop — build and maintain project knowledge

```
capture → (sync to detect drift) → review-wiki
```

Use `capture` to write wiki entries when you learn something worth retaining. Use `sync` periodically to detect entries that track source files and have gone stale. Use `review-wiki` quarterly (or when goal drift is suspected) to approve drafts and archive stale entries.

### Lesson loop — self-improvement from session observations

```
capture-lesson → review-lessons → propose-wiki-entry
```

At session end, run `capture-lesson` to sweep the conversation for non-obvious observations. Then run `review-lessons` to promote, defer, or discard each draft. Promoted lessons can be converted to wiki entries via `propose-wiki-entry`.

---

## The 7 skills

### `capture` — write or update a wiki entry

**When to use:** when a session surfaces a pattern, decision, or piece of project knowledge worth retaining. Also use to update an existing entry when its content has drifted.

**What it does:**
- On-demand: user provides a topic; AI drafts an entry and shows an approval gate before writing
- Session-end: sweeps the conversation for entry candidates

**Output:** `.ai/wiki/<slug>.md` committed to git. The DB is rebuilt automatically after each write.

---

### `sync` — detect stale entries

**When to use:** when source files have changed and you want to know which wiki entries track those files and may be outdated.

**What it does:** runs `sync.py` against the project root, reports entries whose `describes-files` have changed since `synced-at-commit`. For each stale entry, shows a conflict gate with the diff and a proposed revision.

**Key concept — `synced-at-commit`:** when an entry is stamped, the current git HEAD SHA is written into its frontmatter. On the next sync, the script compares that SHA to HEAD — if tracked files changed between those commits, the entry is flagged as stale. This is exact staleness, not heuristic.

---

### `ask` — answer questions from the wiki

**When to use:** when you need to answer a question about the project and want to draw from accumulated knowledge first.

**What it does:** tiered resolution —
1. **Tier 1 (local wiki):** FTS5 search against `.ai/memex.db`. If results are sufficient, answer and cite.
2. **Tier 2 (web):** if local results are insufficient, run a web search. Offer to capture durable findings.
3. **Tier 3 (model knowledge):** if web returns nothing useful, answer from training knowledge with an explicit confidence disclosure.

---

### `capture-lesson` — record session observations

**When to use:** at session end to sweep for lessons, or on-demand when a specific observation is worth capturing.

**What it does:** finds non-obvious observations, mid-session corrections, and "why" decisions from the conversation. Shows a candidate list, then gates each one before writing. Two streams:
- `lessons/inbox/` — AI-captured observations
- `lessons/feedback/` — user-direct corrections (higher priority in review)

---

### `review-lessons` — promote, defer, or discard drafts

**When to use:** at session close (if lessons were captured), or for periodic review of accumulated drafts.

**What it does:** scans `lessons/feedback/` and `lessons/inbox/` for `status: draft` entries. Shows each one with its "How to apply" section. Three actions:
- **promote** → moves to `lessons/promoted/`, suggests follow-up (wiki entry, skill update)
- **discard** → option to log a reason; deleted by default
- **defer** → leave in place, continue

---

### `propose-wiki-entry` — convert promoted lessons to wiki entries

**When to use:** after a `review-lessons` session produces promoted lessons, or when a promoted lesson is ready to become permanent knowledge.

**What it does:** scans `lessons/promoted/` for entries not yet matched to a wiki entry. For each, drafts a wiki entry (rewritten from lesson prose into compact, reusable reference form) and shows an approval gate before writing.

---

### `review-wiki` — curation pass

**When to use:** quarterly, or when goal drift is suspected, or after a major doctrine change.

**What it does:** scans `.ai/wiki/` for draft entries (priority) and optionally stale approved entries. For each, offers three actions:
- **approve** → sets `status: approved`
- **archive** → sets `status: archived` with a required reason
- **defer** → no change

---

## Workflow example

A typical session close:

```
1. Session ends
2. Run capture-lesson (session-end mode)
   → AI sweeps conversation, presents 3 candidates
   → You approve 2, skip 1
   → 2 lesson files written to lessons/inbox/
3. Run review-lessons
   → Shows both draft lessons
   → You promote 1, discard 1
   → 1 lesson moved to lessons/promoted/
4. (Optional) Run propose-wiki-entry
   → Drafts wiki entry from promoted lesson
   → You approve
   → Entry written to .ai/wiki/, DB rebuilt
```

---

## Rebuilding the index

Run after any manual changes to wiki files or after copying entries from another project:

```bash
python /path/to/memex/scripts/rebuild.py .ai/
```

The skills call `rebuild.py` automatically after writing entries — you only need this for manual changes.

---

## What's not in v0.1.0

- No embedding-based search (FTS5 only)
- No cross-project federation
- No automatic promotion (every write requires approval)
- No release tooling skill (planned v0.2)

See `docs/MEMEX_SPEC.md` for the full non-goals list.
