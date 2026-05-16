from pathlib import Path


CORE_SKILLS = [
    "create-store", "migrate", "query", "insert", "update",
    "delete", "list-stores", "register-role", "register-agent", "get-agent",
]


def test_all_core_skills_present():
    for skill in CORE_SKILLS:
        p = Path(f"skills/core/{skill}/SKILL.md")
        assert p.exists(), f"Missing skill: {skill}"


def test_all_core_skills_have_frontmatter_name():
    for skill in CORE_SKILLS:
        content = Path(f"skills/core/{skill}/SKILL.md").read_text()
        expected_name = f"name: memex:core:{skill}"
        assert expected_name in content, f"Skill {skill} missing correct frontmatter name"


def test_all_core_skills_have_description():
    for skill in CORE_SKILLS:
        content = Path(f"skills/core/{skill}/SKILL.md").read_text()
        assert "description:" in content
