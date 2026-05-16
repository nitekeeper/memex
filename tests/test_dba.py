from scripts.agents import dba
from scripts.db import get_connection


def test_integrity_check_passes_on_clean_db(tmp_path):
    db = tmp_path / "clean.db"
    conn = get_connection(str(db))
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    result = dba.integrity_check(str(db))
    assert result == "ok"


def test_checkpoint_passive_succeeds(tmp_path):
    db = tmp_path / "wal.db"
    conn = get_connection(str(db))
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.commit()
    conn.close()

    # PASSIVE checkpoint returns (busy, log_pages, checkpointed_pages)
    result = dba.checkpoint(str(db), mode="PASSIVE")
    assert isinstance(result, dict)
    assert "busy" in result
    assert "log_pages" in result
    assert "checkpointed" in result


def test_vacuum_succeeds(tmp_path):
    db = tmp_path / "v.db"
    conn = get_connection(str(db))
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.commit()
    conn.close()

    # Should not raise; reduces file size after data churn
    dba.vacuum(str(db))


def test_foreign_key_check_returns_violations(tmp_path):
    db = tmp_path / "fk.db"
    conn = get_connection(str(db))
    conn.executescript("""
        CREATE TABLE parent (id INTEGER PRIMARY KEY);
        CREATE TABLE child (
            id INTEGER PRIMARY KEY,
            parent_id INTEGER REFERENCES parent(id)
        );
    """)
    conn.commit()
    # Bypass FK enforcement temporarily to insert bad data
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("INSERT INTO child (id, parent_id) VALUES (1, 999)")
    conn.commit()
    conn.close()

    violations = dba.foreign_key_check(str(db))
    assert len(violations) == 1
    assert violations[0]["table"] == "child"


def test_journal_mode_is_wal(tmp_path):
    db = tmp_path / "w.db"
    conn = get_connection(str(db))
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.commit()
    conn.close()

    assert dba.journal_mode(str(db)) == "wal"
