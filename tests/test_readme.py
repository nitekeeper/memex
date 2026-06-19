from pathlib import Path


def test_readme_mentions_three_layers():
    content = Path("README.md").read_text(encoding="utf-8").lower()
    assert "brain" in content
    assert "index" in content
    assert "core" in content


def test_readme_mentions_internal_agents():
    content = Path("README.md").read_text(encoding="utf-8")
    for agent in ["Librarian", "Reference Librarian", "Archivist"]:
        assert agent in content


def test_readme_mentions_single_skill_registration():
    """Memex registers only `memex:run` with Claude Code; the README must
    call this out so consumers and developers understand the routing model."""
    content = Path("README.md").read_text(encoding="utf-8")
    assert "memex:run" in content
    assert "30 internal procedures" in content or "30 procedures" in content


def test_readme_has_consumer_and_developer_install_sections():
    """The README must distinguish the two install paths so neither
    audience has to guess which steps apply to them."""
    content = Path("README.md").read_text(encoding="utf-8").lower()
    assert "for consumers" in content
    assert "for developers" in content


def test_readme_discloses_claude_code_origin():
    """Set expectations: most code in this repo is developed with AI assistance.
    Readers reviewing PRs should know."""
    content = Path("README.md").read_text(encoding="utf-8")
    assert "Claude Code" in content
