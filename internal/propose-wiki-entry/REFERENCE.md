# propose-wiki-entry — Reference

## Body rewrite guidance

The lesson body uses three fixed sections (Observation / Why it matters / How to apply). The wiki entry body is free-form. When converting:

- **Observation** → opening paragraph or `## Context` section
- **Why it matters** → `## Why` or inline in the opening
- **How to apply** → `## How to apply` or `## Guidance`

Short lessons (< 10 lines) → collapse all three into a single flowing paragraph.
Long lessons (> 20 lines) → keep named sections.

Titles: if the lesson title starts with "I noticed…", "We found…", or similar first-person phrasing, rewrite as a declarative wiki heading. Example: "I noticed parallel agents share context" → "Parallel agents share context by default".

---

## Slug matching heuristic

The heuristic for "already converted" compares the slug portion of `lessons/promoted/<slug>.md` (filename stem) to the filename stems in `.ai/wiki/`. It is a best-effort check — a promoted lesson whose wiki counterpart has a different slug will appear in the candidate list. The user can skip it manually.

---

## Commit message format

| Situation | Format |
|---|---|
| Multiple entries | `wiki: propose — N entries from lessons` |
| Single entry | `wiki: propose — <title>` |

> **Note:** Commit messages use the Unicode em dash (U+2014, `—`). Before committing: run `git config i18n.commitEncoding`. If the command exits with a non-zero code, or if the output is any value other than empty, `utf-8`, `utf8`, `UTF-8`, or `UTF8` — substitute `--` (ASCII double-hyphen). Otherwise use the em dash.

---

## Error table

| Situation | Action |
|---|---|
| No `lessons/promoted/` at project root | Stop: "No promoted lessons directory found." |
| No `.ai/wiki/` at project root | Stop: "No project wiki found. Create `.ai/wiki/` before running propose-wiki-entry." |
| Multiple detectable projects | Ask user which project to target. Wait for explicit choice. |
| Lesson file malformed | Skip it. Report: "Skipped `<path>` — could not parse frontmatter." |
| `rebuild.py` fails | Show error, stop, do not commit. Written files remain on disk. |
| `git commit` fails | Show error, do not retry. Staged files remain staged. |
