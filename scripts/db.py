"""Database connection, Memex home-directory helpers, and v2.5.0 preconditions."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

MEMEX_DIR_NAME = ".memex"

# SQLite identifier syntax: ASCII letter or underscore, followed by letters,
# digits, or underscores. Anything else is rejected to prevent SQL injection
# through interpolated identifiers (SQLite parameter binding only handles
# values, not table or column names — so identifiers must be interpolated,
# but only after this whitelist check).
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def safe_identifier(name: str) -> str:
    """Validate a SQL identifier before interpolation."""
    if not isinstance(name, str):
        raise ValueError(f"identifier must be str, got {type(name).__name__}")
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"invalid SQL identifier: {name!r}. Allowed: [A-Za-z_][A-Za-z0-9_]*")
    return name


def get_connection(db_path: str | os.PathLike[str]) -> sqlite3.Connection:
    """Open a SQLite connection with Memex pragmas applied."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    if mode.lower() != "wal":
        conn.close()
        raise RuntimeError(f"Could not enable WAL mode (got {mode!r})")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


class MemexHomeInvalidError(ValueError):
    """$MEMEX_HOME or default ~/.memex/ failed validation (v2.5.0 §E)."""


class MemexNotInitializedError(RuntimeError):
    """Memex Python invoked before ~/.memex/ is bootstrapped (v2.5.0 §A)."""


def memex_home() -> Path:
    """Resolve the Memex home directory, with validation in both branches.

    Order:
      - $MEMEX_HOME if set → validated (no symlink, under $HOME unless ALLOW_UNUSUAL=1)
      - else Path.home() / .memex → validated (no symlink unless ALLOW_UNUSUAL=1)

    Raises MemexHomeInvalidError on invalid input.
    """
    allow_unusual = os.environ.get("MEMEX_HOME_ALLOW_UNUSUAL") == "1"
    explicit = os.environ.get("MEMEX_HOME")

    if explicit:
        candidate = Path(explicit).expanduser()
        # Check is_symlink BEFORE resolve (resolve collapses symlinks).
        if not allow_unusual and candidate.exists() and candidate.is_symlink():
            raise MemexHomeInvalidError(
                f"$MEMEX_HOME ({candidate}) is a symlink; refusing to write through it. "
                f"Set MEMEX_HOME_ALLOW_UNUSUAL=1 to override."
            )
        resolved = candidate.resolve()
        if not allow_unusual:
            try:
                resolved.relative_to(Path.home().resolve())
            except ValueError as err:
                raise MemexHomeInvalidError(
                    f"$MEMEX_HOME ({resolved}) is not under your home directory "
                    f"({Path.home().resolve()}). Set MEMEX_HOME_ALLOW_UNUSUAL=1 to override."
                ) from err
        return resolved

    # Default branch — validate ~/.memex/ is not a symlink either.
    home = Path.home() / MEMEX_DIR_NAME
    if not allow_unusual and home.exists() and home.is_symlink():
        raise MemexHomeInvalidError(
            f"{home} is a symlink; refusing to write through it. "
            f"Set MEMEX_HOME_ALLOW_UNUSUAL=1 to override."
        )
    return home


def require_bootstrap() -> None:
    """Precondition for public Memex entries that write under memex_home().

    Lazy-imports PLUGIN_ROOT to avoid an import-time cascade from scripts.paths.

    Raises MemexNotInitializedError with operator guidance if ~/.memex/registry.json
    is absent.
    """
    home = memex_home()
    if not (home / "registry.json").exists():
        from scripts.paths import PLUGIN_ROOT

        raise MemexNotInitializedError(
            f"Memex is not bootstrapped at {home}.\n"
            f"To bootstrap:\n"
            f"  PYTHONPATH={PLUGIN_ROOT} python3 -m scripts.install\n"
            f"Or, in Claude Code, invoke memex:run and accept the prompt."
        )


def read_plugin_root_config() -> Path | None:
    """Read plugin_root from ~/.memex/config.json. None if absent or invalid.

    Validation: returned path must contain `scripts/install.py` (regular file)
    AND `plugin.json` whose JSON contains `"name": "memex"`.
    """
    try:
        home = memex_home()
    except MemexHomeInvalidError:
        return None
    config_path = home / "config.json"
    if not config_path.is_file():
        return None
    try:
        data = json.loads(config_path.read_text())
        candidate = Path(data["plugin_root"])
        if not (candidate / "scripts" / "install.py").is_file():
            return None
        # Plugin manifest lives at <root>/.claude-plugin/plugin.json (Claude Code convention).
        plugin_json = candidate / ".claude-plugin" / "plugin.json"
        if not plugin_json.is_file():
            return None
        manifest = json.loads(plugin_json.read_text())
        if manifest.get("name") != "memex":
            return None
        return candidate
    except (json.JSONDecodeError, KeyError, OSError, ValueError):
        return None


def write_plugin_root_config(plugin_root: Path) -> None:
    """Write {plugin_root: <abs>} to ~/.memex/config.json.

    Creates ~/.memex/ if needed.
    """
    home = memex_home()
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.json"
    config_path.write_text(json.dumps({"plugin_root": str(plugin_root)}, indent=2) + "\n")
