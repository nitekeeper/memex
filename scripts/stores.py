"""Store provisioning and generic CRUD."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts import registry
from scripts.db import get_connection, safe_identifier


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
    applied_set = {r["filename"] for r in conn.execute("SELECT filename FROM migrations")}

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


def _resolve(name: str) -> str:
    rec = registry.get_store(name)
    if rec is None:
        raise ValueError(f"Unknown store: {name}")
    return rec["path"]


def query(name: str, sql: str, params: tuple = ()) -> list[dict]:
    """Execute SELECT against a registered store. Returns list of dict rows."""
    conn = get_connection(_resolve(name))
    cur = conn.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def insert(name: str, table: str, row: dict) -> dict:
    """Insert a row. Returns the inserted row (including the new PK).

    Assumes the table has an integer PRIMARY KEY AUTOINCREMENT column
    named `id`. For tables with TEXT PKs, the caller supplies `id` in `row`.
    """
    safe_table = safe_identifier(table)
    cols = list(row.keys())
    for c in cols:
        safe_identifier(c)
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    conn = get_connection(_resolve(name))
    cur = conn.execute(
        f"INSERT INTO {safe_table} ({col_list}) VALUES ({placeholders})",  # nosec B608 - identifiers validated via safe_identifier
        tuple(row[c] for c in cols),
    )
    conn.commit()
    new_id = row.get("id", cur.lastrowid)
    fetched = conn.execute(
        f"SELECT * FROM {safe_table} WHERE id = ?",  # nosec B608 - identifier validated
        (new_id,),
    ).fetchone()
    conn.close()
    return dict(fetched) if fetched else row


def update(name: str, table: str, row_id, updates: dict) -> dict | None:
    if not updates:
        return None
    safe_table = safe_identifier(table)
    for k in updates:
        safe_identifier(k)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn = get_connection(_resolve(name))
    conn.execute(
        f"UPDATE {safe_table} SET {set_clause} WHERE id = ?",  # nosec B608 - identifiers validated
        (*updates.values(), row_id),
    )
    conn.commit()
    fetched = conn.execute(
        f"SELECT * FROM {safe_table} WHERE id = ?",  # nosec B608 - identifier validated
        (row_id,),
    ).fetchone()
    conn.close()
    return dict(fetched) if fetched else None


def delete(name: str, table: str, row_id) -> bool:
    safe_table = safe_identifier(table)
    conn = get_connection(_resolve(name))
    cur = conn.execute(
        f"DELETE FROM {safe_table} WHERE id = ?",  # nosec B608 - identifier validated
        (row_id,),
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
