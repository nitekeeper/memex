from pathlib import Path


def test_user_guide_exists():
    assert Path("USER_GUIDE.md").exists()


def test_user_guide_covers_all_brain_skills():
    content = Path("USER_GUIDE.md").read_text(encoding="utf-8")
    for s in ["ingest", "ask", "capture", "lint", "synthesize"]:
        assert s in content


def test_user_guide_describes_onboarding():
    content = Path("USER_GUIDE.md").read_text(encoding="utf-8").lower()
    assert "onboarding" in content or "first invocation" in content


def test_user_guide_invocation_via_memex_run():
    """Per spec §8.0 the user invokes memex:run with intent, not memex:brain:* directly."""
    content = Path("USER_GUIDE.md").read_text(encoding="utf-8")
    assert "memex:run" in content
