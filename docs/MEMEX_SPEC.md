# Memex — Product Spec

> Version 0.1 — locked 2026-05-10.

## What it is

Memex is a set of AI skills and supporting scripts that give any project a persistent, searchable wiki — written and maintained by AI agents, with exact staleness detection tied to git commits.

The primary user is the AI working on the project, not the human. The human approves entries; the AI authors and retrieves them.

## What it does

| Capability | Skill | Script |
|---|---|---|
| Write or update a wiki entry | `capture` | — |
| Detect stale entries (file-tracked) | `sync` | `sync.py` |
| Search the wiki (FTS5) | `ask` | `search.py` |
| Capture a lesson from a session | `capture-lesson` | — |
| Review and promote/discard lessons | `review-lessons` | — |
| Convert promoted lessons to wiki entries | `propose-wiki-entry` | — |
| Curation pass over existing entries | `review-wiki` | — |
| Rebuild the SQLite index from markdown | — | `rebuild.py` |

## What it doesn't do

- **No general note-taking.** Wiki entries must be project-bound, AI-relevant knowledge. Personal notes, meeting summaries, and todo lists are out of scope.
- **No real-time sync.** The DB is rebuilt on demand via `rebuild.py`, not continuously updated.
- **No access control.** All entries are plain markdown files in `.ai/wiki/`. The git repo is the access layer.
- **No cross-project federation.** Each project has one DB at `.ai/memex.db`. There is no shared index.
- **No automatic promotion.** Every wiki entry write and lesson promotion requires user approval via an explicit gate. Nothing is written silently.

## Project structure

A Memex-enabled project contains:

```
.ai/
  wiki/          ← wiki entries (WIKI_PAGE_FORMAT.md)
  memex.db       ← derived SQLite index (do not edit directly)
  ACTIVE.md      ← current focus pointer (optional, standard)
  DIGEST.md      ← one-page project summary (optional, standard)
lessons/
  inbox/         ← AI-captured lessons awaiting review
  feedback/      ← user-direct feedback (higher priority)
  promoted/      ← lessons approved for wiki conversion
```

## Install

1. Copy `skills/` into your Claude Code skills directory.
2. Copy `scripts/` and `db/` to a stable location (e.g. `<project>/../memex/scripts/`).
3. Install the Python runtime dependency: `pip install python-frontmatter`.
4. Create `.ai/wiki/`, `lessons/inbox/`, `lessons/feedback/`, `lessons/promoted/` in your project.
5. Run `python rebuild.py .ai/` to initialize the DB.

## Versioning

- Wiki entries and lesson files are version-controlled in git. The DB is a derived artifact — it is not committed to git (add `.ai/memex.db` to `.gitignore`).
- Skills are versioned by the Memex product release. The `MANIFEST.md` in each release declares what's included.

## What "approved" means

`status: approved` on a wiki entry means: an AI reviewed it and a human confirmed it at a gate. It does not mean "factually correct forever." Entries decay as code changes. Use `sync` to surface entries whose source files have drifted.
