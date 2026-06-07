from pathlib import Path

CORE_SKILLS = [
    "create-store",
    "migrate",
    "query",
    "insert",
    "update",
    "delete",
    "list-stores",
    "register-role",
    "register-agent",
    "get-agent",
]


def test_all_core_skills_present():
    """Core CRUD skills live under internal/ — agent-only, not registered
    in plugin.json. They are reachable via the memex:run routing skill."""
    for skill in CORE_SKILLS:
        p = Path(f"internal/core/{skill}/SKILL.md")
        assert p.exists(), f"Missing skill: {skill}"


def test_all_core_skills_have_frontmatter_name():
    for skill in CORE_SKILLS:
        content = Path(f"internal/core/{skill}/SKILL.md").read_text()
        expected_name = f"name: memex:core:{skill}"
        assert expected_name in content, f"Skill {skill} missing correct frontmatter name"


def test_all_core_skills_have_description():
    for skill in CORE_SKILLS:
        content = Path(f"internal/core/{skill}/SKILL.md").read_text()
        assert "description:" in content


def test_run_skill_routes_to_core_skills():
    """memex:run must contain routing entries for every internal core skill,
    so agents can discover them without Claude Code auto-loading their
    descriptions."""
    run_content = Path("skills/run/SKILL.md").read_text(encoding="utf-8")
    for skill in CORE_SKILLS:
        assert f"internal/core/{skill}/SKILL.md" in run_content, (
            f"memex:run missing routing entry for internal/core/{skill}"
        )


INDEX_SKILLS = ["write", "search", "archive"]
STEWARD_SKILLS = ["audit", "audit-store", "reconcile-orphan"]
DBA_SKILLS = ["checkpoint", "integrity-check", "vacuum"]


def test_index_skills_present():
    for s in INDEX_SKILLS:
        p = Path(f"internal/index/{s}/SKILL.md")
        assert p.exists(), f"Missing skill: index/{s}"


def test_index_skills_have_frontmatter_name():
    for s in INDEX_SKILLS:
        content = Path(f"internal/index/{s}/SKILL.md").read_text(encoding="utf-8")
        assert f"name: memex:index:{s}" in content


def test_steward_skills_present():
    for s in STEWARD_SKILLS:
        p = Path(f"internal/steward/{s}/SKILL.md")
        assert p.exists()


def test_dba_skills_present():
    for s in DBA_SKILLS:
        p = Path(f"internal/dba/{s}/SKILL.md")
        assert p.exists()


def test_run_skill_routes_to_index_steward_dba_skills():
    """memex:run must contain routing entries for every Plan 2 internal
    procedure (index, steward, dba), so agents can discover them without
    Claude Code auto-loading their descriptions."""
    run_content = Path("skills/run/SKILL.md").read_text(encoding="utf-8")
    for s in INDEX_SKILLS:
        assert f"internal/index/{s}/SKILL.md" in run_content, (
            f"memex:run missing routing entry for internal/index/{s}"
        )
    for s in STEWARD_SKILLS:
        assert f"internal/steward/{s}/SKILL.md" in run_content, (
            f"memex:run missing routing entry for internal/steward/{s}"
        )
    for s in DBA_SKILLS:
        assert f"internal/dba/{s}/SKILL.md" in run_content, (
            f"memex:run missing routing entry for internal/dba/{s}"
        )


BRAIN_SKILLS = ["ingest", "ask", "capture", "lint", "synthesize"]


def test_brain_skills_present():
    for s in BRAIN_SKILLS:
        p = Path(f"internal/brain/{s}/SKILL.md")
        assert p.exists(), f"Missing: brain/{s}"


def test_brain_skills_frontmatter():
    for s in BRAIN_SKILLS:
        content = Path(f"internal/brain/{s}/SKILL.md").read_text(encoding="utf-8")
        assert f"name: memex:brain:{s}" in content


# GraphRAG community layer (v2.7.0): these live under internal/brain/ but use
# hyphenated directory names, so they need their own list rather than the
# BRAIN_SKILLS frontmatter-name convention check.
GRAPHRAG_BRAIN_SKILLS = ["community-report", "graph-rebuild"]


def test_graphrag_brain_skills_present():
    for s in GRAPHRAG_BRAIN_SKILLS:
        p = Path(f"internal/brain/{s}/SKILL.md")
        assert p.exists(), f"Missing: brain/{s}"


def test_graphrag_brain_skills_frontmatter():
    for s in GRAPHRAG_BRAIN_SKILLS:
        content = Path(f"internal/brain/{s}/SKILL.md").read_text(encoding="utf-8")
        assert f"name: memex:brain:{s}" in content


def test_run_skill_routes_to_graphrag_brain_skills():
    run_content = Path("skills/run/SKILL.md").read_text(encoding="utf-8")
    for s in GRAPHRAG_BRAIN_SKILLS:
        assert f"internal/brain/{s}/SKILL.md" in run_content, (
            f"memex:run missing routing entry for internal/brain/{s}"
        )


EMBED_SKILLS = ["backfill", "reembed"]


def test_embed_skills_present():
    for s in EMBED_SKILLS:
        p = Path(f"internal/embed/{s}/SKILL.md")
        assert p.exists(), f"Missing: embed/{s}"


def test_embed_skills_frontmatter():
    for s in EMBED_SKILLS:
        content = Path(f"internal/embed/{s}/SKILL.md").read_text(encoding="utf-8")
        assert f"name: memex:embed:{s}" in content


def test_run_skill_routes_to_embed_skills():
    run_content = Path("skills/run/SKILL.md").read_text(encoding="utf-8")
    for s in EMBED_SKILLS:
        assert f"internal/embed/{s}/SKILL.md" in run_content, (
            f"memex:run missing routing entry for internal/embed/{s}"
        )


def test_run_skill_routes_to_brain_skills():
    run_content = Path("skills/run/SKILL.md").read_text(encoding="utf-8")
    for s in BRAIN_SKILLS:
        assert f"internal/brain/{s}/SKILL.md" in run_content, (
            f"memex:run missing routing entry for internal/brain/{s}"
        )


# Code-navigation graph layer (v2.9.0): non-hyphenated dirs under
# internal/codegraph/, so the standard frontmatter-name convention applies.
CODEGRAPH_SKILLS = ["ingest", "query"]


def test_codegraph_skills_present():
    for s in CODEGRAPH_SKILLS:
        p = Path(f"internal/codegraph/{s}/SKILL.md")
        assert p.exists(), f"Missing: codegraph/{s}"


def test_codegraph_skills_frontmatter():
    for s in CODEGRAPH_SKILLS:
        content = Path(f"internal/codegraph/{s}/SKILL.md").read_text(encoding="utf-8")
        assert f"name: memex:codegraph:{s}" in content


def test_run_skill_routes_to_codegraph_skills():
    run_content = Path("skills/run/SKILL.md").read_text(encoding="utf-8")
    for s in CODEGRAPH_SKILLS:
        assert f"internal/codegraph/{s}/SKILL.md" in run_content, (
            f"memex:run missing routing entry for internal/codegraph/{s}"
        )
