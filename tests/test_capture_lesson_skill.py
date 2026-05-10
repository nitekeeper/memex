import pathlib
import frontmatter as fm

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "capture-lesson-output"
INBOX_LESSON = FIXTURES_DIR / "lessons" / "inbox" / "test-lesson.md"
FEEDBACK_LESSON = FIXTURES_DIR / "lessons" / "feedback" / "test-feedback.md"
SKILL_MD = pathlib.Path(__file__).parent.parent / "skills" / "capture-lesson" / "SKILL.md"
REFERENCE_MD = pathlib.Path(__file__).parent.parent / "skills" / "capture-lesson" / "REFERENCE.md"
LESSON_FORMAT_MD = pathlib.Path(__file__).parent.parent / "docs" / "LESSON_FORMAT.md"


def test_inbox_lesson_parses_correctly():
    """Inbox fixture must parse with correct id, stream, status, tags, and body."""
    post = fm.load(str(INBOX_LESSON))
    assert post.metadata["id"] == "memex:lesson:test-lesson"
    assert post.metadata["stream"] == "inbox"
    assert post.metadata["status"] == "draft"
    assert "test" in post.metadata["tags"]
    assert "Observation" in post.content


def test_feedback_lesson_parses_correctly():
    """Feedback fixture must parse with stream=feedback and required body sections."""
    post = fm.load(str(FEEDBACK_LESSON))
    assert post.metadata["id"] == "memex:lesson:test-feedback"
    assert post.metadata["stream"] == "feedback"
    assert post.metadata["status"] == "draft"
    assert "Observation" in post.content


def test_lesson_id_format():
    """id must follow <project>:lesson:<slug> with type='lesson'."""
    for path in [INBOX_LESSON, FEEDBACK_LESSON]:
        post = fm.load(str(path))
        parts = post.metadata["id"].split(":")
        assert len(parts) == 3, f"id must be <project>:lesson:<slug>, got {post.metadata['id']}"
        assert parts[1] == "lesson", f"id type must be 'lesson', got {parts[1]}"


def test_lesson_status_is_draft():
    """New lessons must always have status=draft."""
    for path in [INBOX_LESSON, FEEDBACK_LESSON]:
        post = fm.load(str(path))
        assert post.metadata["status"] == "draft"


def test_lesson_body_has_required_sections():
    """Body must contain all three required sections."""
    for path in [INBOX_LESSON, FEEDBACK_LESSON]:
        post = fm.load(str(path))
        assert "Observation" in post.content
        assert "Why it matters" in post.content
        assert "How to apply" in post.content


def test_skill_md_under_150_lines():
    """SKILL.md must stay ≤150 lines."""
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
    """skills/capture-lesson/REFERENCE.md must exist."""
    assert REFERENCE_MD.exists(), "skills/capture-lesson/REFERENCE.md must exist"


def test_lesson_format_doc_exists():
    """docs/LESSON_FORMAT.md must exist."""
    assert LESSON_FORMAT_MD.exists(), "docs/LESSON_FORMAT.md must exist"
