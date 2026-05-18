"""Plugin-anchored filesystem constants.

Resource files (SQL migrations, prompt templates) live inside the
installed plugin bundle and must be resolved relative to this file,
not CWD. Stable API: PLUGIN_ROOT, DB_DIR, PROMPTS_DIR.
"""

from __future__ import annotations

from pathlib import Path

# scripts/paths.py → scripts/ → <plugin_root>
# .resolve() follows symlinks intentionally (legitimate dev pattern:
# ~/.claude/plugins/memex symlinked to a working tree).
PLUGIN_ROOT: Path = Path(__file__).resolve().parent.parent

DB_DIR: Path = PLUGIN_ROOT / "db"
PROMPTS_DIR: Path = PLUGIN_ROOT / "prompts"

# Defensive: fail at import time on broken bundle layouts.
if not (DB_DIR / "migrations_table.sql").is_file():
    raise ImportError(
        f"Memex bundle layout broken: {DB_DIR}/migrations_table.sql not found. "
        f"PLUGIN_ROOT resolved to {PLUGIN_ROOT}. See docs/PACKAGING.md."
    )
