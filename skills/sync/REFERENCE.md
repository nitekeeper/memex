# sync — Reference

## Stamp procedure

When stamping a page (fast-forward or after conflict-gate approval):
1. Read the file at the page path.
2. Update `synced-at-commit` to the HEAD SHA (use the `head` field from the JSON report).
3. Update `updated` to today's date (YYYY-MM-DD — read from session context `# currentDate` if present; otherwise run `Get-Date -Format yyyy-MM-dd` on Windows or `date +%Y-%m-%d` on POSIX).
4. Write the file back. Do not change any other field.
5. Do not run `rebuild.py` — the sync skill manages only `synced-at-commit` and `updated`.

## Git commands used by `sync.py`

| Purpose | Command |
|---|---|
| Get HEAD SHA | `git rev-parse HEAD` |
| Validate a SHA exists | `git cat-file -t <sha>` |
| Get diff for a file | `git diff <sha>..HEAD -- <file>` |

## Assessment rule

**Default conservative: if in doubt, treat as conflict.**

**Fast-forward** — diff is purely cosmetic: whitespace normalization, comment rewording, or file moves with no semantic change. The page content remains fully accurate after the change.

**Conflict** — any structural or semantic change to a tracked file, any new information not yet reflected in the page, or any doubt about accuracy. The cost of a false conflict is one extra approval. The cost of a false fast-forward is silently stale wiki content.

## Page states (from `sync.py` JSON output)

| State | Meaning |
|---|---|
| `STALE` | `describes-files` set + `synced-at-commit` set; files changed since that commit |
| `NEVER_SYNCED` | `describes-files` set; `synced-at-commit` absent or null |
| `CLEAN` | `describes-files` set + `synced-at-commit` set; no files changed since that commit |
| `UNTRACKED` | No `describes-files`; concept/decision page; not evaluated by sync |

## Commit message format

`wiki: sync — N pages`

N is the count of pages stamped (fast-forward + conflict-approved combined).

> **Em dash encoding check:** Before committing, run `git config i18n.commitEncoding`. If the command exits with code 0 and output is empty, `utf-8`, `utf8`, `UTF-8`, or `UTF8` — use the Unicode em dash (U+2014, `—`). Otherwise substitute `--` (ASCII double-hyphen). If `git commit` fails for any reason, show the git error and do not retry.
