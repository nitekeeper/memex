import pathlib
import frontmatter as fm

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "review-wiki-output"
APPROVED_ENTRY = FIXTURES_DIR / ".ai" / "wiki" / "test-approved.md"
ARCHIVED_ENTRY = FIXTURES_DIR / ".ai" / "wiki" / "test-archived.md"
SKILL_MD = pathlib.Path(__file__).parent.parent / "skills" / "review-wiki" / "SKILL.md"
REFERENCE_MD = pathlib.Path(__file__).parent.parent / "skills" / "review-wiki" / "REFERENCE.md"


def test_skill_md_exists():
    """skills/review-wiki/SKILL.md must exist."""
    assert SKILL_MD.exists(), "skills/review-wiki/SKILL.md must exist"


def test_skill_md_under_150_lines():
    """SKILL.md must stay ≤150 lines."""
    assert SKILL_MD.exists(), "skills/review-wiki/SKILL.md must exist"
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
    """skills/review-wiki/REFERENCE.md must exist."""
    assert REFERENCE_MD.exists(), "skills/review-wiki/REFERENCE.md must exist"


def test_approved_fixture_parses():
    """Approved wiki fixture must parse with status=approved."""
    post = fm.load(str(APPROVED_ENTRY))
    assert post.metadata["status"] == "approved"
    assert post.metadata["id"], "id must be present"
    assert post.metadata["title"], "title must be present"


def test_archived_fixture_parses():
    """Archived wiki fixture must parse with status=archived and archived-reason."""
    post = fm.load(str(ARCHIVED_ENTRY))
    assert post.metadata["status"] == "archived"
    assert "archived-reason" in post.metadata, "archived entry must have archived-reason field"
    assert post.metadata["archived-reason"], "archived-reason must be non-empty"


def test_valid_status_values():
    """status must be one of draft/approved/archived."""
    valid = {"draft", "approved", "archived"}
    for path in [APPROVED_ENTRY, ARCHIVED_ENTRY]:
        post = fm.load(str(path))
        assert post.metadata["status"] in valid, \
            f"status must be draft/approved/archived, got {post.metadata['status']!r}"


def test_wiki_id_format():
    """id must follow <project>:wiki:<slug> for all fixtures."""
    for path in [APPROVED_ENTRY, ARCHIVED_ENTRY]:
        post = fm.load(str(path))
        parts = post.metadata["id"].split(":")
        assert len(parts) == 3, f"id must be <project>:wiki:<slug>, got {post.metadata['id']}"
        assert parts[1] == "wiki", f"id type must be 'wiki', got {parts[1]}"
