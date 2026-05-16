import json
from pathlib import Path


def test_plugin_manifest_exists():
    assert Path("plugin.json").exists()


def test_plugin_manifest_is_valid_json():
    data = json.loads(Path("plugin.json").read_text())
    assert "name" in data
    assert "version" in data


def test_plugin_manifest_lists_core_skills():
    data = json.loads(Path("plugin.json").read_text())
    skills = data.get("skills", [])
    skill_names = {s.get("name") for s in skills}
    for required in [
        "memex:core:create-store", "memex:core:migrate",
        "memex:core:query", "memex:core:insert",
        "memex:core:update", "memex:core:delete",
        "memex:core:list-stores", "memex:core:register-role",
        "memex:core:register-agent", "memex:core:get-agent",
    ]:
        assert required in skill_names, f"Missing skill in manifest: {required}"
