import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


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
