from pathlib import Path


def test_core_doc_exists():
    assert Path("docs/CORE.md").exists()


def test_core_doc_lists_acceptance_criteria():
    content = Path("docs/CORE.md").read_text()
    for required in [
        "create-store",
        "migrate",
        "query",
        "insert",
        "update",
        "delete",
        "register-role",
        "register-agent",
        "get-agent",
        "list-stores",
    ]:
        assert required in content, f"Doc missing reference to {required}"


def test_core_doc_explains_internal_layout():
    """Plan 1 docs must explain that Core skills live in internal/, not
    top-level, and that memex:run routes to them."""
    content = Path("docs/CORE.md").read_text()
    assert "internal/core" in content
    assert "memex:run" in content
    assert "1%" in content  # budget rationale present
