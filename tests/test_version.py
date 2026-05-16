"""Version sync test.

Per Claude Code docs (https://code.claude.com/docs/en/plugins-reference#version-management):
- Resolution priority is `.claude-plugin/plugin.json:version` FIRST, then marketplace,
  then git SHA.
- The version field is the cache-bust key — bumping it is the documented signal
  that users should receive a refreshed copy.

This test pins both pyproject.toml AND .claude-plugin/plugin.json to the same value,
ensuring they don't drift. Update both when cutting a release.
"""
import json
import re
from pathlib import Path


EXPECTED_VERSION = "2.0.0"


def test_pyproject_version():
    content = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    assert match
    assert match.group(1) == EXPECTED_VERSION


def test_canonical_manifest_version():
    """Canonical Claude Code manifest is at .claude-plugin/plugin.json — this is
    the file Claude Code reads to determine the cache-bust version."""
    data = json.loads(Path(".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert data["version"] == EXPECTED_VERSION
