import pytest

from scripts.db import get_connection


@pytest.fixture
def tmp_memex_home(monkeypatch, tmp_path):
    """Isolated ~/.memex/ root for tests.

    Sets MEMEX_HOME_ALLOW_UNUSUAL=1 because tmp_path is under /tmp,
    which fails the v2.5.0 $MEMEX_HOME validation.
    """
    home = tmp_path / "memex_home"
    home.mkdir()
    monkeypatch.setenv("MEMEX_HOME", str(home))
    monkeypatch.setenv("MEMEX_HOME_ALLOW_UNUSUAL", "1")
    monkeypatch.setenv("MEMEX_V1_PATH_ALLOW_UNUSUAL", "1")
    return home


@pytest.fixture
def bootstrapped_marker(tmp_memex_home):
    """Lightweight: write registry.json so require_bootstrap() passes."""
    (tmp_memex_home / "registry.json").write_text("{}")
    return tmp_memex_home


@pytest.fixture
def bootstrapped_home(tmp_memex_home):
    """Full install. Use for tests that exercise post-bootstrap behavior."""
    from scripts import install

    install.run()
    return tmp_memex_home


@pytest.fixture
def tmp_settings_path(monkeypatch, tmp_path):
    """Hermetic ~/.claude/settings.json for the settings-recommendation feature.

    Points $CLAUDE_SETTINGS_PATH at tmp_path/.claude/settings.json. The parent
    .claude/ directory is deliberately NOT pre-created so tests exercise the
    mkdir-parent path in apply_recommended / _atomic_write_json. Never touches
    the real ~/.claude.
    """
    target = tmp_path / ".claude" / "settings.json"
    monkeypatch.setenv("CLAUDE_SETTINGS_PATH", str(target))
    return target


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
