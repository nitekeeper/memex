import pathlib
import frontmatter as fm

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "review-lessons-output"
PROMOTED_LESSON = FIXTURES_DIR / "lessons" / "promoted" / "test-promoted.md"
DISCARDED_LESSON = FIXTURES_DIR / "lessons" / "inbox" / "test-discarded.md"
HELD_LESSON = FIXTURES_DIR / "lessons" / "inbox" / "test-held.md"
SKILL_MD = pathlib.Path(__file__).parent.parent / "skills" / "review-lessons" / "SKILL.md"
REFERENCE_MD = pathlib.Path(__file__).parent.parent / "skills" / "review-lessons" / "REFERENCE.md"


def test_skill_md_exists():
    """skills/review-lessons/SKILL.md must exist."""
    assert SKILL_MD.exists(), "skills/review-lessons/SKILL.md must exist"


def test_skill_md_under_150_lines():
    """SKILL.md must stay ≤150 lines."""
    assert SKILL_MD.exists(), "skills/review-lessons/SKILL.md must exist"
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
    """skills/review-lessons/REFERENCE.md must exist."""
    assert REFERENCE_MD.exists(), "skills/review-lessons/REFERENCE.md must exist"


def test_promoted_lesson_fixture_parses():
    """Promoted fixture must parse with status=promoted and correct stream."""
    post = fm.load(str(PROMOTED_LESSON))
    assert post.metadata["status"] == "promoted"
    assert post.metadata["stream"] in {"inbox", "feedback"}
    assert "Observation" in post.content


def test_discarded_lesson_fixture_parses():
    """Discarded fixture must parse with status=discarded and discard-reason."""
    post = fm.load(str(DISCARDED_LESSON))
    assert post.metadata["status"] == "discarded"
    assert "discard-reason" in post.metadata
    assert post.metadata["discard-reason"], "discard-reason must be non-empty"


def test_promoted_lesson_in_promoted_dir():
    """Promoted lessons must live under lessons/promoted/."""
    assert "promoted" in str(PROMOTED_LESSON), \
        "promoted lesson must reside in lessons/promoted/"


def test_lesson_id_format():
    """id must follow <project>:lesson:<slug>."""
    for path in [PROMOTED_LESSON, DISCARDED_LESSON]:
        post = fm.load(str(path))
        parts = post.metadata["id"].split(":")
        assert len(parts) == 3, f"id must be <project>:lesson:<slug>, got {post.metadata['id']}"
        assert parts[1] == "lesson", f"id type must be 'lesson', got {parts[1]}"


def test_valid_status_values():
    """status field must be one of draft/promoted/discarded."""
    valid = {"draft", "promoted", "discarded"}
    for path in [PROMOTED_LESSON, DISCARDED_LESSON]:
        post = fm.load(str(path))
        assert post.metadata["status"] in valid, \
            f"status must be draft/promoted/discarded, got {post.metadata['status']!r}"


def test_promoted_lesson_body_has_required_sections():
    """Promoted lesson body must retain all three required sections."""
    post = fm.load(str(PROMOTED_LESSON))
    assert "Observation" in post.content
    assert "Why it matters" in post.content
    assert "How to apply" in post.content


def test_held_lesson_fixture_parses():
    """Held fixture must parse with held-for-review=true and valid held-reason."""
    post = fm.load(str(HELD_LESSON))
    assert post.metadata.get("held-for-review") is True, "held-for-review must be true"
    valid = {"contradiction", "philosophy", "confidence"}
    assert post.metadata.get("held-reason") in valid, \
        f"held-reason must be one of {valid}"
    assert post.metadata.get("status") == "draft"


def test_scan_order_held_before_regular():
    """SKILL.md must describe held items being reviewed before regular drafts."""
    with open(SKILL_MD, encoding="utf-8") as f:
        content = f.read()
    held_pos = content.find("held")
    regular_pos = content.find("regular")
    assert held_pos != -1, "SKILL.md must mention 'held'"
    assert regular_pos != -1, "SKILL.md must mention 'regular'"
    assert held_pos < regular_pos, \
        "SKILL.md must describe held items before regular drafts (scan order)"


def test_candidate_list_includes_held_tag():
    """SKILL.md must contain the [HELD: format tag for held items in the candidate list."""
    with open(SKILL_MD, encoding="utf-8") as f:
        content = f.read()
    assert "[HELD:" in content, "SKILL.md must contain '[HELD:' format tag for held items"


def test_review_block_held_marker_and_reason():
    """SKILL.md must contain [HELD: in the review block header and a Held reason: line."""
    with open(SKILL_MD, encoding="utf-8") as f:
        content = f.read()
    assert "[HELD:" in content, "SKILL.md must contain '[HELD:' in the review block"
    assert "Held reason:" in content, "SKILL.md must contain 'Held reason:' line"
