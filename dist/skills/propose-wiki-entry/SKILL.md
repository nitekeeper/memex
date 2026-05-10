---
description: "Use when the user wants to convert promoted lessons into wiki entries — either after a review-lessons session or on demand. Also use when the user wants to propose a wiki entry from an observed pattern without going through lesson capture first. Do NOT use for reviewing existing wiki entries (use review-wiki), writing arbitrary wiki pages (use capture), or reviewing lesson drafts (use review-lessons)."
---

# propose-wiki-entry — convert promoted lessons into wiki entries

## Project detection

Confirm both a lesson root and a wiki root before proceeding:

- **No `lessons/promoted/`**: stop. Tell the user: 'No promoted lessons directory found.'
- **No `.ai/wiki/`**: stop. Tell the user: 'No project wiki found. Create `.ai/wiki/` before running propose-wiki-entry.'
- **More than one detectable project for either root**: ask the user which project. Wait for explicit choice.

A project is detectable if it contains `lessons/promoted/` or `.ai/wiki/` at its root. Check each root at this fixed path only; do not recurse.

---

## Procedure

1. **Scan** `lessons/promoted/` for all `.md` files with parseable frontmatter.
   - Skip files whose `id` slug already has a matching `.ai/wiki/<slug>.md` (heuristic: compare the slug portion of the lesson `id` to filename stems in `.ai/wiki/`).

2. **Show candidate list** before drafting anything:
   ```
   Found N promoted lessons available for wiki conversion:
   1. <title> (lessons/promoted/<slug>.md)
   2. <title> (lessons/promoted/<slug>.md)
   Proceed through each? (yes / select / cancel)
   ```
   - **yes** → process all candidates in order
   - **select** → user names which to process (e.g. "1, 3"); process only those
   - **cancel** → stop, write nothing
   - No candidates → report "No unmatched promoted lessons found." Done.

3. **For each selected lesson**, draft a wiki entry:
   - `id`: `<project>:wiki:<slug>` — derive `<project>` from the lesson's `id`; use the lesson's slug; prompt if uncertain
   - `title`, `tags`: carry from lesson; refine title if the lesson title reads more like a journal entry than a wiki heading
   - `status`: always `draft`
   - `created`, `updated`: today
   - Body: rewrite from the lesson's three sections (Observation / Why it matters / How to apply) into wiki prose — do not copy verbatim; synthesize into a compact, reusable reference entry

4. **Show approval gate** before writing:
   ```
   Will write: .ai/wiki/<slug>.md
   Title: <title>
   Status: draft  |  Tags: [...]
   ~<N> lines
   [FROM: lessons/promoted/<source-slug>.md]
   Approve? (yes / edit / skip / cancel / quit)
   ```
   - **yes** → write file
   - **edit** → apply correction, re-show gate
   - **skip** → move to next candidate
   - **cancel** / **quit** → stop; already-written files remain
   - Any other message → treat as edit instruction

5. **On approval** → write `.ai/wiki/<slug>.md`, then validate:
   Run `python scripts/rebuild.py .ai/` from the project root.
   - On error: show it, stop, do not commit. Leave file in place. Tell the user to fix and re-run capture for that slug.

6. **After all candidates** → if any files were written and validated:
   Stage each written file individually. Commit: `wiki: propose — N entries from lessons`

---

## Error handling

See REFERENCE.md.
