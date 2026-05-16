from pathlib import Path


def test_readme_mentions_v0_2():
    content = Path("README.md").read_text(encoding="utf-8")
    assert "0.2" in content


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
    """v0.2 registers only memex:run; README must call this out."""
    content = Path("README.md").read_text(encoding="utf-8")
    assert "memex:run" in content
    assert "24 internal procedures" in content or "24 procedures" in content
