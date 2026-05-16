"""Database Administrator — deterministic SQLite operational primitives.

No LLM involvement. The DBA's profile defines the operating rules; this
module implements them as Python functions.
"""
from __future__ import annotations
from scripts.db import get_connection


def integrity_check(db_path: str) -> str:
    """Run PRAGMA integrity_check. Returns 'ok' on clean DB, otherwise
    a concatenated string of issues."""
    conn = get_connection(db_path)
    rows = [r[0] for r in conn.execute("PRAGMA integrity_check")]
    conn.close()
    if rows == ["ok"]:
        return "ok"
    return "; ".join(rows)


def foreign_key_check(db_path: str) -> list[dict]:
    """Run PRAGMA foreign_key_check. Returns a list of violation dicts
    (empty list if no violations).

    Each row: (table, rowid, parent, fkid)
    """
    conn = get_connection(db_path)
    cur = conn.execute("PRAGMA foreign_key_check")
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


def checkpoint(db_path: str, mode: str = "PASSIVE") -> dict:
    """Run a WAL checkpoint. Mode is one of PASSIVE | FULL | RESTART | TRUNCATE.
    Returns dict with busy / log_pages / checkpointed counts."""
    conn = get_connection(db_path)
    row = conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
    conn.close()
    return {
        "busy": row[0],
        "log_pages": row[1],
        "checkpointed": row[2],
    }


def vacuum(db_path: str) -> None:
    """Run VACUUM. Reclaims free space."""
    conn = get_connection(db_path)
    conn.execute("VACUUM")
    conn.commit()
    conn.close()


def analyze(db_path: str) -> None:
    """Run ANALYZE. Updates query planner statistics."""
    conn = get_connection(db_path)
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()


def journal_mode(db_path: str) -> str:
    conn = get_connection(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    return mode.lower()
