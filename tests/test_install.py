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
