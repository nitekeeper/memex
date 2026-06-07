"""Anti-revert guard: every memex SKILL.md that dispatches an LLM subagent via
the Task tool MUST pin an explicit cheap model tier, so the dispatch never
silently inherits the orchestrator's expensive Opus default.

Pure-stdlib markdown-substring checks (pathlib + read_text), mirroring
tests/test_skills_present.py — no fixtures, no install state, runs under
`PYTHONPATH=. python3 -m pytest` on a clean tree.

The cost lever lives in the dispatching SKILL.md Task blocks (the orchestrating
Claude sets `model:` on the Agent/Task call) — memex has no Python model-tier
module, and a model-id buried in a Python helper the skill ignores would be
dead. These tests pin the lever where the dispatch actually happens.

WHY a markdown-substring check is the RIGHT test here (not "documentary-only"):
the production caller for the model tier IS the SKILL.md — memex's agent
harnesses only BUILD a `subagent_prompt` string; the orchestrating Claude reads
the SKILL.md recipe and issues the Agent/Task dispatch. There is no Python
dispatch wrapper to thread a `model=` arg through (contrast atelier's
`scripts/dispatch.py`, which spawns via `Agent(prompt=..., model=...)` and so
unit-tests the model param in Python). The Agent/Task tool's `model` parameter
is the canonical Claude Code per-dispatch tier mechanism (same field atelier's
`scripts/model_tier.py` emits into `Agent(model=...)`, same field a
`~/.claude/settings.json` per-skill `model` override targets). This guard pins
the directive's presence + tier at that production caller and FAILS on a silent
revert to Opus. It deliberately does NOT execute a live LLM dispatch: pytest
cannot spawn a real subagent nor assert which model an LLM actually ran on —
that belongs to a live smoke run, not unit CI. See CLAUDE.md "Dispatched-subagent
tiers (ENFORCED)" for the full rationale.
"""

from pathlib import Path

HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-4-6"

# Stale ids a future contributor might paste from muscle memory — banned.
STALE_MODEL_IDS = ["claude-3-5-haiku", "claude-3-5-sonnet"]

# Each dispatching SKILL.md -> the cheap-tier model id(s) that MUST appear in it.
# A file may require both tiers (e.g. ask: haiku for map/flat, sonnet for
# reduce/local). synthesize requires SONNET twice (Synthesizer + Librarian),
# but a substring-presence check on a tuple of required ids is enough to catch a
# strip-to-opus revert; an exact count guard for synthesize is added separately.
SITE_REQUIRED_MODELS = {
    "internal/brain/community-report/SKILL.md": (HAIKU,),
    "internal/brain/ask/SKILL.md": (HAIKU, SONNET),
    "internal/brain/synthesize/SKILL.md": (SONNET,),
    "internal/brain/ingest/SKILL.md": (SONNET,),
    "internal/brain/capture/SKILL.md": (SONNET,),
    "internal/index/write/SKILL.md": (SONNET,),
    "internal/index/search/SKILL.md": (HAIKU,),
}

# Files that legitimately carry MORE than one `model:` directive of a given tier.
# synthesize: Synthesizer (Step 2) + Librarian-classify (Step 4) -> SONNET x2.
EXACT_SONNET_COUNTS = {
    "internal/brain/synthesize/SKILL.md": 2,
}


def _read(rel_path: str) -> str:
    p = Path(rel_path)
    assert p.exists(), f"dispatch SKILL missing: {rel_path}"
    return p.read_text(encoding="utf-8")


def _normalize(content: str) -> str:
    """Strip markdown backticks so a backtick-wrapped bullet
    (`` `model`: `claude-haiku-4-5` ``) and an inline-prose directive
    (`model = claude-haiku-4-5`) both reduce to the canonical `model: <id>`
    form the SITE map asserts on. Backtick styling is cosmetic; the cost lever
    is the model id pinned next to a `model` key, however it is rendered."""
    no_ticks = content.replace("`", "")
    # Unify the two separator spellings used across the dispatch sites:
    # `model: <id>` (bullet form) and `model = <id>` (inline-pseudocode form).
    return no_ticks.replace("model = ", "model: ")


def _model_directives(content: str, model_id: str) -> int:
    return _normalize(content).count(f"model: {model_id}")


def test_no_dispatch_inherits_opus():
    """No dispatching SKILL may pin an Opus tier — that would re-introduce the
    silent-Opus-inheritance cost regression this cycle removed."""
    for rel_path in SITE_REQUIRED_MODELS:
        content = _normalize(_read(rel_path))
        assert "claude-opus" not in content, (
            f"{rel_path} pins an Opus model tier — the dispatch must request a "
            f"cheap tier (haiku/sonnet), never inherit/declare Opus."
        )


def test_each_dispatch_pins_cheap_tier():
    """Every named dispatch site declares its required cheap-tier `model:` line."""
    for rel_path, required in SITE_REQUIRED_MODELS.items():
        content = _read(rel_path)
        for model_id in required:
            assert _model_directives(content, model_id) >= 1, (
                f"{rel_path} missing required dispatch directive "
                f"'model: {model_id}' — the LLM subagent dispatch would "
                f"silently inherit Opus."
            )


def test_synthesize_pins_both_dispatches():
    """synthesize has TWO subagent dispatches (Synthesizer + Librarian); both
    must be pinned to sonnet — an exact count catches a half-revert that strips
    only one of the two `model:` lines."""
    for rel_path, expected in EXACT_SONNET_COUNTS.items():
        content = _read(rel_path)
        actual = _model_directives(content, SONNET)
        assert actual == expected, (
            f"{rel_path} should declare exactly {expected} 'model: {SONNET}' "
            f"directives (one per subagent dispatch), found {actual}."
        )


def test_no_stale_model_ids():
    """Guard against a contributor pasting a stale/wrong model id (e.g. the
    claude-3-5-* generation) into any dispatching SKILL."""
    for rel_path in SITE_REQUIRED_MODELS:
        content = _read(rel_path)
        for stale in STALE_MODEL_IDS:
            assert stale not in content, (
                f"{rel_path} references stale model id '{stale}' — use the "
                f"ecosystem-canonical ids {HAIKU} / {SONNET}."
            )


def test_claude_md_documents_enforced_tiers():
    """CLAUDE.md must document the dispatched-subagent tiers as ENFORCED (wired
    in SKILL.md model: lines + guarded by this test), not advisory — so a future
    advisory-downgrade of the per-dispatch cost floor is caught."""
    content = Path("CLAUDE.md").read_text(encoding="utf-8")
    assert "Dispatched-subagent tiers (ENFORCED)" in content, (
        "CLAUDE.md must carry the 'Dispatched-subagent tiers (ENFORCED)' "
        "subsection documenting the per-dispatch cost floor."
    )
    # The canonical ids must appear in that enforced documentation.
    assert HAIKU in content, f"CLAUDE.md must reference the canonical id {HAIKU}."
    assert SONNET in content, f"CLAUDE.md must reference the canonical id {SONNET}."
    # The enforced table must name the test that guards it.
    assert "tests/test_model_tier_dispatch.py" in content, (
        "CLAUDE.md enforced-tier subsection must cite its guarding test."
    )
