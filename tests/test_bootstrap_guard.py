"""require_bootstrap() + memex_home() validation + config helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.db import (
    MemexHomeInvalidError,
    MemexNotInitializedError,
    memex_home,
    read_plugin_root_config,
    require_bootstrap,
    write_plugin_root_config,
)


def test_require_bootstrap_raises_when_missing(tmp_memex_home):
    with pytest.raises(MemexNotInitializedError) as exc_info:
        require_bootstrap()
    msg = str(exc_info.value)
    assert "not bootstrapped" in msg.lower()
    assert str(tmp_memex_home) in msg


def test_require_bootstrap_passes_when_present(bootstrapped_marker):
    require_bootstrap()


def test_error_subclasses():
    assert issubclass(MemexNotInitializedError, RuntimeError)
    assert issubclass(MemexHomeInvalidError, ValueError)


def test_error_message_resolves_plugin_root(tmp_memex_home):
    from scripts.paths import PLUGIN_ROOT

    with pytest.raises(MemexNotInitializedError) as exc_info:
        require_bootstrap()
    msg = str(exc_info.value)
    assert "<plugin_root>" not in msg
    assert str(PLUGIN_ROOT) in msg


def test_memex_home_default(monkeypatch):
    monkeypatch.delenv("MEMEX_HOME", raising=False)
    monkeypatch.delenv("MEMEX_HOME_ALLOW_UNUSUAL", raising=False)
    assert memex_home() == Path.home() / ".memex"


def test_memex_home_rejects_outside_home(monkeypatch):
    monkeypatch.setenv("MEMEX_HOME", "/etc/memex")
    monkeypatch.delenv("MEMEX_HOME_ALLOW_UNUSUAL", raising=False)
    with pytest.raises(MemexHomeInvalidError):
        memex_home()


def test_memex_home_rejects_root(monkeypatch):
    monkeypatch.setenv("MEMEX_HOME", "/")
    monkeypatch.delenv("MEMEX_HOME_ALLOW_UNUSUAL", raising=False)
    with pytest.raises(MemexHomeInvalidError):
        memex_home()


def test_memex_home_rejects_symlinked_explicit(monkeypatch, tmp_path):
    """$MEMEX_HOME set to a symlink → reject."""
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    monkeypatch.setenv("MEMEX_HOME", str(link))
    monkeypatch.delenv("MEMEX_HOME_ALLOW_UNUSUAL", raising=False)
    with pytest.raises(MemexHomeInvalidError):
        memex_home()


def test_memex_home_rejects_symlinked_default(monkeypatch, tmp_path):
    """~/.memex/ existing as a symlink in default branch → reject."""
    monkeypatch.delenv("MEMEX_HOME", raising=False)
    monkeypatch.delenv("MEMEX_HOME_ALLOW_UNUSUAL", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    real = tmp_path / "elsewhere"
    real.mkdir()
    link = tmp_path / ".memex"
    link.symlink_to(real)
    with pytest.raises(MemexHomeInvalidError, match="symlink"):
        memex_home()


def test_memex_home_allow_unusual(monkeypatch):
    monkeypatch.setenv("MEMEX_HOME", "/tmp/memex-allow-unusual-test")
    monkeypatch.setenv("MEMEX_HOME_ALLOW_UNUSUAL", "1")
    assert memex_home() == Path("/tmp/memex-allow-unusual-test").resolve()


def test_registry_does_not_require_bootstrap(tmp_memex_home):
    from scripts import registry

    assert registry.get_store("any") is None
    assert registry.list_stores() == []


def test_registry_does_not_call_require_bootstrap_via_mock_bomb(tmp_memex_home, monkeypatch):
    bomb = Mock(side_effect=AssertionError("require_bootstrap leaked into registry"))
    monkeypatch.setattr("scripts.db.require_bootstrap", bomb)
    from scripts import registry

    registry.get_store("x")
    registry.list_stores()
    bomb.assert_not_called()


def test_config_write_then_read(tmp_memex_home):
    from scripts.paths import PLUGIN_ROOT

    write_plugin_root_config(PLUGIN_ROOT)
    config = tmp_memex_home / "config.json"
    assert config.exists()
    assert json.loads(config.read_text())["plugin_root"] == str(PLUGIN_ROOT)
    assert read_plugin_root_config() == PLUGIN_ROOT


def test_config_read_missing_returns_none(tmp_memex_home):
    assert read_plugin_root_config() is None


def test_config_read_invalid_returns_none(tmp_memex_home):
    (tmp_memex_home / "config.json").write_text("not json")
    assert read_plugin_root_config() is None


def test_config_read_stale_path_returns_none(tmp_memex_home, tmp_path):
    (tmp_memex_home / "config.json").write_text(
        json.dumps({"plugin_root": str(tmp_path / "nonexistent")})
    )
    assert read_plugin_root_config() is None


def test_config_read_path_with_wrong_name_returns_none(tmp_memex_home, tmp_path):
    fake_plugin = tmp_path / "fake_plugin"
    (fake_plugin / "scripts").mkdir(parents=True)
    (fake_plugin / "scripts" / "install.py").write_text("# fake")
    (fake_plugin / ".claude-plugin").mkdir()
    (fake_plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "not-memex"}))
    (tmp_memex_home / "config.json").write_text(json.dumps({"plugin_root": str(fake_plugin)}))
    assert read_plugin_root_config() is None


def test_config_read_path_missing_install_py_returns_none(tmp_memex_home, tmp_path):
    """plugin_root must contain scripts/install.py — otherwise it's a stale or
    decoy path and we fall back to PLUGIN_ROOT discovery."""
    fake_plugin = tmp_path / "fake_plugin"
    fake_plugin.mkdir()
    (fake_plugin / ".claude-plugin").mkdir()
    (fake_plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "memex"}))
    # Deliberately omit scripts/install.py
    (tmp_memex_home / "config.json").write_text(json.dumps({"plugin_root": str(fake_plugin)}))
    assert read_plugin_root_config() is None
