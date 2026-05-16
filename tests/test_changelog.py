from pathlib import Path


def test_changelog_has_v0_2_0_section():
    content = Path("CHANGELOG.md").read_text(encoding="utf-8")
    assert "0.2.0" in content or "v0.2.0" in content


def test_changelog_mentions_breaking_changes():
    content = Path("CHANGELOG.md").read_text(encoding="utf-8").lower()
    assert "breaking" in content or "rewrite" in content or "redesign" in content


def test_changelog_mentions_single_skill_model():
    """v0.2's 'Single-skill registration model' is a load-bearing architectural call-out."""
    content = Path("CHANGELOG.md").read_text(encoding="utf-8")
    assert "memex:run" in content
