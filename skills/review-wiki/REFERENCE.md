# review-wiki — Reference

## Status transitions

| From | Action | To |
|---|---|---|
| `draft` | approve | `approved` |
| `draft` | archive | `archived` |
| `approved` | archive | `archived` |
| any | defer | unchanged |

`review-wiki` never transitions `approved` → `draft`. If an approved entry needs content changes, use `capture`.

---

## Frontmatter changes by action

### Approve
- `status`: `draft` → `approved`
- `updated`: set to today
- All other fields: unchanged

### Archive
- `status`: any → `archived`
- `archived-reason`: added or updated with the provided reason
- `updated`: set to today
- All other fields: unchanged (including `synced-at-commit`, `describes-files` — `sync` owns those)

---

## Staleness note

`review-wiki` shows staleness indicators (Priority 2 bucket) but does not modify `synced-at-commit` or `describes-files`. Those fields are owned by `sync`. If an approved entry with `describes-files` appears stale, direct the user to run `sync` after the review pass.

---

## Commit message formats

| Situation | Format |
|---|---|
| Mix of actions | `wiki: review — N approved, M archived` |
| Approve only | `wiki: review — N approved` |
| Archive only | `wiki: review — N archived` |
| Single entry | `wiki: review — <title>` |

> **Note:** Commit messages use the Unicode em dash (U+2014, `—`). Before committing: run `git config i18n.commitEncoding`. If the command exits with a non-zero code, or if the output is any value other than empty, `utf-8`, `utf8`, `UTF-8`, or `UTF8` — substitute `--` (ASCII double-hyphen). Otherwise use the em dash.

---

## Error table

| Situation | Action |
|---|---|
| No `.ai/wiki/` at project root | Stop: "No project wiki found. Create `.ai/wiki/` before running review-wiki." |
| Multiple detectable projects | Ask user which project to target. Wait for explicit choice. |
| Entry malformed (unparseable YAML) | Skip it. Report: "Skipped `<path>` — could not parse frontmatter. Use capture to repair." |
| Archive action — no reason provided | Re-ask. Do not archive without a reason. |
| `git add` fails | Show error, do not retry. Changes already applied on disk remain. |
| `git commit` fails | Show error, do not retry. Staged files remain staged. |
