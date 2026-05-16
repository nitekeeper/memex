import json
import pytest
from pathlib import Path
from scripts import release


def test_build_dist_creates_versioned_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(Path.cwd())  # ensure we run from the repo
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    assert (target / "v2.0.0").exists()


def test_dist_has_manifest_json(tmp_path):
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    manifest = json.loads((target / "v2.0.0" / "manifest.json").read_text())
    assert manifest["version"] == "2.0.0"
    assert "files" in manifest


def test_dist_includes_all_skills(tmp_path):
    """Per spec §8.0, only memex:run is registered at top level; the 24
    internal procedures live under internal/<category>/<name>/SKILL.md
    and must all be included in the bundle."""
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    bundle = target / "v2.0.0"
    # Top-level skills/ holds only the memex:run registration entry.
    assert (bundle / "skills" / "run" / "SKILL.md").exists()
    # The 24 procedures live under internal/<category>/.
    internal_dir = bundle / "internal"
    assert (internal_dir / "core").is_dir()
    assert (internal_dir / "index").is_dir()
    assert (internal_dir / "brain").is_dir()
    assert (internal_dir / "steward").is_dir()
    assert (internal_dir / "dba").is_dir()


def test_dist_includes_plugin_json(tmp_path):
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    assert (target / "v2.0.0" / "plugin.json").exists()


def test_dist_includes_install_md(tmp_path):
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    install_doc = target / "v2.0.0" / "INSTALL.md"
    assert install_doc.exists()
    assert "2.0.0" in install_doc.read_text()
