import pathlib
import frontmatter as fm

SKILL_MD = pathlib.Path(__file__).parent.parent / "skills" / "self-improve" / "SKILL.md"
REFERENCE_MD = pathlib.Path(__file__).parent.parent / "skills" / "self-improve" / "REFERENCE.md"
FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "self-improve-output"
HELD_LESSON = FIXTURES_DIR / "lessons" / "inbox" / "test-held.md"


def test_skill_md_exists():
    """skills/self-improve/SKILL.md must exist."""
    assert SKILL_MD.exists(), "skills/self-improve/SKILL.md must exist"


def test_skill_md_under_150_lines():
    """SKILL.md must stay ≤150 lines."""
    assert SKILL_MD.exists(), "skills/self-improve/SKILL.md must exist"
    with open(SKILL_MD, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) <= 150, f"SKILL.md is {len(lines)} lines — must be ≤150"


def test_skill_description_under_1024_chars():
    """SKILL.md description frontmatter must be ≤1024 chars."""
    post = fm.load(str(SKILL_MD))
    desc = str(post.metadata.get("description", ""))
    assert len(desc) > 0, "description field is empty"
    assert len(desc) <= 1024, f"description is {len(desc)} chars — must be ≤1024"


def test_reference_md_exists():
    """skills/self-improve/REFERENCE.md must exist."""
    assert REFERENCE_MD.exists(), "skills/self-improve/REFERENCE.md must exist"


def test_held_lesson_fixture_parses():
    """Held fixture must parse with held-for-review=true and valid held-reason."""
    post = fm.load(str(HELD_LESSON))
    assert post.metadata.get("held-for-review") is True, "held-for-review must be true"
    valid = {"contradiction", "philosophy", "confidence"}
    assert post.metadata.get("held-reason") in valid, \
        f"held-reason must be one of {valid}, got {post.metadata.get('held-reason')!r}"


def test_held_lesson_is_draft():
    """Held fixture must have status: draft."""
    post = fm.load(str(HELD_LESSON))
    assert post.metadata.get("status") == "draft", "held lesson must have status: draft"


def test_held_lesson_has_required_fields():
    """Held fixture must have all required lesson fields."""
    post = fm.load(str(HELD_LESSON))
    for field in ["id", "title", "stream", "status", "created"]:
        assert field in post.metadata, f"Missing required field: {field}"


def test_held_lesson_id_format():
    """id must follow <project>:lesson:<slug>."""
    post = fm.load(str(HELD_LESSON))
    parts = post.metadata["id"].split(":")
    assert len(parts) == 3, f"id must be <project>:lesson:<slug>, got {post.metadata['id']}"
    assert parts[1] == "lesson", f"id type must be 'lesson', got {parts[1]}"


def test_held_lesson_body_has_required_sections():
    """Held lesson body must have all three required sections."""
    post = fm.load(str(HELD_LESSON))
    assert "## Observation" in post.content
    assert "## Why it matters" in post.content
    assert "## How to apply" in post.content
