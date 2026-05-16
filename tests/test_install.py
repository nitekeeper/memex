import pytest
from scripts import install, registry, roles
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


def test_install_does_not_seed_internal_agents_in_core(tmp_memex_home):
    """Plan 1 (Core) does NOT seed the 5 Memex internal agents.
    That happens in Plan 2 (Index + agents). Core only sets up infrastructure."""
    install.run()
    agents_db = str(memex_home() / "agents.db")
    listed = roles.list_roles(agents_db)
    assert listed == []
