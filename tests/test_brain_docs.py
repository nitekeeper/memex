from pathlib import Path


def test_brain_doc_exists():
    assert Path("docs/BRAIN.md").exists()


def test_brain_doc_lists_skills():
    content = Path("docs/BRAIN.md").read_text(encoding="utf-8")
    for s in ["ingest", "ask", "capture", "lint", "synthesize"]:
        assert s in content


def test_brain_doc_references_internal_paths():
    """Plan 3 docs must reference internal/brain/ per spec §8.0."""
    content = Path("docs/BRAIN.md").read_text(encoding="utf-8")
    assert "internal/brain" in content
    assert "memex:run" in content
