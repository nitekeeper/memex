import pathlib
import frontmatter as fm

SKILL_MD = pathlib.Path(__file__).parent.parent / "internal" / "upgrade" / "SKILL.md"
REFERENCE_MD = pathlib.Path(__file__).parent.parent / "internal" / "upgrade" / "REFERENCE.md"


def test_skill_md_exists():
    """internal/upgrade/SKILL.md must exist."""
    assert SKILL_MD.exists(), "internal/upgrade/SKILL.md must exist"


def test_skill_md_under_150_lines():
    """SKILL.md must stay ≤150 lines."""
    assert SKILL_MD.exists(), "internal/upgrade/SKILL.md must exist"
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
    """internal/upgrade/REFERENCE.md must exist."""
    assert REFERENCE_MD.exists(), "internal/upgrade/REFERENCE.md must exist"


def test_skill_has_version_detection():
    """SKILL.md must reference MANIFEST for version detection."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "MANIFEST" in body, "SKILL.md must reference MANIFEST.md for version detection"


def test_skill_has_approval_gate():
    """SKILL.md must require explicit user approval before making changes."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "yes" in body.lower() and ("cancel" in body.lower() or "confirm" in body.lower()), \
        "SKILL.md must include a yes/cancel approval gate"


def test_skill_has_migration_step():
    """SKILL.md must address schema migration handling."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "migrat" in body.lower(), "SKILL.md must mention migration handling"


def test_skill_has_rebuild_step():
    """SKILL.md must include a DB rebuild step after upgrade."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "rebuild" in body.lower(), "SKILL.md must include a rebuild step"


def test_skill_references_memex_dir():
    """SKILL.md must reference memex_dir config input."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "memex_dir" in body, "SKILL.md must reference memex_dir input"


def test_skill_references_memex_path():
    """SKILL.md must reference memex_path config input."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "memex_path" in body, "SKILL.md must reference memex_path input"
