from scripts import agents, install, registry, roles
from scripts.db import memex_home


def test_install_creates_memex_home(tmp_memex_home):
    install.run()
    assert memex_home().is_dir()
    assert (memex_home() / "agents.db").exists()
    assert (memex_home() / "raw").is_dir()
    assert (memex_home() / "backups").is_dir()
    assert (memex_home() / "audits").is_dir()


def test_install_registers_agents_db(tmp_memex_home):
    install.run()
    rec = registry.get_store("agents")
    assert rec is not None


def test_install_idempotent(tmp_memex_home):
    install.run()
    install.run()  # second call must not error
    rec = registry.get_store("agents")
    assert rec is not None


def test_install_seeds_five_internal_roles(tmp_memex_home):
    install.run()
    agents_db = str(memex_home() / "agents.db")
    listed = roles.list_roles(agents_db)
    role_names = {r["name"] for r in listed}
    assert role_names == {
        "Librarian",
        "Reference Librarian",
        "Archivist",
        "Database Administrator",
        "Data Steward",
    }


def test_install_seeds_five_internal_agents(tmp_memex_home):
    install.run()
    agents_db = str(memex_home() / "agents.db")
    listed = agents.list_agents(agents_db)
    agent_ids = {a["id"] for a in listed}
    assert agent_ids == {
        "librarian-1",
        "reference-librarian-1",
        "archivist-1",
        "dba-1",
        "data-steward-1",
    }


def test_install_creates_index_db(tmp_memex_home):
    install.run()
    assert (memex_home() / "index.db").exists()


def test_install_registers_index_in_registry(tmp_memex_home):
    install.run()
    rec = registry.get_store("index")
    assert rec is not None
    assert rec["path"] == str(memex_home() / "index.db")


def test_install_is_idempotent_with_seeds(tmp_memex_home):
    install.run()
    install.run()  # second call must not duplicate or error
    agents_db = str(memex_home() / "agents.db")
    listed = agents.list_agents(agents_db)
    assert len(listed) == 5  # not 10


def test_install_creates_article_db(tmp_memex_home):
    install.run()
    assert (memex_home() / "article.db").exists()


def test_install_registers_article_in_registry(tmp_memex_home):
    install.run()
    rec = registry.get_store("article")
    assert rec is not None


def test_install_migrates_existing_index_db_to_unique_key(tmp_memex_home):
    """Spec §6.4: re-running install on a pre-existing index.db that was
    created before UNIQUE(key) landed must upgrade in place — drop the old
    non-unique index, create documents_key_unique_idx, succeed."""
    from scripts.db import get_connection

    # Stand up an "old" index.db without the unique invariant
    index_db = memex_home() / "index.db"
    index_db.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(str(index_db))
    conn.executescript(
        """
        CREATE TABLE documents (
            index_id TEXT PRIMARY KEY, key TEXT, domain TEXT NOT NULL,
            store TEXT NOT NULL, table_name TEXT NOT NULL, row_id TEXT NOT NULL,
            searchable TEXT, metadata TEXT, embedding BLOB,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX documents_key_idx ON documents(key);
        """
    )
    conn.commit()
    conn.close()

    install.run()  # must upgrade

    conn = get_connection(str(index_db))
    row = conn.execute(
        "SELECT \"unique\" FROM pragma_index_list('documents') "
        "WHERE name = 'documents_key_unique_idx'"
    ).fetchone()
    old_idx = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'documents_key_idx'"
    ).fetchone()
    conn.close()
    assert row is not None and row["unique"] == 1
    assert old_idx is None  # superseded non-unique index dropped


def test_install_migration_is_idempotent(tmp_memex_home):
    """Re-running install after the migration must no-op cleanly."""
    install.run()
    install.run()  # second invocation hits the "already migrated" branch
    from scripts.db import get_connection

    conn = get_connection(str(memex_home() / "index.db"))
    row = conn.execute(
        "SELECT \"unique\" FROM pragma_index_list('documents') "
        "WHERE name = 'documents_key_unique_idx'"
    ).fetchone()
    conn.close()
    assert row is not None and row["unique"] == 1


def test_install_migration_refuses_when_existing_duplicates_present(tmp_memex_home):
    """Spec §6.4: if the legacy DB has pre-existing duplicate keys, the
    migration must refuse rather than silently merge or delete. Operator
    resolves manually, then re-runs."""
    import pytest

    from scripts.db import get_connection

    index_db = memex_home() / "index.db"
    index_db.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(str(index_db))
    conn.executescript(
        """
        CREATE TABLE documents (
            index_id TEXT PRIMARY KEY, key TEXT, domain TEXT NOT NULL,
            store TEXT NOT NULL, table_name TEXT NOT NULL, row_id TEXT NOT NULL,
            searchable TEXT, metadata TEXT, embedding BLOB,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX documents_key_idx ON documents(key);
        """
    )
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("a", "dup", "article", "brain", "articles", "1", "x", "system"),
    )
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("b", "dup", "article", "brain", "articles", "2", "y", "system"),
    )
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="duplicate key"):
        install.run()


def test_install_archives_v1_if_present(tmp_memex_home, tmp_path, monkeypatch):
    v1_dir = tmp_path / "memex-v1"
    v1_dir.mkdir()
    (v1_dir / ".ai").mkdir()
    (v1_dir / ".ai" / "memex.db").write_text("v1")
    monkeypatch.setenv("MEMEX_V1_PATH", str(v1_dir))

    install.run()

    legacy = memex_home() / "legacy" / "v1-wiki"
    assert legacy.exists()
    assert (legacy / "memex.db").exists()
