"""Store provisioning and generic CRUD."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scripts import registry
from scripts.db import get_connection, require_bootstrap, safe_identifier
from scripts.paths import DB_DIR

# ---------------------------------------------------------------------------
# Migration apply path (reconcile-guarded, per-migration atomic).
#
# Background (the incident this guards against): a store's migration ledger can
# fall BEHIND its actual schema — e.g. the ledger records only 001..003 while
# the schema already has the column 004 would add. The pre-guard runner would
# then re-`executescript` 004 against a store that already had the effect and
# crash with `sqlite3.OperationalError: duplicate column name: ...`, taking the
# whole caller (e.g. /atelier:save) down with it.
#
# The guard treats the SPECIFIC "object already exists" OperationalError family
# as evidence the statement's effect is ALREADY PRESENT, skips just that
# statement as a no-op, and lets the migration be recorded as applied — so the
# ledger self-heals instead of aborting. Crucially it ONLY swallows that narrow
# family; every other error (syntax error, missing dependency, constraint
# failure, ...) still propagates.
#
# Atomicity decision (why a SAVEPOINT + per-statement execution, not executescript):
#   * `sqlite3.Connection.executescript` issues an implicit COMMIT before it
#     runs, which DESTROYS any enclosing SAVEPOINT — so a migration body run via
#     executescript cannot be wrapped in a rollback boundary, and a mid-file
#     failure would leave the store half-migrated with no clean undo.
#   * We therefore run each migration inside an explicit SAVEPOINT, executing
#     its statements one at a time. A genuine (non-already-exists) failure
#     ROLLBACKs the whole file to the savepoint — so a partially-applied
#     migration is never left behind AND is never recorded as applied (the
#     ledger INSERT happens only after a clean RELEASE). This closes the
#     "partial-apply then mark-applied" hazard: on the next run the file is
#     re-attempted from a clean state, not silently skipped.
#   * Statement splitting uses the stdlib `sqlite3.complete_statement()` — the
#     SAME tokenizer-aware boundary logic the sqlite3 shell uses. It correctly
#     accounts for string/identifier literals, comments, and trigger
#     `BEGIN ... END` bodies (it does NOT report a statement complete while
#     inside a trigger body, and it is not fooled by `CASE ... END`, transaction
#     `BEGIN;`/`COMMIT;`, or `begin`/`end` used as identifiers). This structurally
#     avoids the whole class of hand-rolled-tokenizer mis-split bugs.
#
# Atomicity contract (INTENTIONAL — PER-FILE all-or-nothing):
#   * Each migration file is applied inside a SAVEPOINT AND its ledger row is
#     INSERTed inside the SAME savepoint. RELEASEing that savepoint is the commit
#     boundary: it ends the enclosing transaction and makes the file's schema
#     effect AND its ledger row durable together, before the next file runs. So
#     there is NO window where the schema moves ahead of the ledger (the very
#     desync this whole module exists to prevent). (Statements inside the open
#     SAVEPOINT are NOT auto-committed — DDL included — which is exactly why the
#     per-file ROLLBACK TO works.)
#   * This mirrors the pre-guard executescript path's per-file durability: a
#     file that applied cleanly stays applied even if a LATER file in the same
#     call fails. We deliberately do NOT promise whole-call (cross-file)
#     atomicity: each file is independently durable on its RELEASE, so by the
#     time file N+1 runs, files 1..N are already committed and cannot be undone.
#     Coupling schema + ledger per file (so they advance lock-step) is the right
#     contract here — the goal is "never schema-ahead-of-ledger", which per-file
#     commit guarantees; a cross-file rollback would buy nothing and only widen
#     the failure blast radius.
#   * On a genuine (non-already-exists) error mid-file, the SAVEPOINT rolls that
#     file back and nothing is recorded for it; the connection is then closed
#     via try/finally (no WAL connection leak).
# `test_cross_file_*` / `test_*_closes_connection_on_error` pin this.
# ---------------------------------------------------------------------------

# The narrow OperationalError family meaning "this object/effect is already
# present" — duplicate column, or table/index/trigger/view already exists.
# Anchored to SQLite's exact phrasings so unrelated errors never match.
_ALREADY_EXISTS_RE = re.compile(
    r"(?:duplicate column name: )"
    r"|(?:^(?:table|index|trigger|view) .+ already exists$)",
    re.IGNORECASE,
)


def _is_already_exists_error(exc: sqlite3.OperationalError) -> bool:
    """True only for the specific 'object already exists' family (see module note)."""
    return bool(_ALREADY_EXISTS_RE.search(str(exc).strip()))


def _split_sql_statements(script: str) -> list[str]:
    """Split a migration body into individual statements.

    Uses ``sqlite3.complete_statement()`` — the tokenizer-aware boundary check
    the sqlite3 shell itself uses — to decide where each statement ends. We
    accumulate the script up to each ``;`` and emit a statement only once the
    accumulated buffer is a *complete* SQL statement. Because that primitive is
    tokenizer-aware, it does not mis-split on:

      * trigger ``CREATE TRIGGER ... BEGIN ... END`` bodies (the inner ``;`` of
        the trigger's statements, and a ``CASE ... END`` inside the body);
      * ``;`` inside string literals, quoted identifiers, or comments;
      * transaction-control ``BEGIN;`` / ``COMMIT;`` (each is its own complete
        statement) or ``begin``/``end`` used as plain identifiers.

    Statements that are only whitespace/comments are dropped.
    """
    statements: list[str] = []
    buf = ""
    for ch in script:
        buf += ch
        # `complete_statement` only returns True when the buffer ends in `;` and
        # forms a complete statement, so we only ever test at a `;` boundary.
        if ch == ";" and sqlite3.complete_statement(buf):
            stmt = buf.strip()
            if _strip_sql_noise(stmt):
                statements.append(stmt)
            buf = ""
    tail = buf.strip()
    if _strip_sql_noise(tail):
        statements.append(tail)
    return statements


def _strip_sql_noise(stmt: str) -> str:
    """Return the statement with comments/whitespace stripped, for emptiness checks."""
    no_block = re.sub(r"/\*.*?\*/", "", stmt, flags=re.DOTALL)
    no_line = re.sub(r"--[^\n]*", "", no_block)
    return no_line.strip()


def _apply_migration_file(conn: sqlite3.Connection, body: str, filename: str) -> None:
    """Apply one migration file AND record its ledger row, atomically per file.

    The file body and the `migrations` ledger INSERT run inside ONE SAVEPOINT so
    the schema effect and the ledger row advance together — there is never a
    window where the schema is ahead of the ledger (the desync this module
    guards against). RELEASEing the outermost savepoint is the commit boundary:
    it ends the enclosing transaction, making the file's schema effect + ledger
    row durable together before the next file runs (per-file atomicity contract).

    Reconcile guard: a statement that fails with the specific 'object already
    exists' family is treated as ALREADY APPLIED and skipped (a no-op), so a
    ledger that has fallen behind its schema self-heals. Any OTHER error rolls
    the whole file back to the savepoint and propagates — the file is neither
    half-applied nor recorded.
    """
    # Fixed savepoint name: this helper is non-reentrant (one migration file at
    # a time on a single connection), so a constant name cannot collide with
    # itself. If this ever becomes reentrant, switch to a per-call unique name.
    savepoint = "memex_migrate"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        for stmt in _split_sql_statements(body):
            if not _strip_sql_noise(stmt):
                continue
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as exc:
                if _is_already_exists_error(exc):
                    # Effect already present (ledger behind schema) — skip this
                    # statement only; keep applying the rest of the file.
                    continue
                # Annotate with the migration filename for incident diagnosis,
                # preserving the original error type (still an OperationalError).
                raise sqlite3.OperationalError(f"in migration {filename}: {exc}") from exc
        # Ledger row INSIDE the same savepoint → schema + ledger are atomic.
        conn.execute(
            "INSERT INTO migrations (filename, applied_at) VALUES (?, ?)",
            (filename, _now()),
        )
    except Exception:
        conn.execute(f"ROLLBACK TO {savepoint}")
        conn.execute(f"RELEASE {savepoint}")
        raise
    # RELEASE of the outermost savepoint IS the commit boundary: it ends the
    # enclosing transaction, so after this line the file's schema effect + ledger
    # row are durable together. No explicit conn.commit() is needed (and one here
    # would be a no-op on the normal path: in_transaction is already False).
    conn.execute(f"RELEASE {savepoint}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrations_table_sql() -> str:
    return (DB_DIR / "migrations_table.sql").read_text()


def create_store(name: str, path: str, migrations_dir: str, schema_version: str = "v1") -> dict:
    """Create a new SQLite store and register it."""
    require_bootstrap()
    if registry.get_store(name) is not None:
        raise ValueError(f"Store already registered: {name}")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(path)

    conn.executescript(_migrations_table_sql())
    conn.commit()

    try:
        sql_files = sorted(Path(migrations_dir).glob("*.sql"))
        for sql_file in sql_files:
            # _apply_migration_file applies the body + ledger row + commit
            # atomically per file (see its docstring / the module note).
            _apply_migration_file(conn, sql_file.read_text(), sql_file.name)
    except Exception:
        # Per-file contract: already-committed files stay; the in-flight file
        # was savepoint-rolled-back inside the helper. Roll back any pending
        # (uncommitted) work and never leak the connection under WAL.
        conn.rollback()
        raise
    finally:
        conn.close()

    return registry.register_store(name, path, schema_version)


def migrate(name: str, migrations_dir: str) -> list[str]:
    """Apply unapplied .sql files from migrations_dir to a registered store.

    Returns the list of newly-applied filenames.
    """
    require_bootstrap()
    rec = registry.get_store(name)
    if rec is None:
        raise ValueError(f"Unknown store: {name}")

    conn = get_connection(rec["path"])
    applied_set = {r["filename"] for r in conn.execute("SELECT filename FROM migrations")}

    sql_files = sorted(Path(migrations_dir).glob("*.sql"))
    newly_applied: list[str] = []
    try:
        for sql_file in sql_files:
            if sql_file.name in applied_set:
                continue
            # _apply_migration_file applies the body + ledger row + commit
            # atomically per file (see its docstring / the module note).
            _apply_migration_file(conn, sql_file.read_text(), sql_file.name)
            newly_applied.append(sql_file.name)
    except Exception:
        # Per-file contract: already-committed files stay; the in-flight file
        # was savepoint-rolled-back inside the helper. Roll back any pending
        # (uncommitted) work and never leak the connection under WAL.
        conn.rollback()
        raise
    finally:
        conn.close()
    return newly_applied


def _resolve(name: str) -> str:
    rec = registry.get_store(name)
    if rec is None:
        raise ValueError(f"Unknown store: {name}")
    return rec["path"]


def query(name: str, sql: str, params: tuple = ()) -> list[dict]:
    """Execute SELECT against a registered store. Returns list of dict rows."""
    require_bootstrap()
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
    require_bootstrap()
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
    require_bootstrap()
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
    require_bootstrap()
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
