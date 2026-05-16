"""Version sync test.

Per Claude Code docs (https://code.claude.com/docs/en/plugins-reference#version-management):
- Resolution priority is `.claude-plugin/plugin.json:version` FIRST, then marketplace,
  then git SHA.
- The version field is the cache-bust key — bumping it is the documented signal
  that users should receive a refreshed copy.

`.claude-plugin/plugin.json` is the single source of truth. `pyproject.toml`
must agree. This test verifies the two files agree without pinning to a
constant — releases only touch the two manifests; this test stays untouched.

To check that `plugin.json:description` also reflects the same version, see
`test_plugin_description_matches_version`.
"""
import json
import re
from pathlib import Path


def _plugin_json_version() -> str:
    return json.loads(Path(".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]


def _pyproject_version() -> str:
    content = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    assert match, "pyproject.toml has no top-level version field"
    return match.group(1)


def test_pyproject_matches_plugin_json():
    """The canonical version lives in plugin.json (Claude Code reads it as
    the cache-bust key). pyproject.toml must agree."""
    py = _pyproject_version()
    pj = _plugin_json_version()
    assert py == pj, f"version drift: pyproject.toml={py!r} but plugin.json={pj!r}"


def test_plugin_description_matches_version():
    """The plugin.json description string embeds the version (e.g.
    'Memex v2.2.0 — ...'). Catch drift between the version field and the
    inline version in the description."""
    data = json.loads(Path(".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    version = data["version"]
    description = data["description"]
    assert f"v{version}" in description, (
        f"plugin.json description does not mention v{version!r}: {description!r}"
    )
