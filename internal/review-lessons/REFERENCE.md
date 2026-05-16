# review-lessons — Reference

## Status transitions

| From | Action | To | File location |
|---|---|---|---|
| `draft` | promote | `promoted` | Moved to `lessons/promoted/<slug>.md` |
| `draft` | discard-with-reason | `discarded` | Stays at `lessons/<stream>/<slug>.md` |
| `draft` | delete (no reason) | _(deleted)_ | Removed from disk |
| `draft` | defer | `draft` | Unchanged |

`status` is the only mutable field during review. All other frontmatter is preserved.

---

## Frontmatter changes by action

### Promote
- `status`: `draft` → `promoted`
- All other fields: unchanged

### Discard-with-reason
- `status`: `draft` → `discarded`
- `discard-reason`: added (new field, string)
- All other fields: unchanged

### Delete
- File removed from disk and git index. No frontmatter update.

---

## `promoted/` directory

The `lessons/promoted/` directory must exist before promotion can proceed. If it is absent, stop and tell the user: 'Create `lessons/promoted/` before promoting lessons.'

---

## Commit message formats

| Situation | Format |
|---|---|
| Mix of actions | `lessons: review — N promoted, M discarded, K deleted` |
| Promote only | `lessons: review — N promoted` |
| Discard/delete only | `lessons: review — N discarded` |
| Single lesson | `lessons: review — <title>` |

> **Note:** Commit messages use the Unicode em dash (U+2014, `—`). Before committing: run `git config i18n.commitEncoding`. If the command exits with a non-zero code, or if the output is any value other than empty, `utf-8`, `utf8`, `UTF-8`, or `UTF8` — substitute `--` (ASCII double-hyphen). Otherwise use the em dash.

---

## Error table

| Situation | Action |
|---|---|
| No `lessons/inbox/` at project root | Stop: "No lessons directory found. Create `lessons/inbox/`, `lessons/feedback/`, and `lessons/promoted/` in your project root." |
| `lessons/promoted/` absent at promotion time | Stop: "Create `lessons/promoted/` before promoting lessons." |
| Multiple detectable projects | Ask user which project to target. Wait for explicit choice. |
| Lesson file malformed (unparseable YAML) | Skip it. Report: "Skipped `<path>` — could not parse frontmatter. Run capture-lesson to repair." |
| `git rm` or `git add` fails | Show error, do not retry. Files already changed on disk remain changed. |
| `git commit` fails | Show error, do not retry. Staged files remain staged. |
