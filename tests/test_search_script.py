import json
import pathlib
import subprocess
import sys

import frontmatter as fm
import pytest

SEARCH_SCRIPT = str(pathlib.Path(__file__).parent.parent / "scripts" / "search.py")
REBUILD_SCRIPT = str(pathlib.Path(__file__).parent.parent / "scripts" / "rebuild.py")
SKILL_MD = str(pathlib.Path(__file__).parent.parent / "skills" / "ask" / "SKILL.md")


def _run_search(ai_dir, *args):
    return subprocess.run(
        [sys.executable, SEARCH_SCRIPT, str(ai_dir)] + list(args),
        capture_output=True,
        text=True,
    )


def _parse_result(result):
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"search.py stdout was not valid JSON.\n"
            f"stdout: {result.stdout!r}\n"
            f"stderr: {result.stderr!r}"
        ) from exc


def _write_page(wiki_dir, slug, title, body, status="approved", tags=None):
    tags_yaml = ""
    if tags:
        tags_yaml = "tags:\n" + "".join(f"  - {t}\n" for t in tags)
    content = (
        f"---\n"
        f"id: test:wiki:{slug}\n"
        f"title: {title}\n"
        f"status: {status}\n"
        f"created: 2026-05-10\n"
        f"updated: 2026-05-10\n"
        f"{tags_yaml}"
        f"---\n\n"
        f"{body}\n"
    )
    (wiki_dir / f"{slug}.md").write_text(content, encoding="utf-8")


def _build_db(ai_dir):
    subprocess.run(
        [sys.executable, REBUILD_SCRIPT, str(ai_dir)],
        capture_output=True, text=True, check=True,
    )


@pytest.fixture
def wiki(tmp_path):
    wiki_dir = tmp_path / ".ai" / "wiki"
    wiki_dir.mkdir(parents=True)
    return tmp_path / ".ai", wiki_dir


def test_basic_match(wiki):
    ai_dir, wiki_dir = wiki
    _write_page(wiki_dir, "auth", "Auth design", "Authentication flow using JWT tokens")
    _build_db(ai_dir)

    result = _run_search(ai_dir, "Authentication")
    assert result.returncode == 0
    data = _parse_result(result)
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == "test:wiki:auth"
    assert data["results"][0]["title"] == "Auth design"
    assert data["results"][0]["status"] == "approved"
    assert data["results"][0]["file_path"].endswith("auth.md")
    assert data["results"][0]["score"] is not None


def test_no_results(wiki):
    ai_dir, wiki_dir = wiki
    _write_page(wiki_dir, "auth", "Auth design", "Some content")
    _build_db(ai_dir)

    result = _run_search(ai_dir, "xyzzy_not_found_anywhere")
    assert result.returncode == 0
    data = _parse_result(result)
    assert data["results"] == []


def test_db_not_found(tmp_path):
    bad_ai_dir = tmp_path / "nonexistent" / ".ai"
    result = _run_search(bad_ai_dir, "query")
    assert result.returncode != 0
    assert "not found" in result.stderr.lower() or "DB" in result.stderr


def test_empty_query(wiki):
    ai_dir, wiki_dir = wiki
    _build_db(ai_dir)
    result = _run_search(ai_dir, "")
    assert result.returncode != 0
    assert result.stderr.strip() != ""
