# Memex

A project-wiki capability for AI systems — persistent, searchable knowledge with exact git-commit staleness detection and a built-in self-improvement loop.

The name comes from Vannevar Bush's 1945 *As We May Think* — a memory extender that follows associative trails through documents.

---

## What it does

Memex gives AI agents the ability to:

- **Build and maintain a project wiki** — structured entries in `.ai/wiki/`, indexed in SQLite for full-text search
- **Know precisely what's stale** — not heuristically, but by comparing `synced-at-commit` to repo HEAD
- **Capture and promote lessons** — surface non-obvious observations from sessions, review them, promote them into wiki entries
- **Curate deliberately** — every write and promotion requires explicit approval; nothing is written silently

---

## Install

**Requirements:** Claude Code, Python 3.9+, git

```bash
# 1. Install the Python dependency
pip install python-frontmatter

# 2. Copy the Memex skills into your Claude Code skills directory
#    (copy dist/skills/ to wherever your project loads skills from)

# 3. Create the project directories
mkdir -p .ai/wiki lessons/inbox lessons/feedback lessons/promoted

# 4. Add the DB to .gitignore
echo ".ai/memex.db" >> .gitignore

# 5. Build the index
python /path/to/memex/scripts/rebuild.py .ai/
```

See `dist/USER_GUIDE.md` for full setup and workflow instructions.

---

## Skills

| Skill | When to use |
|---|---|
| `internal/capture/SKILL.md` | Write or update a wiki entry |
| `internal/sync/SKILL.md` | Check whether file-tracked entries have gone stale |
| `internal/ask/SKILL.md` | Answer a question from the wiki (FTS), then web, then model |
| `internal/capture-lesson/SKILL.md` | Record a session observation as a lesson |
| `internal/review-lessons/SKILL.md` | Promote, defer, or discard draft lessons |
| `internal/propose-wiki-entry/SKILL.md` | Convert promoted lessons into wiki entries |
| `internal/review-wiki/SKILL.md` | Curation pass — approve drafts, archive stale entries |

---

## Quick start

```
Session ends → run capture-lesson → review-lessons → propose-wiki-entry
                                                     → review-wiki (quarterly)
Question arises → run ask
Source files change → run sync
```

---

## Releases

Current release: **v0.1.0** (2026-05-10) — 7 skills, 3 scripts, dogfood-validated against Skill Atelier.

See `CHANGELOG.md` for release history and `dist/MANIFEST.md` for what's in the current release.

---

## Contributing / development

This is Product 1 of [Skill Atelier](https://github.com/nitekeeper/skill-atelier). See `CLAUDE.md` for session entry instructions and `DESIGN_NOTES.md` for decisions made so far.
