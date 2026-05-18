"""SKILL.md Step 0 preflight markers (presence-only, scoped to Step 0 region).

These assertions are xfail-strict until T23 inserts the Step 0 block.
Once Step 0 lands, the xfail marker is removed in T23 Step 2.
"""

from __future__ import annotations

from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "run" / "SKILL.md"


_H2_STEP0 = "\n## Step 0 "
_H2_NEXT = "\n## "


def _step_0_region() -> str:
    """Return the slice of SKILL.md starting at the unique H2 '## Step 0' heading
    and ending at the next H2 heading. Anchors on '\\n## Step 0 ' (newline + H2 +
    trailing space) so H3 subheadings like '### Step 0.1' do not match.
    """
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert text.count(_H2_STEP0) == 1, "Expected exactly one '## Step 0 ' H2 heading"
    after = text.split(_H2_STEP0, 1)[1]
    end = after.find(_H2_NEXT)
    region = after if end == -1 else after[:end]
    return "## Step 0 " + region


def test_step_0_heading_present():
    assert "## Step 0 " in _step_0_region()


def test_python_check_one_liner():
    region = _step_0_region()
    # Spec uses a loop over candidate interpreters: `for cmd in python3 ...; do
    # $cmd -c '...'`. Allow either the literal `python3 -c` form or the
    # loop form `$cmd -c`.
    assert "python3 -c" in region or "$cmd -c" in region
    assert "sys.version_info" in region
    assert "(3, 10)" in region
    # And the candidate list must include python3.
    assert "python3" in region


def test_initialization_check_paths():
    region = _step_0_region()
    for p in ("registry.json", "agents.db", "index.db", "article.db", "config.json"):
        assert p in region, f"Step 0 missing path check for {p}"


def test_strict_y_n_via_stdin():
    region = _step_0_region()
    assert "(y/n)" in region
    # Consent piped to install.py via stdin (Python-deterministic gate)
    assert 'echo "y"' in region


def test_install_invocation_uses_pythonpath_not_cd():
    region = _step_0_region()
    assert "PYTHONPATH=" in region, "install invocation should use PYTHONPATH=<plugin_root>"


def test_platform_install_blocks():
    region = _step_0_region().lower()
    assert "apt" in region
    assert "brew" in region
    assert "winget" in region


def test_two_blocks_for_v1():
    region = _step_0_region()
    # Block A (with v1) and Block B (without v1) both present.
    assert "Block A" in region or "v1 install" in region.lower()
    assert "HAS_V1" in region or "test -d" in region
