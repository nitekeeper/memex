from pathlib import Path


def test_packaging_doc_exists():
    assert Path("docs/PACKAGING.md").exists()


def test_packaging_doc_mentions_single_skill_model():
    content = Path("docs/PACKAGING.md").read_text(encoding="utf-8")
    assert "memex:run" in content
    assert "internal/" in content


def test_packaging_doc_lists_install_flow():
    content = Path("docs/PACKAGING.md").read_text(encoding="utf-8").lower()
    assert "install" in content
    assert "v0.2.0" in content.lower() or "0.2.0" in content
