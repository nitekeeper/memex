# capture-lesson — Reference

## Frontmatter fields

### Required

| Field | Type | Notes |
|---|---|---|
| `id` | string | `<project>:lesson:<slug>`. Type is always `lesson`. Immutable after creation. Never reuse a deleted slug. Prompt if uncertain — never guess. On REPAIR: re-derived as if NEW. |
| `title` | string | Human-readable. Sentence case. |
| `stream` | enum | `inbox` / `feedback`. Auto-routed (see Stream routing). Set at creation; never changed on UPDATE. |
| `status` | enum | `draft` / `promoted` / `discarded`. Always `draft` on NEW or REPAIR. Preserved unchanged on UPDATE. |
| `created` | YYYY-MM-DD | Set to today on NEW or REPAIR; preserved on UPDATE. |

### Optional

| Field | Type | Notes |
|---|---|---|
| `slug` | string | Bare slug only (e.g. `my-lesson`, not `memex:lesson:my-lesson`). Include only when it differs from the filename stem; omit otherwise. |
| `tags` | string[] | Categorization labels. |

---

## Body structure

```
## Observation

<What happened or was noticed. For feedback stream: user's stated direction verbatim or close to it.>

## Why it matters

<The non-obvious implication. What would go wrong without this lesson.>

## How to apply

<Concrete guidance for next time.>
```

---

## Stream routing

| Origin | Stream | Path |
|---|---|---|
| AI proposes the lesson unprompted | `inbox` | `lessons/inbox/<slug>.md` |
| User explicitly states feedback, correction, or direction | `feedback` | `lessons/feedback/<slug>.md` |
| Ambiguous | `inbox` (default) | `lessons/inbox/<slug>.md` |

---

## REPAIR path

REPAIR triggers when: (a) YAML frontmatter cannot be parsed, OR (b) one or more required fields (`id`, `title`, `stream`, `status`) are absent or empty. On REPAIR, all fields are re-derived as if NEW from the current conversation. `created` is excluded from the trigger list because it is always auto-derived as today's date on REPAIR, requiring no content knowledge.

---

## Commit message formats

| Mode | Format |
|---|---|
| On-demand (single lesson) | `lessons: capture — <title>` |
| Session-end (batch) | `lessons: capture — N lessons` |

> **Note:** Commit messages use the Unicode em dash (U+2014, `—`). Before committing: run `git config i18n.commitEncoding`. If the command exits with a non-zero code, or if the output is any value other than empty, `utf-8`, `utf8`, `UTF-8`, or `UTF8` — substitute `--` (ASCII double-hyphen). Otherwise use the em dash.

---

## Error table

| Situation | Action |
|---|---|
| No `lessons/inbox/` at project root | Stop: "No lessons directory found. Create `lessons/inbox/` and `lessons/feedback/` in your project root before running capture-lesson." |
| Multiple detectable projects | Ask user which project to target. Wait for explicit choice. |
| Existing file malformed | REPAIR path: re-derive all fields as if NEW. Gate shows `[REPAIR: previous write failed — re-drafted from conversation]`. |
| `git commit` fails | Show error, do not retry. Written files remain on disk uncommitted. |
| Session-end sweep finds no candidates | Report "No lesson candidates found in this session." Done. |
