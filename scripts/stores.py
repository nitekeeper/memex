"""Store provisioning and generic CRUD."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts.db import get_connection
from scripts import registry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrations_table_sql() -> str:
    return Path("db/migrations_table.sql").read_text()


def create_store(name: str, path: str, migrations_dir: str, schema_version: str = "v1") -> dict:
    """Create a new SQLite store and register it."""
    if registry.get_store(name) is not None:
        raise ValueError(f"Store already registered: {name}")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(path)

    conn.executescript(_migrations_table_sql())
    conn.commit()

    sql_files = sorted(Path(migrations_dir).glob("*.sql"))
    for sql_file in sql_files:
        conn.executescript(sql_file.read_text())
        conn.execute(
            "INSERT INTO migrations (filename, applied_at) VALUES (?, ?)",
            (sql_file.name, _now()),
        )
    conn.commit()
    conn.close()

    return registry.register_store(name, path, schema_version)


def migrate(name: str, migrations_dir: str) -> list[str]:
    """Apply unapplied .sql files from migrations_dir to a registered store.

    Returns the list of newly-applied filenames.
    """
    rec = registry.get_store(name)
    if rec is None:
        raise ValueError(f"Unknown store: {name}")

    conn = get_connection(rec["path"])
    applied_set = {
        r["filename"] for r in conn.execute("SELECT filename FROM migrations")
    }

    sql_files = sorted(Path(migrations_dir).glob("*.sql"))
    newly_applied: list[str] = []
    for sql_file in sql_files:
        if sql_file.name in applied_set:
            continue
        conn.executescript(sql_file.read_text())
        conn.execute(
            "INSERT INTO migrations (filename, applied_at) VALUES (?, ?)",
            (sql_file.name, _now()),
        )
        newly_applied.append(sql_file.name)
    conn.commit()
    conn.close()
    return newly_applied
