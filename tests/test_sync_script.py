import json
import pathlib
import subprocess
import sys

import frontmatter as fm
import pytest

SYNC_SCRIPT = str(pathlib.Path(__file__).parent.parent / "scripts" / "sync.py")
SKILL_MD = str(pathlib.Path(__file__).parent.parent / "skills" / "sync" / "SKILL.md")


def _git(args, cwd):
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, check=True
    )


def _run_sync(ai_dir):
    return subprocess.run(
        [sys.executable, SYNC_SCRIPT, str(ai_dir)],
        capture_output=True,
        text=True,
    )


def _parse_report(result):
    """Parse sync.py JSON output; surfaces stdout+stderr on decode failure."""
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"sync.py stdout was not valid JSON.\n"
            f"stdout: {result.stdout!r}\n"
            f"stderr: {result.stderr!r}"
        ) from exc


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    ai_dir = repo / ".ai"
    wiki_dir = ai_dir / "wiki"
    wiki_dir.mkdir(parents=True)
    _git(["init"], cwd=repo)
    _git(["config", "user.email", "test@example.com"], cwd=repo)
    _git(["config", "user.name", "Test"], cwd=repo)
    return repo, ai_dir, wiki_dir


def test_stale_page_detected(git_repo):
    repo, ai_dir, wiki_dir = git_repo
    tracked = repo / "db" / "schema.sql"
    tracked.parent.mkdir()
    tracked.write_text("CREATE TABLE foo (id INTEGER);")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)
    sha_a = _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()

    page = wiki_dir / "db-schema.md"
    page.write_text(
        f"---\n"
        f"id: test:wiki:db-schema\n"
        f"title: DB Schema\n"
        f"status: draft\n"
        f"created: 2026-05-10\n"
        f"updated: 2026-05-10\n"
        f"describes-files:\n"
        f"  - db/schema.sql\n"
        f"synced-at-commit: {sha_a}\n"
        f"---\n\n"
        f"Describes the database schema.\n"
    )
    tracked.write_text(
        "CREATE TABLE foo (id INTEGER);\nCREATE TABLE bar (id INTEGER);"
    )
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "add page and modify schema"], cwd=repo)

    result = _run_sync(ai_dir)
    assert result.returncode == 0
    report = _parse_report(result)
    assert len(report["stale"]) == 1, f"Expected 1 stale entry, got: {report['stale']}"
    assert report["stale"][0]["state"] == "STALE"
    assert report["stale"][0]["id"] == "test:wiki:db-schema"
    assert len(report["stale"][0]["changed_files"]) == 1, (
        f"Expected 1 changed_files entry, got: {report['stale'][0]['changed_files']}"
    )
    assert report["stale"][0]["changed_files"][0]["diff"] is not None
    assert report["stale"][0]["changed_files"][0]["lines_changed"] > 0
    assert report["stale"][0]["changed_files"][0]["path"] == "db/schema.sql"


def test_never_synced_page_detected(git_repo):
    repo, ai_dir, wiki_dir = git_repo
    tracked = repo / "src" / "auth.py"
    tracked.parent.mkdir()
    tracked.write_text("def auth(): pass")
    page = wiki_dir / "auth-flow.md"
    page.write_text(
        "---\n"
        "id: test:wiki:auth-flow\n"
        "title: Auth Flow\n"
        "status: draft\n"
        "created: 2026-05-10\n"
        "updated: 2026-05-10\n"
        "describes-files:\n"
        "  - src/auth.py\n"
        "---\n\n"
        "Describes the auth flow.\n"
    )
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)

    result = _run_sync(ai_dir)
    assert result.returncode == 0
    report = _parse_report(result)
    assert len(report["stale"]) == 1, f"Expected 1 stale entry, got: {report['stale']}"
    assert report["stale"][0]["state"] == "NEVER_SYNCED"
    assert report["stale"][0]["synced_at_commit"] is None
    assert len(report["stale"][0]["changed_files"]) == 1, (
        "NEVER_SYNCED entry should have one changed_files entry per describes-files path"
    )
    assert report["stale"][0]["changed_files"][0]["diff"] is None
    assert report["stale"][0]["changed_files"][0]["lines_changed"] is None


def test_clean_page_not_stale(git_repo):
    repo, ai_dir, wiki_dir = git_repo
    tracked = repo / "db" / "schema.sql"
    tracked.parent.mkdir()
    tracked.write_text("CREATE TABLE foo (id INTEGER);")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)
    sha_a = _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()

    page = wiki_dir / "db-schema.md"
    page.write_text(
        f"---\n"
        f"id: test:wiki:db-schema\n"
        f"title: DB Schema\n"
        f"status: draft\n"
        f"created: 2026-05-10\n"
        f"updated: 2026-05-10\n"
        f"describes-files:\n"
        f"  - db/schema.sql\n"
        f"synced-at-commit: {sha_a}\n"
        f"---\n\n"
        f"Describes the database schema.\n"
    )
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "add wiki page"], cwd=repo)

    result = _run_sync(ai_dir)
    assert result.returncode == 0
    report = _parse_report(result)
    assert len(report["stale"]) == 0, f"Expected 0 stale entries, got: {report['stale']}"
    assert len(report["clean"]) == 1, f"Expected 1 clean entry, got: {report['clean']}"
    assert report["clean"][0]["state"] == "CLEAN"
    assert report["clean"][0]["id"] == "test:wiki:db-schema"
    assert report["clean"][0]["changed_files"] == [], (
        "CLEAN entry must have no changed_files"
    )


def test_untracked_page_ignored(git_repo):
    repo, ai_dir, wiki_dir = git_repo
    page = wiki_dir / "concept.md"
    page.write_text(
        "---\n"
        "id: test:wiki:concept\n"
        "title: A Concept\n"
        "status: draft\n"
        "created: 2026-05-10\n"
        "updated: 2026-05-10\n"
        "---\n\n"
        "A concept page with no file tracking.\n"
    )
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)

    result = _run_sync(ai_dir)
    assert result.returncode == 0
    report = _parse_report(result)
    assert len(report["stale"]) == 0, f"Expected 0 stale entries, got: {report['stale']}"
    assert len(report["clean"]) == 0, f"Expected 0 clean entries, got: {report['clean']}"
    assert len(report["untracked"]) == 1, f"Expected 1 untracked entry, got: {report['untracked']}"
    assert report["untracked"][0]["id"] == "test:wiki:concept"
    assert "state" not in report["untracked"][0], (
        "Untracked entries should not have a state field"
    )


def test_bad_ai_dir_exits_nonzero(tmp_path):
    result = _run_sync(tmp_path / "nonexistent" / ".ai")
    assert result.returncode != 0
    assert "not found" in result.stderr or "ai_dir" in result.stderr, (
        f"Expected an ai_dir error message in stderr, got: {result.stderr!r}"
    )


def test_unresolvable_sha_exits_nonzero(git_repo):
    repo, ai_dir, wiki_dir = git_repo
    tracked = repo / "db" / "schema.sql"
    tracked.parent.mkdir()
    tracked.write_text("CREATE TABLE foo (id INTEGER);")
    page = wiki_dir / "db-schema.md"
    page.write_text(
        "---\n"
        "id: test:wiki:db-schema\n"
        "title: DB Schema\n"
        "status: draft\n"
        "created: 2026-05-10\n"
        "updated: 2026-05-10\n"
        "describes-files:\n"
        "  - db/schema.sql\n"
        "synced-at-commit: deadbeefdeadbeefdeadbeef\n"
        "---\n\n"
        "Describes the database schema.\n"
    )
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)

    result = _run_sync(ai_dir)
    assert result.returncode != 0
    assert "deadbeefdeadbeefdeadbeef" in result.stderr


def test_skill_md_under_100_lines():
    with open(SKILL_MD, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) <= 100, f"SKILL.md is {len(lines)} lines — must be ≤100"


def test_skill_description_under_1024_chars():
    post = fm.load(SKILL_MD)
    desc = str(post.metadata.get("description", ""))
    assert len(desc) > 0, "description field is empty"
    assert len(desc) <= 1024, f"description is {len(desc)} chars — must be ≤1024"
