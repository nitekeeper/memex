# upgrade — Reference

## Inputs

| Field | Source | Required | Description |
|---|---|---|---|
| `memex_path` | `CLAUDE.md` | yes | Absolute path to the Memex git repo on disk |
| `memex_dir` | `CLAUDE.md` | yes | Absolute path to the installed Memex directory in the product |

## Version detection

Current version is read from `<memex_dir>/MANIFEST.md`. The header line format is:

    # Memex vX.Y.Z — Release Manifest

Latest available version is the topmost result of:

    git -C <memex_path> tag --list "v*" --sort=-version:refname

## applied_migrations.txt

Tracks which SQL migrations have already been applied to `.ai/memex.db`. Lives at
`.ai/applied_migrations.txt`. One filename per line. Created on first migration run if absent.

## Error table

| Condition | Action |
|---|---|
| `memex_path` missing from `CLAUDE.md` | Stop — ask user to add it |
| `memex_dir` missing from `CLAUDE.md` | Stop — ask user to add it |
| `MANIFEST.md` not found in `memex_dir` | Stop — Memex may not be installed |
| `git fetch` fails | Stop — report git error |
| `git checkout` fails | Stop — do not proceed |
| Migration SQL fails | Stop — do not apply further migrations |
| `rebuild.py` fails | Report error — upgrade otherwise complete |

## Invocation

Typically called by the parent product's upgrade skill. Can also be invoked directly:

    upgrade memex
    update memex
