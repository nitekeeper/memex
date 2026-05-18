import json
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


def test_dist_includes_canonical_plugin_manifest(tmp_path):
    """Per Claude Code docs (plugins-reference), the canonical manifest is
    .claude-plugin/plugin.json (NOT a root-level plugin.json). The bundle
    must include this directory so `claude --plugin-dir <bundle>` works."""
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    assert (target / "v2.0.0" / ".claude-plugin" / "plugin.json").exists()
    # And confirm we did NOT regress by re-introducing a root plugin.json:
    assert not (target / "v2.0.0" / "plugin.json").exists()


def test_dist_includes_install_md(tmp_path):
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    install_doc = target / "v2.0.0" / "INSTALL.md"
    assert install_doc.exists()
    assert "2.0.0" in install_doc.read_text()


def test_install_md_uses_python3(tmp_path):
    """v2.5.0 §D: generated INSTALL.md must use `python3 -m scripts.install`,
    never the bare `python` form. Windows users on Python launcher can
    follow the documented `py -3` fallback elsewhere in the doc."""
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    install_md = (target / "v2.0.0" / "INSTALL.md").read_text()
    assert "python3 -m scripts.install" in install_md
    # Must not contain the bare-python form (we still allow `py -3` mentions,
    # which don't match this substring).
    assert "python -m scripts.install" not in install_md
