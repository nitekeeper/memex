"""Reconcile-guard tests for the migration runner.

Guards the incident where a store's migration ledger falls BEHIND its actual
schema (ledger recorded 001..003 while the schema already advanced to include
004's effect). The pre-guard runner re-ran 004 and crashed with
``duplicate column name``. These tests pin the self-healing behavior and its
correctness boundaries:

  (a) fresh store migrates to head;
  (b) desynced store (schema ahead of ledger) reconciles without crashing and
      records the skipped files;
  (c) a genuine non-'already-exists' error still propagates (no blanket-swallow);
  (d) partial-failure rolls the whole file back (no half-applied store), and the
      file is NOT recorded as applied.
"""

import sqlite3
from typing import ClassVar

import pytest

from scripts import stores
from scripts.db import get_connection
from scripts.paths import DB_DIR
from scripts.stores import (
    _apply_migration_file,
    _is_already_exists_error,
    _split_sql_statements,
)


def _make_store(tmp_path, initial_sql="CREATE TABLE tasks (id INTEGER PRIMARY KEY);"):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text(initial_sql)
    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))
    return target, migrations_dir


def _applied(target):
    conn = get_connection(str(target))
    rows = [r["filename"] for r in conn.execute("SELECT filename FROM migrations ORDER BY id")]
    conn.close()
    return rows


def _columns(target, table):
    conn = get_connection(str(target))
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    conn.close()
    return cols


# --- (a) fresh store → head -------------------------------------------------


def test_fresh_store_migrates_to_head(bootstrapped_marker, tmp_path):
    target, migrations_dir = _make_store(tmp_path)
    (migrations_dir / "002_col.sql").write_text(
        "ALTER TABLE tasks ADD COLUMN parallel_group INTEGER;"
    )
    (migrations_dir / "003_idx.sql").write_text("CREATE INDEX idx_pg ON tasks(parallel_group);")
    newly = stores.migrate("alpha", str(migrations_dir))
    assert newly == ["002_col.sql", "003_idx.sql"]
    assert _applied(target) == ["001_init.sql", "002_col.sql", "003_idx.sql"]
    assert "parallel_group" in _columns(target, "tasks")


# --- (b) desynced store (schema ahead of ledger) ----------------------------


def test_desynced_ledger_reconciles_without_crashing(bootstrapped_marker, tmp_path):
    """The exact incident: the column already exists but the ledger lacks 002."""
    target, migrations_dir = _make_store(tmp_path)
    (migrations_dir / "002_col.sql").write_text(
        "ALTER TABLE tasks ADD COLUMN parallel_group INTEGER;"
    )

    # Simulate the desync: apply the column directly to the schema, but DO NOT
    # record 002 in the ledger (ledger now behind the schema).
    conn = get_connection(str(target))
    conn.execute("ALTER TABLE tasks ADD COLUMN parallel_group INTEGER")
    conn.commit()
    conn.close()
    assert _applied(target) == ["001_init.sql"]  # ledger behind
    assert "parallel_group" in _columns(target, "tasks")  # schema ahead

    # Re-running migrate must NOT crash on the duplicate column — it reconciles.
    newly = stores.migrate("alpha", str(migrations_dir))
    assert newly == ["002_col.sql"]
    assert _applied(target) == ["001_init.sql", "002_col.sql"]  # skipped file recorded


def test_desync_reconcile_for_all_already_exists_kinds(bootstrapped_marker, tmp_path):
    """table/index/trigger/view 'already exists' are all treated as applied."""
    target, migrations_dir = _make_store(tmp_path)
    body = (
        "CREATE TABLE extra (x INTEGER);\n"
        "CREATE INDEX idx_extra ON extra(x);\n"
        "CREATE VIEW v_extra AS SELECT x FROM extra;\n"
        "CREATE TRIGGER trg_extra AFTER INSERT ON extra BEGIN\n"
        "  UPDATE extra SET x = x;\n"
        "END;\n"
    )
    (migrations_dir / "002_objects.sql").write_text(body)

    # Pre-create every object directly, leaving the ledger behind.
    conn = get_connection(str(target))
    conn.executescript(body)
    conn.commit()
    conn.close()

    newly = stores.migrate("alpha", str(migrations_dir))
    assert newly == ["002_objects.sql"]
    assert _applied(target) == ["001_init.sql", "002_objects.sql"]


def test_reconcile_still_applies_new_statements_in_mixed_file(bootstrapped_marker, tmp_path):
    """A file mixing an already-present effect with a genuinely-new one applies the new one."""
    target, migrations_dir = _make_store(tmp_path)
    (migrations_dir / "002_mixed.sql").write_text(
        "ALTER TABLE tasks ADD COLUMN parallel_group INTEGER;\n"
        "ALTER TABLE tasks ADD COLUMN wave INTEGER;\n"
    )
    # parallel_group already present; wave is new.
    conn = get_connection(str(target))
    conn.execute("ALTER TABLE tasks ADD COLUMN parallel_group INTEGER")
    conn.commit()
    conn.close()

    stores.migrate("alpha", str(migrations_dir))
    cols = _columns(target, "tasks")
    assert "parallel_group" in cols
    assert "wave" in cols  # the new statement still applied
    assert _applied(target) == ["001_init.sql", "002_mixed.sql"]


# --- (c) genuine non-'already-exists' error propagates ----------------------


def test_genuine_error_propagates(bootstrapped_marker, tmp_path):
    target, migrations_dir = _make_store(tmp_path)
    # Reference a table that does not exist — a real dependency error, NOT an
    # 'already exists' one. Must propagate, not be swallowed.
    (migrations_dir / "002_bad.sql").write_text("ALTER TABLE does_not_exist ADD COLUMN c INTEGER;")
    with pytest.raises(sqlite3.OperationalError):
        stores.migrate("alpha", str(migrations_dir))
    # The failing file must NOT be recorded.
    assert _applied(target) == ["001_init.sql"]


def test_syntax_error_propagates(bootstrapped_marker, tmp_path):
    target, migrations_dir = _make_store(tmp_path)
    (migrations_dir / "002_syntax.sql").write_text("THIS IS NOT SQL;")
    with pytest.raises(sqlite3.OperationalError):
        stores.migrate("alpha", str(migrations_dir))
    assert _applied(target) == ["001_init.sql"]


# --- (d) partial-failure rollback -------------------------------------------


def test_partial_failure_rolls_back_whole_file(bootstrapped_marker, tmp_path):
    """A file whose first statement succeeds but second fails leaves NO partial state."""
    target, migrations_dir = _make_store(tmp_path)
    (migrations_dir / "002_partial.sql").write_text(
        "ALTER TABLE tasks ADD COLUMN good_col INTEGER;\n"
        "ALTER TABLE does_not_exist ADD COLUMN c INTEGER;\n"  # genuine failure
    )
    with pytest.raises(sqlite3.OperationalError):
        stores.migrate("alpha", str(migrations_dir))

    # The first statement's effect must have been rolled back (savepoint undo).
    assert "good_col" not in _columns(target, "tasks")
    # And the file is NOT recorded — so a re-run re-attempts from a clean state.
    assert _applied(target) == ["001_init.sql"]


def test_partial_failure_then_fixed_reruns_cleanly(bootstrapped_marker, tmp_path):
    """After a partial failure is fixed, a re-run applies the file cleanly (no skip)."""
    target, migrations_dir = _make_store(tmp_path)
    bad = migrations_dir / "002_partial.sql"
    bad.write_text(
        "ALTER TABLE tasks ADD COLUMN good_col INTEGER;\n"
        "ALTER TABLE does_not_exist ADD COLUMN c INTEGER;\n"
    )
    with pytest.raises(sqlite3.OperationalError):
        stores.migrate("alpha", str(migrations_dir))

    # Operator fixes the migration; re-run must apply it fully.
    bad.write_text("ALTER TABLE tasks ADD COLUMN good_col INTEGER;\n")
    stores.migrate("alpha", str(migrations_dir))
    assert "good_col" in _columns(target, "tasks")
    assert _applied(target) == ["001_init.sql", "002_partial.sql"]


# --- idempotency / determinism preserved ------------------------------------


def test_fully_applied_store_is_noop(bootstrapped_marker, tmp_path):
    target, migrations_dir = _make_store(tmp_path)
    (migrations_dir / "002_col.sql").write_text(
        "ALTER TABLE tasks ADD COLUMN parallel_group INTEGER;"
    )
    stores.migrate("alpha", str(migrations_dir))
    # Second run: nothing new, no crash, ledger unchanged.
    assert stores.migrate("alpha", str(migrations_dir)) == []
    assert _applied(target) == ["001_init.sql", "002_col.sql"]


def test_repeated_runs_safe(bootstrapped_marker, tmp_path):
    target, migrations_dir = _make_store(tmp_path)
    (migrations_dir / "002_col.sql").write_text(
        "ALTER TABLE tasks ADD COLUMN parallel_group INTEGER;"
    )
    for _ in range(3):
        stores.migrate("alpha", str(migrations_dir))
    conn = get_connection(str(target))
    n = conn.execute("SELECT COUNT(*) AS n FROM migrations").fetchone()["n"]
    conn.close()
    assert n == 2


# --- unit: error classifier + splitter --------------------------------------


@pytest.mark.parametrize(
    "msg",
    [
        "duplicate column name: parallel_group",
        "table tasks already exists",
        "index idx_pg already exists",
        "trigger trg already exists",
        "view v_extra already exists",
    ],
)
def test_classifier_matches_already_exists_family(msg):
    assert _is_already_exists_error(sqlite3.OperationalError(msg))


@pytest.mark.parametrize(
    "msg",
    [
        "no such table: does_not_exist",
        'near "THIS": syntax error',
        "no such column: missing",
        "UNIQUE constraint failed: tasks.id",
        "database is locked",
        # Adversarial: an 'already exists' substring inside an unrelated message
        # must NOT match (the regex is anchored to SQLite's exact phrasing).
        "no such table: my_already_exists_log",
    ],
)
def test_classifier_rejects_other_errors(msg):
    assert not _is_already_exists_error(sqlite3.OperationalError(msg))


def test_splitter_keeps_trigger_body_intact():
    body = (
        "CREATE TABLE t (a INTEGER);\n"
        "CREATE TRIGGER trg AFTER INSERT ON t BEGIN\n"
        "  UPDATE t SET a = 1;\n"
        "  UPDATE t SET a = 2;\n"
        "END;\n"
        "CREATE INDEX ix ON t(a);\n"
    )
    stmts = _split_sql_statements(body)
    assert len(stmts) == 3
    assert stmts[0].startswith("CREATE TABLE")
    assert "BEGIN" in stmts[1] and "END" in stmts[1]
    assert stmts[1].count("UPDATE") == 2  # trigger body not split
    assert stmts[2].startswith("CREATE INDEX")


def test_splitter_ignores_semicolons_in_strings_and_comments():
    body = (
        "CREATE TABLE t (a TEXT DEFAULT 'x;y');\n"
        "-- a comment with ; in it\n"
        "/* block ; comment */\n"
        "INSERT INTO t (a) VALUES ('p;q');\n"
    )
    stmts = _split_sql_statements(body)
    assert len(stmts) == 2


def test_apply_migration_file_rolls_back_on_error(conn):
    # Needs the ledger table since _apply_migration_file records a row.
    conn.executescript((DB_DIR / "migrations_table.sql").read_text())
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.commit()
    with pytest.raises(sqlite3.OperationalError):
        _apply_migration_file(
            conn,
            "ALTER TABLE t ADD COLUMN good INTEGER;\nINSERT INTO no_table VALUES (1);\n",
            "x.sql",
        )
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(t)")}
    assert "good" not in cols  # rolled back
    # Ledger must NOT record the failed file.
    recorded = [r["filename"] for r in conn.execute("SELECT filename FROM migrations")]
    assert "x.sql" not in recorded


def test_apply_migration_file_records_ledger_atomically(conn):
    """The ledger row lands in the SAME savepoint as the body (no desync window)."""
    conn.executescript((DB_DIR / "migrations_table.sql").read_text())
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.commit()
    _apply_migration_file(conn, "ALTER TABLE t ADD COLUMN good INTEGER;", "002.sql")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(t)")}
    recorded = [r["filename"] for r in conn.execute("SELECT filename FROM migrations")]
    assert "good" in cols and "002.sql" in recorded


# --- splitter: C1/C2 regression coverage ------------------------------------


def _exec_all(stmts, setup="CREATE TABLE t (a INTEGER);"):
    """Execute split statements in order against a throwaway DB (autocommit)."""
    c = sqlite3.connect(":memory:")
    c.isolation_level = None
    c.executescript(setup)
    for s in stmts:
        c.execute(s)
    c.close()


def test_splitter_case_end_inside_trigger_body_not_split():
    """C1: a CASE ... END inside a trigger body must NOT close the trigger early."""
    body = (
        "CREATE TRIGGER trg AFTER INSERT ON t BEGIN\n"
        "  UPDATE t SET a = CASE WHEN a = 1 THEN 2 ELSE 3 END;\n"
        "END;\n"
    )
    stmts = _split_sql_statements(body)
    assert len(stmts) == 1  # one CREATE TRIGGER, not split on the CASE's END
    assert "CASE" in stmts[0] and stmts[0].rstrip().endswith("END;")
    _exec_all(stmts)  # and it actually executes cleanly


def test_splitter_transaction_control_begin_commit():
    """C2: bare BEGIN; / COMMIT; are their own statements, not an open block."""
    body = "BEGIN;\nCREATE TABLE q (x INTEGER);\nCOMMIT;\n"
    stmts = _split_sql_statements(body)
    assert len(stmts) == 3
    assert stmts[0].upper().startswith("BEGIN")
    assert stmts[1].upper().startswith("CREATE TABLE")
    assert stmts[2].upper().startswith("COMMIT")


def test_splitter_begin_transaction_variants():
    body = "BEGIN TRANSACTION;\nCREATE TABLE q (x INTEGER);\nCOMMIT TRANSACTION;\n"
    stmts = _split_sql_statements(body)
    assert len(stmts) == 3


def test_splitter_begin_end_as_identifiers():
    """C2: begin/end used as column identifiers must not be parsed as keywords."""
    body = 'CREATE TABLE u ("end" INTEGER, begin INTEGER);\nCREATE TABLE v (z INTEGER);\n'
    stmts = _split_sql_statements(body)
    assert len(stmts) == 2
    _exec_all(stmts, setup="SELECT 1;")


def test_splitter_nested_begin_end():
    body = (
        "CREATE TRIGGER trg AFTER INSERT ON t BEGIN\n"
        "  SELECT 1;\n"
        "  SELECT 2;\n"
        "END;\n"
        "CREATE TABLE w (x INTEGER);\n"
    )
    stmts = _split_sql_statements(body)
    assert len(stmts) == 2
    assert stmts[0].count("SELECT") == 2  # both inner statements kept together


def test_splitter_trigger_with_when_clause():
    body = (
        "CREATE TRIGGER trg AFTER UPDATE ON t WHEN NEW.a = 1 BEGIN\n  UPDATE t SET a = 2;\nEND;\n"
    )
    stmts = _split_sql_statements(body)
    assert len(stmts) == 1
    _exec_all(stmts)


def test_case_end_trigger_migrates_end_to_end(bootstrapped_marker, tmp_path):
    """A real migration carrying a CASE-in-trigger applies without a split crash."""
    target, migrations_dir = _make_store(tmp_path)
    (migrations_dir / "002_trg.sql").write_text(
        "CREATE TRIGGER bump AFTER INSERT ON tasks BEGIN\n"
        "  UPDATE tasks SET id = CASE WHEN NEW.id = 0 THEN 1 ELSE NEW.id END;\n"
        "END;\n"
    )
    stores.migrate("alpha", str(migrations_dir))
    conn = get_connection(str(target))
    triggers = {
        r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
    }
    conn.close()
    assert "bump" in triggers


# --- atomicity contract (INTENTIONAL: PER-FILE all-or-nothing) --------------


def test_per_file_atomicity_earlier_files_durable(bootstrapped_marker, tmp_path):
    """A failure at file N+1 leaves files applied earlier in the SAME call durable.

    Per-file contract: each file's schema effect + ledger row commit together
    before the next file runs, so an earlier success is NOT rolled back by a
    later failure — and the ledger never drifts ahead of/behind the schema.
    """
    target, migrations_dir = _make_store(tmp_path)
    (migrations_dir / "002_ok.sql").write_text("CREATE TABLE good (x INTEGER);")
    (migrations_dir / "003_bad.sql").write_text("ALTER TABLE nope ADD COLUMN c INTEGER;")
    with pytest.raises(sqlite3.OperationalError):
        stores.migrate("alpha", str(migrations_dir))

    conn = get_connection(str(target))
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    applied = [r["filename"] for r in conn.execute("SELECT filename FROM migrations ORDER BY id")]
    conn.close()
    # 002 committed per-file (durable); 003 failed and was savepoint-rolled-back.
    assert "good" in tables
    assert applied == ["001_init.sql", "002_ok.sql"]


def test_per_file_atomicity_no_ledger_schema_desync_on_failure(bootstrapped_marker, tmp_path):
    """The failing file leaves NEITHER its schema effect NOR a ledger row (lock-step)."""
    target, migrations_dir = _make_store(tmp_path)
    # First statement is valid DDL, second fails → savepoint rolls BOTH back,
    # and the ledger row (also inside the savepoint) is rolled back too.
    (migrations_dir / "002_partial.sql").write_text(
        "ALTER TABLE tasks ADD COLUMN halfway INTEGER;\nALTER TABLE nope ADD COLUMN c INTEGER;\n"
    )
    with pytest.raises(sqlite3.OperationalError):
        stores.migrate("alpha", str(migrations_dir))

    conn = get_connection(str(target))
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
    applied = [r["filename"] for r in conn.execute("SELECT filename FROM migrations")]
    conn.close()
    assert "halfway" not in cols  # schema not advanced
    assert "002_partial.sql" not in applied  # ledger not advanced → no desync


def test_previous_call_durable(bootstrapped_marker, tmp_path):
    """Files committed by a PREVIOUS call survive a later failed call."""
    target, migrations_dir = _make_store(tmp_path)
    (migrations_dir / "002_ok.sql").write_text("CREATE TABLE good (x INTEGER);")
    stores.migrate("alpha", str(migrations_dir))  # commits 002 durably

    (migrations_dir / "003_bad.sql").write_text("ALTER TABLE nope ADD COLUMN c INTEGER;")
    with pytest.raises(sqlite3.OperationalError):
        stores.migrate("alpha", str(migrations_dir))

    conn = get_connection(str(target))
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    applied = [r["filename"] for r in conn.execute("SELECT filename FROM migrations ORDER BY id")]
    conn.close()
    assert "good" in tables  # previous call's work is durable
    assert applied == ["001_init.sql", "002_ok.sql"]


# --- connection-leak guard (H1) ---------------------------------------------


class _TrackingConn(sqlite3.Connection):
    """Connection subclass that records close() calls (Connection.close is read-only)."""

    closes: ClassVar[list] = []

    def close(self):
        type(self).closes.append(True)
        super().close()


def _patch_tracking_connection(monkeypatch):
    """Make stores.get_connection hand back a close-tracking connection."""
    _TrackingConn.closes = []

    def tracking_get(path):
        # Reproduce get_connection's pragmas but with our subclass factory.
        from pathlib import Path as _P

        _P(path).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(path, timeout=5.0, factory=_TrackingConn)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("PRAGMA foreign_keys = ON")
        return c

    monkeypatch.setattr(stores, "get_connection", tracking_get)


def test_migrate_closes_connection_on_error(bootstrapped_marker, tmp_path, monkeypatch):
    """On the error path, the connection MUST be closed (try/finally), not leaked."""
    _, migrations_dir = _make_store(tmp_path)  # uses the real helper
    (migrations_dir / "002_bad.sql").write_text("ALTER TABLE nope ADD COLUMN c INTEGER;")
    # Swap in the tracking connection only for the failing migrate() call.
    _patch_tracking_connection(monkeypatch)
    with pytest.raises(sqlite3.OperationalError):
        stores.migrate("alpha", str(migrations_dir))
    assert _TrackingConn.closes, "connection was not closed on the error path (leak)"


def test_create_store_closes_connection_on_error(bootstrapped_marker, tmp_path, monkeypatch):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_bad.sql").write_text("ALTER TABLE nope ADD COLUMN c INTEGER;")
    _patch_tracking_connection(monkeypatch)
    with pytest.raises(sqlite3.OperationalError):
        stores.create_store("beta", str(tmp_path / "beta.db"), str(migrations_dir))
    assert _TrackingConn.closes, "connection was not closed on the error path (leak)"


# --- real shipped migrations: pin the splitter against db/*.sql -------------


def test_real_shipped_migrations_split_and_execute_in_order():
    """Every real db/*.sql executes statement-by-statement through the splitter.

    Pins the splitter against the actual shipped DDL so a future CASE-using
    trigger (or any other construct) can't silently regress the boundary logic.
    """
    sql_files = sorted(DB_DIR.glob("*.sql"))
    assert sql_files, f"no shipped migrations found in {DB_DIR}"

    c = sqlite3.connect(":memory:")
    c.isolation_level = None
    # Seed the universal migrations tracker the runner injects first.
    c.executescript((DB_DIR / "migrations_table.sql").read_text())
    for sql_file in sql_files:
        if sql_file.name == "migrations_table.sql":
            continue
        stmts = _split_sql_statements(sql_file.read_text())
        # Round-trip: splitter output must be non-empty and each piece must be a
        # complete statement that executes cleanly in file order.
        assert stmts, f"{sql_file.name} split to zero statements"
        for stmt in stmts:
            assert sqlite3.complete_statement(
                stmt if stmt.rstrip().endswith(";") else stmt + ";"
            ), f"{sql_file.name}: incomplete fragment: {stmt[:60]!r}"
            c.execute(stmt)
    c.close()
