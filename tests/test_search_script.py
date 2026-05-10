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
    assert isinstance(data["results"][0]["score"], float)
    assert data["results"][0]["score"] < 0


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


def test_bm25_ranking(wiki):
    ai_dir, wiki_dir = wiki
    _write_page(wiki_dir, "exact", "Expiry handling",
                "token expiry token expiry token expiry token expiry token expiry")
    _write_page(wiki_dir, "vague", "Session management",
                "Mentions token expiry once in passing")
    _build_db(ai_dir)

    result = _run_search(ai_dir, "token expiry")
    assert result.returncode == 0
    data = _parse_result(result)
    assert len(data["results"]) == 2
    assert data["results"][0]["id"] == "test:wiki:exact"
    scores = [r["score"] for r in data["results"]]
    assert scores[0] < scores[1]  # BM25 is negative; more relevant = more negative


def test_snippet_extraction(wiki):
    ai_dir, wiki_dir = wiki
    _write_page(wiki_dir, "auth", "Auth design", "We handle token expiry by refreshing the session automatically.")
    _build_db(ai_dir)

    result = _run_search(ai_dir, "token expiry")
    assert result.returncode == 0
    data = _parse_result(result)
    snippet = data["results"][0]["snippet"]
    assert "[token]" in snippet or "[expiry]" in snippet
    # Verify surrounding context exists — snippet should contain more than just the bracket
    assert any(word in snippet for word in ["handle", "refreshing", "session", "automatically"])


def test_status_filter(wiki):
    ai_dir, wiki_dir = wiki
    _write_page(wiki_dir, "approved-page", "approved page", "content about widgets", status="approved")
    _write_page(wiki_dir, "draft-page", "draft page", "content about widgets", status="draft")
    _build_db(ai_dir)

    result = _run_search(ai_dir, "widgets", "--status", "approved")
    assert result.returncode == 0
    data = _parse_result(result)
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == "test:wiki:approved-page"
    assert data["results"][0]["status"] == "approved"


def test_tags_filter(wiki):
    ai_dir, wiki_dir = wiki
    _write_page(wiki_dir, "auth", "auth page", "content about security", tags=["auth", "security"])
    _write_page(wiki_dir, "db", "db page", "content about security", tags=["database"])
    _build_db(ai_dir)

    result = _run_search(ai_dir, "security", "--tag", "auth")
    assert result.returncode == 0
    data = _parse_result(result)
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == "test:wiki:auth"


def test_limit(wiki):
    ai_dir, wiki_dir = wiki
    for i in range(5):
        _write_page(wiki_dir, f"page{i}", f"page {i}", "searchable content here")
    _build_db(ai_dir)

    result = _run_search(ai_dir, "searchable", "--limit", "3")
    assert result.returncode == 0
    data = _parse_result(result)
    assert len(data["results"]) == 3
    assert all(r["id"].startswith("test:wiki:page") for r in data["results"])


def test_skill_md_under_100_lines():
    with open(SKILL_MD, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) <= 100, f"SKILL.md is {len(lines)} lines — must be ≤100"


def test_skill_description_under_1024_chars():
    post = fm.load(SKILL_MD)
    desc = str(post.metadata.get("description", ""))
    assert len(desc) > 0, "description field is empty"
    assert len(desc) <= 1024, f"description is {len(desc)} chars — must be ≤1024"
