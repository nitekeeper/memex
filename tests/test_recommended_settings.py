"""Hermetic tests for the settings-recommendation-on-upgrade feature.

M2 clean-runner discipline: every test uses the conftest `tmp_settings_path`
fixture (monkeypatched $CLAUDE_SETTINGS_PATH) and a monkeypatched
$MEMEX_SETTINGS_REC_STATE_PATH for the state marker — NONE of these touch the
real ~/.claude or ~/.memex.

Each anti-revert test is paired with the production behavior it guards: neuter
the behavior (e.g. make apply_recommended overwrite the whole dict, strip the
Step 0 wiring, or pin model to claude-sonnet-4-6) and the matching test goes
RED.

Run CI-faithfully via:
    HOME=$(mktemp -d) MEMEX_HOME_ALLOW_UNUSUAL=1 PYTHONPATH=. pytest tests/ -q
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import recommended_settings as rs


@pytest.fixture
def tmp_state_path(monkeypatch, tmp_path):
    """Hermetic per-version state marker path (no ~/.memex)."""
    target = tmp_path / "memex_home" / "settings_rec_state.json"
    monkeypatch.setenv("MEMEX_SETTINGS_REC_STATE_PATH", str(target))
    return target


# ---------------------------------------------------------------------------
# AI-1 / AI-2 — constant pin (sonnet alias, exact 3-key dict)
# ---------------------------------------------------------------------------


def test_recommended_constant_is_exact_sonnet_alias():
    """Anti-revert: RECOMMENDED must be exactly the 3-key cost-optimized dict
    with model as the FAMILY ALIAS 'sonnet'. Fails if pinned to a
    claude-sonnet-* id, or if any key is added/removed/retyped."""
    assert rs.RECOMMENDED == {
        "model": "sonnet",
        "effortLevel": "high",
        "autoCompactEnabled": True,
    }
    # Belt-and-braces: the alias must not have drifted to a pinned id.
    assert rs.RECOMMENDED["model"] == "sonnet"
    assert not str(rs.RECOMMENDED["model"]).startswith("claude-")
    assert set(rs.RECOMMENDED) == {"model", "effortLevel", "autoCompactEnabled"}
    assert rs.RECOMMENDED["autoCompactEnabled"] is True


# ---------------------------------------------------------------------------
# AI-1 — current_plugin_version via PLUGIN_ROOT
# ---------------------------------------------------------------------------


def test_current_plugin_version_reads_plugin_json():
    """Reads the real plugin.json via PLUGIN_ROOT and returns the version str,
    matching plugin.json:version exactly."""
    version = rs.current_plugin_version()
    assert isinstance(version, str)
    expected = json.loads(Path(".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    assert version == expected


def test_current_plugin_version_none_on_missing(monkeypatch, tmp_path):
    """Returns None (never raises) when the plugin.json is missing."""
    monkeypatch.setattr(rs, "PLUGIN_ROOT", tmp_path / "nonexistent")
    assert rs.current_plugin_version() is None


def test_current_plugin_version_none_on_malformed(monkeypatch, tmp_path):
    """Returns None (never raises) when plugin.json is malformed JSON."""
    root = tmp_path / "root"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(rs, "PLUGIN_ROOT", root)
    assert rs.current_plugin_version() is None


# ---------------------------------------------------------------------------
# AI-1 — load_settings graceful
# ---------------------------------------------------------------------------


def test_load_settings_empty_on_missing(tmp_settings_path):
    assert not tmp_settings_path.exists()
    assert rs.load_settings() == {}


def test_load_settings_empty_on_malformed(tmp_settings_path):
    tmp_settings_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_settings_path.write_text("{ broken json", encoding="utf-8")
    assert rs.load_settings() == {}


def test_load_settings_empty_on_non_dict(tmp_settings_path):
    tmp_settings_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_settings_path.write_text("[1, 2, 3]", encoding="utf-8")
    assert rs.load_settings() == {}


# ---------------------------------------------------------------------------
# AI-1 / AI-2 — compute_changes
# ---------------------------------------------------------------------------


def test_compute_changes_returns_only_recommended_keys():
    current = {"model": "opus", "env": {"FOO": "bar"}}
    changes = rs.compute_changes(current)
    # Only recommended keys, never the user's env key.
    assert set(changes) <= set(rs.RECOMMENDED)
    assert "env" not in changes
    # model differs -> included; effortLevel/autoCompactEnabled absent -> included.
    assert changes["model"] == "sonnet"
    assert changes["effortLevel"] == "high"
    assert changes["autoCompactEnabled"] is True


def test_compute_changes_empty_when_already_applied():
    current = dict(rs.RECOMMENDED)
    assert rs.compute_changes(current) == {}


def test_compute_changes_only_diff_keys():
    """Already-correct keys are omitted; only the genuinely-different one stays."""
    current = {"model": "sonnet", "effortLevel": "high", "autoCompactEnabled": False}
    changes = rs.compute_changes(current)
    assert changes == {"autoCompactEnabled": True}


# ---------------------------------------------------------------------------
# AI-1 — read_state / write_state atomic round-trip
# ---------------------------------------------------------------------------


def test_write_state_round_trip(tmp_state_path):
    rs.write_state("9.9.9", "declined")
    assert rs.read_state() == {"last_handled_version": "9.9.9", "decision": "declined"}


def test_read_state_empty_on_missing(tmp_state_path):
    assert not tmp_state_path.exists()
    assert rs.read_state() == {}


def test_read_state_empty_on_malformed(tmp_state_path):
    tmp_state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_state_path.write_text("nope", encoding="utf-8")
    assert rs.read_state() == {}


def test_write_state_rejects_unknown_decision(tmp_state_path):
    rs.write_state("9.9.9", "garbage")
    # Unknown decision is a no-op: nothing written.
    assert not tmp_state_path.exists()
    assert rs.read_state() == {}


def test_write_state_mkdir_parent(tmp_state_path):
    """Parent dir does not exist beforehand; write_state must create it."""
    assert not tmp_state_path.parent.exists()
    rs.write_state("1.2.3", "applied")
    assert tmp_state_path.exists()
    assert rs.read_state()["last_handled_version"] == "1.2.3"


# ---------------------------------------------------------------------------
# AI-1 — atomic-no-debris
# ---------------------------------------------------------------------------


def test_write_state_leaves_no_temp_debris(tmp_state_path):
    rs.write_state("1.0.0", "applied")
    siblings = list(tmp_state_path.parent.iterdir())
    # Only the state file itself — no leftover .tmp-*.json temp files.
    assert [p.name for p in siblings] == [tmp_state_path.name]


def test_apply_recommended_leaves_no_temp_debris(tmp_settings_path):
    rs.apply_recommended()
    siblings = list(tmp_settings_path.parent.iterdir())
    assert [p.name for p in siblings] == [tmp_settings_path.name]


# ---------------------------------------------------------------------------
# AI-2 — merge-safety
# ---------------------------------------------------------------------------


def test_apply_recommended_merge_safety(tmp_settings_path):
    """Anti-revert: seed a settings.json with non-recommended keys AND a
    pre-existing user model; after apply, every non-recommended key is
    byte-for-byte preserved and only the 3 recommended keys changed.

    Neutering apply_recommended to write `RECOMMENDED` (clobbering everything)
    makes this RED."""
    tmp_settings_path.parent.mkdir(parents=True, exist_ok=True)
    seed = {
        "model": "opus",  # user-chosen — must be overwritten to sonnet
        "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
        "enabledPlugins": ["memex", "atelier"],
        "permissions": {"allow": ["Bash(git:*)"]},
        "statusLine": {"type": "command", "command": "echo hi"},
        "hooks": {"PostToolUse": []},
    }
    tmp_settings_path.write_text(json.dumps(seed, indent=2), encoding="utf-8")

    changes = rs.apply_recommended()
    result = json.loads(tmp_settings_path.read_text(encoding="utf-8"))

    # Only the 3 recommended keys changed.
    assert changes == {"model": "sonnet", "effortLevel": "high", "autoCompactEnabled": True}
    assert result["model"] == "sonnet"
    assert result["effortLevel"] == "high"
    assert result["autoCompactEnabled"] is True
    # Every non-recommended key preserved byte-for-byte.
    assert result["env"] == seed["env"]
    assert result["enabledPlugins"] == seed["enabledPlugins"]
    assert result["permissions"] == seed["permissions"]
    assert result["statusLine"] == seed["statusLine"]
    assert result["hooks"] == seed["hooks"]


def test_apply_recommended_mkdir_parent(tmp_settings_path):
    """Parent .claude/ does not exist; apply must create it."""
    assert not tmp_settings_path.parent.exists()
    rs.apply_recommended()
    assert tmp_settings_path.exists()
    result = json.loads(tmp_settings_path.read_text(encoding="utf-8"))
    assert result["model"] == "sonnet"


def test_apply_recommended_from_empty(tmp_settings_path):
    """No settings file → creates one with exactly the 3 keys."""
    changes = rs.apply_recommended()
    assert changes == dict(rs.RECOMMENDED)
    result = json.loads(tmp_settings_path.read_text(encoding="utf-8"))
    assert result == dict(rs.RECOMMENDED)


def test_apply_never_writes_managed_settings(tmp_settings_path):
    """The feature must NEVER touch managed-settings.json."""
    rs.apply_recommended()
    managed = tmp_settings_path.parent / "managed-settings.json"
    assert not managed.exists()


# ---------------------------------------------------------------------------
# AI-2 — idempotency
# ---------------------------------------------------------------------------


def test_apply_recommended_idempotent(tmp_settings_path):
    """Second apply returns {} changes and the file content is byte-identical."""
    rs.apply_recommended()
    content_after_first = tmp_settings_path.read_text(encoding="utf-8")
    changes = rs.apply_recommended()
    assert changes == {}
    assert tmp_settings_path.read_text(encoding="utf-8") == content_after_first


# ---------------------------------------------------------------------------
# AI-2 — version-gating via eligibility
# ---------------------------------------------------------------------------


def test_eligibility_none_when_no_changes(tmp_settings_path, tmp_state_path):
    """When settings already satisfy the recommendation, no offer is due."""
    tmp_settings_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_settings_path.write_text(json.dumps(dict(rs.RECOMMENDED)), encoding="utf-8")
    assert rs.eligibility() is None


def test_eligibility_non_none_on_upgrade_with_changes(tmp_settings_path, tmp_state_path):
    """Fresh state + pending changes → eligible, carrying the current version."""
    e = rs.eligibility()
    assert e is not None
    assert e["eligible"] is True
    assert e["current_version"] == rs.current_plugin_version()
    assert e["changes"]  # non-empty


def test_eligibility_none_when_version_already_handled(tmp_settings_path, tmp_state_path):
    """Anti-revert for the per-version gate: a handled (declined OR applied)
    version must NOT re-offer. Removing the read_state gate makes this RED."""
    version = rs.current_plugin_version()
    rs.write_state(version, "declined")
    assert rs.eligibility() is None
    # Bumping the version (simulated) re-arms the offer.
    rs.write_state("0.0.1", "declined")
    assert rs.eligibility() is not None


def test_maybe_offer_is_eligibility_alias():
    assert rs.maybe_offer is rs.eligibility


# ---------------------------------------------------------------------------
# AI-1 — read-only-compute-never-writes
# ---------------------------------------------------------------------------


def test_read_only_paths_never_write(tmp_settings_path, tmp_state_path):
    """current_plugin_version / load_settings / compute_changes / eligibility
    must NOT create settings.json or the state file on disk."""
    assert not tmp_settings_path.exists()
    assert not tmp_state_path.exists()

    rs.current_plugin_version()
    rs.load_settings()
    rs.compute_changes(rs.load_settings())
    rs.read_state()
    rs.eligibility()

    assert not tmp_settings_path.exists(), "eligibility/compute path wrote settings.json"
    assert not tmp_state_path.exists(), "eligibility/compute path wrote state.json"


# ---------------------------------------------------------------------------
# AI-1 — graceful-on-malformed end to end
# ---------------------------------------------------------------------------


def test_eligibility_graceful_on_malformed_inputs(tmp_settings_path, tmp_state_path):
    """Planted malformed JSON in BOTH settings and state yields no exception."""
    tmp_settings_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_settings_path.write_text("not json", encoding="utf-8")
    tmp_state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_state_path.write_text("also not json", encoding="utf-8")
    # Malformed settings -> load_settings {} -> changes present -> eligible.
    e = rs.eligibility()
    assert e is None or e["eligible"] is True  # no exception either way


# ---------------------------------------------------------------------------
# AI-1 — CLI guard
# ---------------------------------------------------------------------------


def test_cli_status_and_apply(tmp_settings_path, tmp_state_path, capsys):
    """The __main__ CLI exposes status (read-only) and apply (mutating)."""
    rc = rs.main(["recommended_settings", "status"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out  # eligible on a fresh tmp settings file
    assert json.loads(out)["eligible"] is True

    rc = rs.main(["recommended_settings", "apply"])
    assert rc == 0
    applied = json.loads(capsys.readouterr().out.strip())
    assert applied["applied"]["model"] == "sonnet"
    assert tmp_settings_path.exists()
    # apply recorded state -> status is now empty (handled).
    rc = rs.main(["recommended_settings", "status"])
    assert capsys.readouterr().out.strip() == ""


def test_cli_bad_arg_returns_2(capsys):
    assert rs.main(["recommended_settings", "bogus"]) == 2


# ---------------------------------------------------------------------------
# AI-3 — consent SKILL presence + frontmatter + body references
# ---------------------------------------------------------------------------

_SKILL = Path("internal/core/settings-recommendation/SKILL.md")


def test_consent_skill_present():
    assert _SKILL.exists(), "Missing consent SKILL: internal/core/settings-recommendation"


def test_consent_skill_frontmatter_name():
    content = _SKILL.read_text(encoding="utf-8")
    assert "name: memex:core:settings-recommendation" in content


def test_consent_skill_body_references():
    """Anti-revert: the consent surface must reference the eligibility +
    apply functions, the default-NO y/N prompt, and the managed-settings
    caveat. Stripping the consent or flipping the default makes this RED."""
    content = _SKILL.read_text(encoding="utf-8")
    assert "scripts.recommended_settings" in content
    assert "eligibility" in content
    assert "apply_recommended" in content
    assert "(y/N)" in content  # default NO prompt
    assert "managed-settings.json" in content
    assert "M3" in content  # local-config / not-a-store distinction stated


# ---------------------------------------------------------------------------
# AI-4 — startup wiring anti-revert
# ---------------------------------------------------------------------------

_RUN_SKILL = Path("skills/run/SKILL.md")


def test_startup_wiring_references_module():
    content = _RUN_SKILL.read_text(encoding="utf-8")
    assert "scripts.recommended_settings" in content


def test_startup_wiring_references_consent_skill():
    content = _RUN_SKILL.read_text(encoding="utf-8")
    assert "internal/core/settings-recommendation/SKILL.md" in content


def test_startup_wiring_is_a_preflight_before_routing():
    """Anti-revert: the eligibility reference must appear BEFORE the first
    routing table header, so the offer is a Step-0 preflight, not buried after
    routing. Moving the wiring below routing (a silent unwiring) makes this RED."""
    content = _RUN_SKILL.read_text(encoding="utf-8")
    elig_idx = content.find("scripts.recommended_settings")
    routing_idx = content.find("## v2 Brain user-facing intent routing")
    assert elig_idx != -1, "Step 0 eligibility wiring missing from skills/run/SKILL.md"
    assert routing_idx != -1, "routing header missing from skills/run/SKILL.md"
    assert elig_idx < routing_idx, "eligibility wiring must precede the routing tables"


# ---------------------------------------------------------------------------
# AI-6 — CLAUDE.md doc-pin
# ---------------------------------------------------------------------------


def test_claude_md_documents_feature_with_m3_distinction():
    """Anti-revert: the Model-recommendations subsection must document the
    feature with the M3 LOCAL-config distinction, the sonnet alias, and the
    y/N default-NO consent framing. Dropping the M3 note or the advisory/consent
    framing makes this RED."""
    content = Path("CLAUDE.md").read_text(encoding="utf-8")
    # New subsection exists under Model recommendations.
    assert "Settings-recommendation-on-upgrade" in content
    # M3 distinction: settings.json is a LOCAL config, not a memex store.
    # \s+ tolerates the markdown line-wrap between words.
    assert re.search(r"LOCAL\s+Claude\s+Code\s+config", content)
    assert re.search(r"NOT\s+a\s+memex-managed\s+store", content)
    assert "M3" in content
    assert "does NOT apply" in content or "does not apply" in content
    # sonnet family alias + default-NO consent.
    assert "sonnet" in content
    assert "y/N" in content
    # advisory/consent framing.
    assert "advisory" in content
    # cites the implementation paths.
    assert "scripts/recommended_settings.py" in content
    assert "internal/core/settings-recommendation/SKILL.md" in content


# ---------------------------------------------------------------------------
# AI-7 — version agreement (defense-in-depth alongside test_version.py)
# ---------------------------------------------------------------------------


def test_plugin_json_and_pyproject_versions_agree():
    """Re-assert plugin.json:version == pyproject.toml:version so a feature-cycle
    bump can't drift them (defense-in-depth alongside tests/test_version.py)."""
    pj = json.loads(Path(".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    py_content = Path("pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', py_content, re.MULTILINE)
    assert m, "pyproject.toml has no top-level version field"
    assert pj == m.group(1), f"version drift: plugin.json={pj!r} pyproject={m.group(1)!r}"
