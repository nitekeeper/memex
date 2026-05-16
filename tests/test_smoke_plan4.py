import pytest
from pathlib import Path
from scripts import install, release
from scripts.db import memex_home


def test_fresh_install_creates_all_components(tmp_memex_home):
    """Fresh install (no v1 to archive) should bootstrap cleanly."""
    install.run()
    # Plan 1
    assert (memex_home() / "agents.db").exists()
    # Plan 2
    assert (memex_home() / "index.db").exists()
    # Plan 3
    assert (memex_home() / "article.db").exists()
    # Plan 4 — legacy dir created lazily on first archive, not at install


def test_upgrade_from_v1_archives_then_installs_v2(tmp_memex_home, tmp_path, monkeypatch):
    """Upgrade flow: v1 -> archived -> v2 installed alongside."""
    v1 = tmp_path / "v1"
    v1.mkdir()
    (v1 / ".ai").mkdir()
    (v1 / ".ai" / "memex.db").write_text("v1 placeholder")
    (v1 / ".ai" / "wiki").mkdir()
    (v1 / ".ai" / "wiki" / "test-entry.md").write_text("# Test\n\nContent")
    monkeypatch.setenv("MEMEX_V1_PATH", str(v1))

    install.run()

    # v1 archived
    legacy = memex_home() / "legacy" / "v1-wiki"
    assert legacy.exists()
    assert (legacy / "wiki" / "test-entry.md").exists()

    # v2 fully installed
    assert (memex_home() / "agents.db").exists()
    assert (memex_home() / "index.db").exists()
    assert (memex_home() / "article.db").exists()


def test_release_bundle_builds(tmp_path):
    """Build a dist bundle in a temp dir and verify structure."""
    out = release.build(version="2.0.0", target_root=tmp_path / "dist")
    assert (out / "manifest.json").exists()
    assert (out / ".claude-plugin" / "plugin.json").exists()
    assert (out / "INSTALL.md").exists()
    # Top-level skills/ holds the memex:run registration entry.
    assert (out / "skills" / "run" / "SKILL.md").exists()
    # The 24 procedures live under internal/<category>/ (spec §8.0).
    assert (out / "internal" / "core").is_dir()
    assert (out / "internal" / "index").is_dir()
    assert (out / "internal" / "brain").is_dir()
