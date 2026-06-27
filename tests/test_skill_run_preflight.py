"""SKILL.md Step 0 preflight markers (presence-only, scoped to Step 0 region).

These assertions are xfail-strict until T23 inserts the Step 0 block.
Once Step 0 lands, the xfail marker is removed in T23 Step 2.
"""

from __future__ import annotations

from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "run" / "SKILL.md"
STEP0_PATH = Path(__file__).resolve().parent.parent / "skills" / "run" / "STEP0.md"


_H2_STEP0 = "\n## Step 0 "
_H2_NEXT = "\n## "


def _step0_file() -> str:
    """Return the full text of skills/run/STEP0.md (the lazy-loaded Step 0
    cold-path detail doc)."""
    return STEP0_PATH.read_text(encoding="utf-8")


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


def test_step0_cold_path_doc_exists():
    """The lazy-loaded cold-path detail doc must exist, and the always-loaded
    Step 0 region must point to it."""
    assert STEP0_PATH.exists(), "skills/run/STEP0.md missing"
    assert "STEP0.md" in _step_0_region(), "Step 0 region must reference STEP0.md"


def test_step0_doc_has_no_skill_frontmatter():
    """STEP0.md is a plain data doc — it must NOT register as a 2nd skill."""
    text = _step0_file()
    assert "name:" not in text
    assert "description:" not in text


def test_strict_y_n_via_stdin():
    doc = _step0_file()
    assert "(y/n)" in doc
    # Consent piped to install.py via stdin (Python-deterministic gate)
    assert 'echo "y"' in doc


def test_install_invocation_uses_pythonpath_not_cd():
    doc = _step0_file()
    assert "PYTHONPATH=" in doc, "install invocation should use PYTHONPATH=<plugin_root>"


def test_platform_install_blocks():
    doc = _step0_file().lower()
    assert "apt" in doc
    assert "brew" in doc
    assert "winget" in doc


def test_two_blocks_for_v1():
    doc = _step0_file()
    # Block A (with v1) and Block B (without v1) both present.
    assert "Block A" in doc or "v1 install" in doc.lower()
    assert "HAS_V1" in doc or "test -d" in doc
