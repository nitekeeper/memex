# Memex User Guide

**Version:** v0.2.0  
**Audience:** AI agents and developers using Memex in a project

---

## What Memex is

Memex gives any project a persistent, searchable wiki — written and maintained by AI agents, with exact git-commit staleness detection and a self-improvement loop.

The primary user is the **AI working on the project**. The human approves entries; the AI authors and retrieves them. Every write requires an explicit approval gate — nothing is written silently.

---

## Prerequisites

- Claude Code (or any AI agent that can invoke skills)
- Python 3.9+
- Git
- `pip install python-frontmatter`

---

## Installation

The recommended install pattern bundles Memex inside the consumer project:

```
my-project/
  memex/           ← Memex dist/ copied here
    scripts/
    db/
    skills/
    docs/
  .ai/
    wiki/
  lessons/
```

### Step 1 — Copy dist/

Copy the contents of the Memex `dist/` directory into `memex/` inside your project.

### Step 2 — Copy skills

Copy the contents of `memex/skills/` into your Claude Code skills directory. Each skill lives in its own subdirectory with a `SKILL.md` and `REFERENCE.md`.

### Step 3 — Declare config in CLAUDE.md

Add these two lines to your project's `CLAUDE.md`:

```
- `memex_path`: path to the Memex git repo on disk (used by the upgrade skill)
- `memex_dir`: path to the memex/ install directory inside your project
```

Example:

```
- `memex_path`: C:\Users\you\Documents\Skills\memex
- `memex_dir`: C:\Users\you\Documents\Projects\my-project\memex
```

Also update the rebuild command reference:

```
Rebuild the index: python memex/scripts/rebuild.py .ai/
```

### Step 4 — Create project directories

```bash
mkdir -p .ai/wiki lessons/inbox lessons/feedback lessons/promoted
```

### Step 5 — Gitignore the DB and migration log

```
.ai/memex.db
.ai/applied_migrations.txt
```

The DB is a derived artifact — rebuilt from markdown on demand, never committed.

### Step 6 — Build the initial index

```bash
python memex/scripts/rebuild.py .ai/
```

This creates `.ai/memex.db`. Run this any time wiki files are added or changed outside of a Memex skill session.

---

## Project structure

A Memex-enabled project contains:

```
memex/             ← Memex install (bundled dist/)
  scripts/
  skills/
  db/
  docs/
.ai/
  wiki/            ← wiki entries (one .md file per entry)
  memex.db         ← derived SQLite index (gitignored)
  ACTIVE.md        ← current focus pointer (optional)
lessons/
  inbox/           ← AI-captured lessons awaiting review
  feedback/        ← user-direct corrections (higher priority)
  promoted/        ← lessons approved and moved here after review
```

---

## The two loops

Memex runs two complementary loops:

### Wiki loop — build and maintain project knowledge

```
capture → (sync to detect drift) → review-wiki
```

Use `capture` to write wiki entries when you learn something worth retaining. Use `sync` periodically to detect entries that track source files and have gone stale. Use `review-wiki` quarterly (or when goal drift is suspected) to approve drafts and archive stale entries.

### Self-improvement loop — learn from session observations

```
capture-lesson → review-lessons → propose-wiki-entry
```

At session end, run `capture-lesson` (or `self-improve` for a unified entry point) to sweep the conversation for non-obvious observations. Then run `review-lessons` to promote, defer, or discard each draft. Promoted lessons can be converted to wiki entries via `propose-wiki-entry`.

---

## The 9 skills

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

**What it does:** scans `lessons/feedback/` and `lessons/inbox/` for `status: draft` entries. Held items (marked `held-for-review: true`) surface first. Three actions per lesson:
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

### `self-improve` — unified self-improvement entry point

**When to use:** at session end as a single command instead of running capture-lesson → review-lessons → propose-wiki-entry individually.

**Two modes:**
- **Solo:** autonomous sweep — captures confident lessons, holds uncertain ones, runs review and propose without approval gates, shows a summary. Use when working alone.
- **Collaborative:** user-guided — all existing approval gates intact. Use when you want to review each step together.

---

### `upgrade` — upgrade Memex to a newer version

**When to use:** when a new Memex version is available and you want to update the bundled install.

**What it does:** reads `memex_path` and `memex_dir` from `CLAUDE.md`, detects current vs. latest version from git tags, shows the changelog excerpt, asks for approval, checks out the new version, copies the full `dist/` into `memex_dir`, runs any pending schema migrations, and rebuilds the DB.

**Requires:** `memex_path` and `memex_dir` declared in `CLAUDE.md` (see Installation above).

---

## Workflow example

A typical session close:

```
1. Session ends
2. Run self-improve (solo mode)
   → AI sweeps conversation, captures 2 confident lessons to lessons/inbox/
   → Holds 1 uncertain lesson with held-for-review: true
   → Runs review-lessons autonomously, promotes 1, defers held item
   → Runs propose-wiki-entry, drafts entry, writes to .ai/wiki/
   → Shows summary
```

Or collaboratively:

```
1. Run self-improve (collaborative mode)
   → Shows candidate lessons, you approve each
   → Review-lessons with approval gates
   → Propose-wiki-entry with approval gate
```

---

## Rebuilding the index

Run after any manual changes to wiki files or after copying entries from another project:

```bash
python memex/scripts/rebuild.py .ai/
```

The skills call `rebuild.py` automatically after writing entries — you only need this for manual changes.

---

## What's not in v0.2.0

- No embedding-based search (FTS5 only)
- No cross-project federation
- No automatic promotion (every write requires approval)

See `docs/MEMEX_SPEC.md` for the full non-goals list.
