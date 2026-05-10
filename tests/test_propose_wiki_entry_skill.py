import pathlib
import frontmatter as fm

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "propose-wiki-entry-output"
WIKI_FROM_LESSON = FIXTURES_DIR / ".ai" / "wiki" / "test-from-lesson.md"
SKILL_MD = pathlib.Path(__file__).parent.parent / "skills" / "propose-wiki-entry" / "SKILL.md"
REFERENCE_MD = pathlib.Path(__file__).parent.parent / "skills" / "propose-wiki-entry" / "REFERENCE.md"


def test_skill_md_exists():
    """skills/propose-wiki-entry/SKILL.md must exist."""
    assert SKILL_MD.exists(), "skills/propose-wiki-entry/SKILL.md must exist"


def test_skill_md_under_150_lines():
    """SKILL.md must stay ≤150 lines."""
    assert SKILL_MD.exists(), "skills/propose-wiki-entry/SKILL.md must exist"
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
    """skills/propose-wiki-entry/REFERENCE.md must exist."""
    assert REFERENCE_MD.exists(), "skills/propose-wiki-entry/REFERENCE.md must exist"


def test_wiki_fixture_from_lesson_parses():
    """Wiki entry created from a promoted lesson must parse with required fields."""
    post = fm.load(str(WIKI_FROM_LESSON))
    assert post.metadata["id"], "id must be present"
    assert post.metadata["title"], "title must be present"
    assert post.metadata["status"] == "draft", "new wiki entry from lesson must start as draft"
    assert post.metadata["created"], "created must be present"
    assert post.metadata["updated"], "updated must be present"


def test_wiki_fixture_id_format():
    """id must follow <project>:wiki:<slug>."""
    post = fm.load(str(WIKI_FROM_LESSON))
    parts = post.metadata["id"].split(":")
    assert len(parts) == 3, f"id must be <project>:wiki:<slug>, got {post.metadata['id']}"
    assert parts[1] == "wiki", f"id type must be 'wiki', got {parts[1]}"


def test_wiki_fixture_status_is_draft():
    """Wiki entries proposed from lessons must start with status=draft."""
    post = fm.load(str(WIKI_FROM_LESSON))
    assert post.metadata["status"] == "draft"


def test_wiki_fixture_has_body():
    """Wiki entry created from a lesson must have non-empty body."""
    post = fm.load(str(WIKI_FROM_LESSON))
    assert post.content.strip(), "wiki body must not be empty"
