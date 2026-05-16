"""Tests for `scripts.bump` — one-command version bump.

The bump script operates on real files at the repo root (plugin.json,
pyproject.toml, dist/). To keep tests isolated, each test sets up a
temp-repo fixture and chdir's into it.
"""

import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """A minimal repo skeleton — just enough for scripts.bump to operate.

    Copies the real `.claude-plugin/`, `pyproject.toml`, `scripts/`,
    `skills/`, `internal/`, `db/`, `prompts/`, `README.md`, `USER_GUIDE.md`,
    `CHANGELOG.md` so `scripts.release.build()` succeeds inside the temp dir.
    Then chdir's into the temp root.
    """
    for d in [".claude-plugin", "scripts", "skills", "internal", "db", "prompts"]:
        src = REPO_ROOT / d
        if src.exists():
            shutil.copytree(
                src, tmp_path / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
    for f in ["pyproject.toml", "README.md", "USER_GUIDE.md", "CHANGELOG.md"]:
        src = REPO_ROOT / f
        if src.exists():
            shutil.copy2(src, tmp_path / f)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_bump_rewrites_plugin_json_version_and_description(tmp_repo):
    from scripts import bump

    result = bump.bump("9.9.9")
    data = json.loads(Path(".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert data["version"] == "9.9.9"
    assert "v9.9.9" in data["description"]
    # Old version no longer appears in description
    assert f"v{result['old']}" not in data["description"]


def test_bump_rewrites_pyproject_version(tmp_repo):
    from scripts import bump

    bump.bump("9.9.9")
    content = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "9.9.9"' in content


def test_bump_builds_new_dist_manifest(tmp_repo):
    from scripts import bump

    bump.bump("9.9.9")
    manifest = Path("dist/v9.9.9/manifest.json")
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["version"] == "9.9.9"


def test_bump_removes_previous_dist_manifest(tmp_repo):
    """Stage a fake old-version manifest, then bump and verify it's gone."""
    from scripts import bump

    current = json.loads(Path(".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    old_manifest = Path("dist") / f"v{current}" / "manifest.json"
    old_manifest.parent.mkdir(parents=True, exist_ok=True)
    old_manifest.write_text('{"version": "stub"}', encoding="utf-8")

    bump.bump("9.9.9")

    assert not old_manifest.exists()


def test_bump_refuses_to_downgrade(tmp_repo):
    from scripts import bump

    with pytest.raises(ValueError, match="not greater than"):
        bump.bump("0.0.1")


def test_bump_refuses_same_version(tmp_repo):
    from scripts import bump

    current = json.loads(Path(".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    with pytest.raises(ValueError, match="not greater than"):
        bump.bump(current)


def test_bump_rejects_malformed_version(tmp_repo):
    from scripts import bump

    for bad in ["v9.9.9", "9.9", "9.9.9-rc1", "abc", "9.9.9.9"]:
        with pytest.raises(ValueError, match=r"X\.Y\.Z"):
            bump.bump(bad)


def test_bump_main_returns_2_on_missing_arg(tmp_repo, capsys):
    from scripts import bump

    rc = bump.main(["scripts.bump"])
    assert rc == 2
    assert "usage:" in capsys.readouterr().err


def test_bump_main_returns_1_on_invalid_version(tmp_repo, capsys):
    from scripts import bump

    rc = bump.main(["scripts.bump", "not-a-version"])
    assert rc == 1
    assert "bump failed" in capsys.readouterr().err
