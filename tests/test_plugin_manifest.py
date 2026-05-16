import json
from pathlib import Path


def test_plugin_manifest_exists():
    assert Path("plugin.json").exists()


def test_plugin_manifest_is_valid_json():
    data = json.loads(Path("plugin.json").read_text())
    assert "name" in data
    assert "version" in data


def test_plugin_manifest_registers_only_memex_run():
    """To stay under Claude Code's 1% skill-description budget, only memex:run
    is registered as a top-level skill. All other operations are reachable
    via memex:run's routing table to internal/<category>/<skill>/SKILL.md."""
    data = json.loads(Path("plugin.json").read_text())
    skills = data.get("skills", [])
    skill_names = {s.get("name") for s in skills}
    assert skill_names == {"memex:run"}, (
        f"Expected only 'memex:run' registered; got {skill_names}"
    )


def test_plugin_manifest_run_path_correct():
    data = json.loads(Path("plugin.json").read_text())
    skills = data.get("skills", [])
    run = next((s for s in skills if s.get("name") == "memex:run"), None)
    assert run is not None
    assert run["path"] == "skills/run/SKILL.md"
