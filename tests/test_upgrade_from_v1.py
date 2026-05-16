import pytest
from pathlib import Path
from scripts import upgrade_from_v1
from scripts.db import memex_home


def test_detect_v1_returns_false_when_no_prior_install(tmp_memex_home, monkeypatch):
    monkeypatch.delenv("MEMEX_V1_PATH", raising=False)
    assert upgrade_from_v1.detect_v1_install() is None


def test_detect_v1_returns_path_when_v1_dir_present(tmp_memex_home, tmp_path, monkeypatch):
    v1_dir = tmp_path / "memex-v1"
    v1_dir.mkdir()
    (v1_dir / ".ai").mkdir()
    (v1_dir / ".ai" / "memex.db").write_text("v1 db placeholder")
    (v1_dir / ".ai" / "wiki").mkdir()
    monkeypatch.setenv("MEMEX_V1_PATH", str(v1_dir))

    result = upgrade_from_v1.detect_v1_install()
    assert result == v1_dir


def test_archive_v1_moves_content_to_legacy(tmp_memex_home, tmp_path, monkeypatch):
    v1_dir = tmp_path / "memex-v1"
    v1_dir.mkdir()
    (v1_dir / ".ai").mkdir()
    (v1_dir / ".ai" / "memex.db").write_text("v1 db")
    (v1_dir / ".ai" / "wiki").mkdir()
    (v1_dir / ".ai" / "wiki" / "test.md").write_text("wiki content")
    monkeypatch.setenv("MEMEX_V1_PATH", str(v1_dir))

    upgrade_from_v1.archive_v1()

    legacy = memex_home() / "legacy" / "v1-wiki"
    assert legacy.exists()
    assert (legacy / "memex.db").exists()
    assert (legacy / "wiki" / "test.md").exists()


def test_archive_v1_no_op_when_no_v1(tmp_memex_home, monkeypatch):
    monkeypatch.delenv("MEMEX_V1_PATH", raising=False)
    # Should not raise
    result = upgrade_from_v1.archive_v1()
    assert result is None


def test_upgrade_logs_to_changelog(tmp_memex_home, tmp_path, monkeypatch):
    v1_dir = tmp_path / "memex-v1"
    v1_dir.mkdir()
    (v1_dir / ".ai").mkdir()
    (v1_dir / ".ai" / "memex.db").write_text("v1")
    monkeypatch.setenv("MEMEX_V1_PATH", str(v1_dir))

    upgrade_from_v1.archive_v1()

    log_path = memex_home() / "legacy" / "upgrade-log.md"
    assert log_path.exists()
    assert "v1" in log_path.read_text()
