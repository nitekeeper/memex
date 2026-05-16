import json
from pathlib import Path
import re


def test_pyproject_version_is_0_2_0():
    content = Path("pyproject.toml").read_text()
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    assert match
    assert match.group(1) == "0.2.0"


def test_plugin_json_version_is_0_2_0():
    data = json.loads(Path("plugin.json").read_text())
    assert data["version"] == "0.2.0"
