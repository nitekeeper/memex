from pathlib import Path


def test_index_doc_exists():
    assert Path("docs/INDEX.md").exists()


def test_index_doc_lists_internal_agents():
    content = Path("docs/INDEX.md").read_text(encoding="utf-8")
    for agent in ["Librarian", "Reference Librarian", "Archivist", "Database Administrator", "Data Steward"]:
        assert agent in content


def test_index_doc_references_internal_paths():
    """Plan 2 docs must reference internal/ paths per spec 8.0."""
    content = Path("docs/INDEX.md").read_text(encoding="utf-8")
    for path in ["internal/index", "internal/steward", "internal/dba"]:
        assert path in content
