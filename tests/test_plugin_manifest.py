"""Tests for the canonical Claude Code plugin manifest at .claude-plugin/plugin.json.

Per https://code.claude.com/docs/en/plugins-reference, the manifest at
.claude-plugin/plugin.json is the ONLY location Claude Code reads. A root-level
plugin.json (if present) is ignored. The `version` field there is the cache-bust
key — Claude Code uses it to decide whether to refetch the plugin on update.

These tests verify the canonical manifest exists, parses, and stays in sync with
pyproject.toml. Skills registration is NOT in this manifest (Claude Code
auto-discovers skills/<name>/SKILL.md); tests for that live in
test_skills_present.py.
"""

import json
import re
from pathlib import Path

CANONICAL_MANIFEST = Path(".claude-plugin/plugin.json")


def test_plugin_manifest_exists_at_canonical_location():
    """Canonical location per Claude Code docs is .claude-plugin/plugin.json."""
    assert CANONICAL_MANIFEST.exists(), (
        f"Missing {CANONICAL_MANIFEST}. This is Claude Code's only documented "
        "manifest location; without it the plugin install records version='unknown'."
    )


def test_root_plugin_json_does_not_exist():
    """A root-level plugin.json is NOT read by Claude Code (per docs). Keep it out
    of the tree to avoid the bug where the two files drift in version."""
    assert not Path("plugin.json").exists(), (
        "Root-level plugin.json is ignored by Claude Code. Move metadata into "
        ".claude-plugin/plugin.json to keep a single source of truth."
    )


def test_plugin_manifest_is_valid_json():
    data = json.loads(CANONICAL_MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_plugin_manifest_required_name():
    """`name` is the only required field per the manifest schema."""
    data = json.loads(CANONICAL_MANIFEST.read_text(encoding="utf-8"))
    assert data.get("name") == "memex"


def test_plugin_manifest_version_matches_pyproject():
    """Claude Code uses .claude-plugin/plugin.json:version as the cache-bust key.
    It must match pyproject.toml or installs will drift."""
    manifest = json.loads(CANONICAL_MANIFEST.read_text(encoding="utf-8"))
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*"([^"]+)"', pyproject)
    assert match, "pyproject.toml is missing a version line"
    assert manifest.get("version") == match.group(1), (
        f"Version mismatch: manifest={manifest.get('version')!r} pyproject={match.group(1)!r}"
    )


def test_plugin_manifest_has_attribution_metadata():
    """Author/homepage/repository/license make the plugin a good citizen on
    marketplaces. None of these is required by Claude Code, but every other
    plugin on agora has them."""
    data = json.loads(CANONICAL_MANIFEST.read_text(encoding="utf-8"))
    assert data.get("author", {}).get("name"), "author.name missing"
    assert data.get("homepage"), "homepage missing"
    assert data.get("repository"), "repository missing"
    assert data.get("license"), "license missing"
