import pytest

from scripts.db import get_connection


@pytest.fixture
def tmp_memex_home(monkeypatch, tmp_path):
    """Isolated ~/.memex/ root for tests."""
    home = tmp_path / "memex_home"
    home.mkdir()
    monkeypatch.setenv("MEMEX_HOME", str(home))
    return home


@pytest.fixture
def tmp_store_path(tmp_path):
    """Disposable SQLite store path."""
    return tmp_path / "store.db"


@pytest.fixture
def conn(tmp_store_path):
    """Opened SQLite connection with Memex pragmas; closed on teardown."""
    c = get_connection(tmp_store_path)
    try:
        yield c
    finally:
        c.close()
