from pathlib import Path


CORE_SKILLS = [
    "create-store", "migrate", "query", "insert", "update",
    "delete", "list-stores", "register-role", "register-agent", "get-agent",
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
