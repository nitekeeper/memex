import pathlib
import sqlite3
import frontmatter as fm

from scripts.rebuild import parse_page, rebuild

SCHEMA_PATH = str(pathlib.Path(__file__).parent.parent / "db" / "schema.sql")
FIXTURE_AI_DIR = str(
    pathlib.Path(__file__).parent / "fixtures" / "capture-output" / ".ai"
)
FIXTURE_PAGE = str(
    pathlib.Path(__file__).parent
    / "fixtures" / "capture-output" / ".ai" / "wiki" / "capture-design.md"
)
SKILL_MD = str(
    pathlib.Path(__file__).parent.parent / "internal" / "capture" / "SKILL.md"
)


def test_capture_output_parses_correctly():
    """A page the capture skill would produce must pass parse_page()."""
    page = parse_page(FIXTURE_PAGE)
    assert page["id"] == "memex:wiki:capture-design"
    assert page["title"] == "Capture skill design decisions"
    assert page["status"] == "draft"
    assert page["slug"] == "capture-design"
    assert page["project"] == "memex"
    assert page["tags"] == ["skill", "capture", "design"]
    assert page["synced_at_commit"] is None
    assert page["describes_files"] == []
    assert "capture" in page["body"]


def test_capture_output_rebuilds_cleanly(tmp_path):
    """A page the capture skill would produce must pass rebuild()."""
    db_path = str(tmp_path / "memex.db")
    rebuild(FIXTURE_AI_DIR, db_path, SCHEMA_PATH)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    assert count == 1
    row = conn.execute("SELECT * FROM pages").fetchone()
    assert row["id"] == "memex:wiki:capture-design"
    assert row["title"] == "Capture skill design decisions"
    conn.close()


def test_capture_skill_md_under_150_lines():
    """SKILL.md must stay ≤150 lines — grew to 125 lines through hardening review."""
    with open(SKILL_MD, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) <= 150, f"SKILL.md is {len(lines)} lines — must be ≤150"


def test_skill_description_under_1024_chars():
    """SKILL.md description field must stay ≤1024 chars per wiki:skill-file-structure."""
    post = fm.load(SKILL_MD)
    desc = str(post.metadata.get("description", ""))
    assert len(desc) > 0, "description field is empty"
    assert len(desc) <= 1024, f"description is {len(desc)} chars — must be ≤1024"
