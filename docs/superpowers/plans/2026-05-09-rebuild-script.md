# Memex Rebuild Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python script that reads all `.md` files from a project's `.ai/` directory and populates `.ai/memex.db` according to `db/schema.sql`.

**Architecture:** A single `scripts/rebuild.py` with four focused functions: `connect()` opens the DB with WAL+NORMAL safety and applies the schema; `parse_page()` reads a `.md` file and returns a structured dict; `load_page()` inserts a parsed page into all four normalized tables; `rebuild()` walks the directory, parses each page, and loads it. Each run wipes and recreates the DB — the DB is a derived artifact, never edited directly.

**Tech Stack:** Python 3.11+, `sqlite3` (stdlib), `python-frontmatter` 1.x for YAML frontmatter parsing, `pytest` 8.x for tests.

---

## Scope note

This is Plan 1 of 3 for the Memex build phase. Plans 2 and 3 cover the AI skills (`capture`, `sync`, `search`) which depend on the rebuild script being in place first.

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `scripts/rebuild.py` | Create | `connect()`, `parse_page()`, `load_page()`, `rebuild()`, CLI entry point |
| `scripts/requirements.txt` | Create | `python-frontmatter`, `pytest` |
| `tests/fixtures/sample/.ai/wiki/concept-page.md` | Create | Test fixture: minimal page, no describes-files |
| `tests/fixtures/sample/.ai/wiki/code-page.md` | Create | Test fixture: code-tracking page with all optional fields |
| `tests/test_rebuild.py` | Create | Unit + integration tests |
| `.gitignore` | Create/modify | Exclude `.ai/memex.db` (derived artifact) |

---

### Task 1: Project setup

**Files:**
- Create: `scripts/requirements.txt`
- Create: `tests/fixtures/sample/.ai/wiki/concept-page.md`
- Create: `tests/fixtures/sample/.ai/wiki/code-page.md`

- [ ] **Step 1: Create requirements.txt**

Create `scripts/requirements.txt`:
```
python-frontmatter==1.1.0
pytest==8.3.4
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r scripts/requirements.txt`
Expected: packages install without error.

- [ ] **Step 3: Create test fixtures**

Create `tests/fixtures/sample/.ai/wiki/concept-page.md`:
```markdown
---
id: sample:wiki:auth-design
title: Auth design decisions
status: draft
created: 2026-05-09
updated: 2026-05-09
tags: [auth, design]
---

This is the body of the auth design page.
```

Create `tests/fixtures/sample/.ai/wiki/code-page.md`:
```markdown
---
id: sample:wiki:db-schema
title: Database schema
status: approved
created: 2026-05-09
updated: 2026-05-09
slug: db-schema
synced-at-commit: f88c1c6
describes-files: ["db/schema.sql", "db/migrations/"]
tags: [database, schema]
related: [sample:wiki:auth-design]
---

This page describes the database schema.
```

- [ ] **Step 4: Commit**

```bash
git add scripts/requirements.txt tests/fixtures/
git commit -m "chore: add requirements and test fixtures for rebuild script"
```

---

### Task 2: DB connection and schema application

**Files:**
- Create: `scripts/rebuild.py` (initial skeleton)
- Create: `tests/conftest.py` (sys.path setup for all tests)
- Create: `tests/test_rebuild.py`

- [ ] **Step 1: Create conftest.py**

Create `tests/conftest.py` — ensures `scripts/` is on the Python path for all tests regardless of where pytest is invoked from:
```python
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
```

- [ ] **Step 2: Write failing test**

Create `tests/test_rebuild.py`:
```python
import os
import sqlite3
import pytest

from rebuild import connect

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")


def test_connect_creates_tables(tmp_path):
    db_path = str(tmp_path / "memex.db")
    conn = connect(db_path, SCHEMA_PATH)

    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "pages" in tables
    assert "links" in tables
    assert "page_files" in tables
    assert "page_tags" in tables
    conn.close()


def test_connect_sets_wal_mode(tmp_path):
    db_path = str(tmp_path / "memex.db")
    conn = connect(db_path, SCHEMA_PATH)

    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    conn.close()


def test_connect_wipes_existing_db(tmp_path):
    db_path = str(tmp_path / "memex.db")
    # First build
    conn = connect(db_path, SCHEMA_PATH)
    conn.execute("INSERT INTO pages (id, slug, project, title, status, body, file_path, created, updated) "
                 "VALUES ('x', 'x', 'x', 'x', 'draft', '', 'x.md', '2026-01-01', '2026-01-01')")
    conn.commit()
    conn.close()
    # Rebuild — should wipe and start fresh
    conn = connect(db_path, SCHEMA_PATH)
    count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    assert count == 0
    conn.close()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_rebuild.py -v`
Expected: `ModuleNotFoundError: No module named 'rebuild'`

- [ ] **Step 4: Write minimal implementation**

Create `scripts/rebuild.py`:
```python
import os
import sqlite3


def connect(db_path: str, schema_path: str) -> sqlite3.Connection:
    """Open (or recreate) memex.db with WAL safety and schema applied."""
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    with open(schema_path) as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    return conn
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_rebuild.py -v`
Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/rebuild.py tests/conftest.py tests/test_rebuild.py
git commit -m "feat: connect() opens memex.db with WAL safety and schema"
```

---

### Task 3: Frontmatter parser

**Files:**
- Modify: `scripts/rebuild.py`
- Modify: `tests/test_rebuild.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_rebuild.py`:
```python
import pathlib
from rebuild import parse_page

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "sample" / ".ai" / "wiki"


def test_parse_concept_page():
    page = parse_page(str(FIXTURES / "concept-page.md"))
    assert page["id"] == "sample:wiki:auth-design"
    assert page["title"] == "Auth design decisions"
    assert page["status"] == "draft"
    assert page["created"] == "2026-05-09"
    assert page["updated"] == "2026-05-09"
    assert page["slug"] == "concept-page"          # derived from filename stem
    assert page["project"] == "sample"              # extracted from id prefix
    assert page["synced_at_commit"] is None
    assert page["describes_files"] == []
    assert page["tags"] == ["auth", "design"]
    assert page["body"].strip() == "This is the body of the auth design page."
    assert page["file_path"].endswith("concept-page.md")


def test_parse_code_page():
    page = parse_page(str(FIXTURES / "code-page.md"))
    assert page["id"] == "sample:wiki:db-schema"
    assert page["slug"] == "db-schema"              # from frontmatter, not filename
    assert page["synced_at_commit"] == "f88c1c6"
    assert page["describes_files"] == ["db/schema.sql", "db/migrations/"]
    assert page["tags"] == ["database", "schema"]
    assert page["related"] == ["sample:wiki:auth-design"]


def test_parse_missing_id_returns_empty_id():
    # Files without an id field should return id='' so rebuild() can skip them
    import tempfile, textwrap
    content = textwrap.dedent("""\
        ---
        title: No ID page
        status: draft
        created: 2026-05-09
        updated: 2026-05-09
        ---
        Body text.
    """)
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write(content)
        tmp = f.name
    page = parse_page(tmp)
    assert page["id"] == ""
    os.unlink(tmp)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rebuild.py::test_parse_concept_page -v`
Expected: `ImportError: cannot import name 'parse_page'`

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/rebuild.py` (after the imports block):
```python
import frontmatter
import pathlib
from typing import Any


def parse_page(file_path: str) -> dict[str, Any]:
    """Read a .md file and return a structured dict for DB insertion."""
    post = frontmatter.load(file_path)
    meta = post.metadata
    stem = pathlib.Path(file_path).stem

    raw_id = str(meta.get("id", ""))
    project = raw_id.split(":")[0] if ":" in raw_id else ""

    return {
        "id": raw_id,
        "slug": str(meta.get("slug", stem)),
        "project": project,
        "title": str(meta.get("title", "")),
        "status": str(meta.get("status", "draft")),
        "synced_at_commit": meta.get("synced-at-commit"),
        "body": post.content,
        "file_path": file_path,
        "created": str(meta.get("created", "")),
        "updated": str(meta.get("updated", "")),
        "describes_files": list(meta.get("describes-files", [])),
        "tags": list(meta.get("tags", [])),
        "related": list(meta.get("related", [])),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rebuild.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/rebuild.py tests/test_rebuild.py
git commit -m "feat: parse_page() reads frontmatter and body from .md files"
```

---

### Task 4: Page loader (all four tables)

**Files:**
- Modify: `scripts/rebuild.py`
- Modify: `tests/test_rebuild.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_rebuild.py`:
```python
from rebuild import load_page


def test_load_concept_page(tmp_path):
    db_path = str(tmp_path / "memex.db")
    conn = connect(db_path, SCHEMA_PATH)
    page = parse_page(str(FIXTURES / "concept-page.md"))
    load_page(conn, page)
    conn.commit()

    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page["id"],)).fetchone()
    assert row is not None
    assert row["title"] == "Auth design decisions"
    assert row["status"] == "draft"
    assert row["synced_at_commit"] is None

    tags = sorted(r["tag"] for r in conn.execute(
        "SELECT tag FROM page_tags WHERE page_id = ?", (page["id"],)
    ))
    assert tags == ["auth", "design"]

    files = conn.execute(
        "SELECT * FROM page_files WHERE page_id = ?", (page["id"],)
    ).fetchall()
    assert files == []
    conn.close()


def test_load_code_page(tmp_path):
    db_path = str(tmp_path / "memex.db")
    conn = connect(db_path, SCHEMA_PATH)

    # Load concept page first (its id is the link target)
    concept = parse_page(str(FIXTURES / "concept-page.md"))
    load_page(conn, concept)

    page = parse_page(str(FIXTURES / "code-page.md"))
    load_page(conn, page)
    conn.commit()

    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page["id"],)).fetchone()
    assert row["synced_at_commit"] == "f88c1c6"

    files = sorted(
        r["file_path"] for r in conn.execute(
            "SELECT file_path FROM page_files WHERE page_id = ?", (page["id"],)
        )
    )
    assert files == ["db/migrations/", "db/schema.sql"]

    links = conn.execute(
        "SELECT to_id, rel_type FROM links WHERE from_id = ?", (page["id"],)
    ).fetchall()
    assert len(links) == 1
    assert links[0]["to_id"] == "sample:wiki:auth-design"
    assert links[0]["rel_type"] == "related"
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rebuild.py::test_load_concept_page -v`
Expected: `ImportError: cannot import name 'load_page'`

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/rebuild.py`:
```python
def load_page(conn: sqlite3.Connection, page: dict[str, Any]) -> None:
    """Insert a parsed page into all four normalized tables."""
    conn.execute(
        """INSERT INTO pages
           (id, slug, project, title, status, synced_at_commit,
            body, file_path, created, updated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            page["id"], page["slug"], page["project"], page["title"],
            page["status"], page["synced_at_commit"], page["body"],
            page["file_path"], page["created"], page["updated"],
        ),
    )
    for tag in page["tags"]:
        conn.execute(
            "INSERT INTO page_tags (page_id, tag) VALUES (?, ?)",
            (page["id"], tag),
        )
    for file_path in page["describes_files"]:
        conn.execute(
            "INSERT INTO page_files (page_id, file_path) VALUES (?, ?)",
            (page["id"], file_path),
        )
    for to_id in page["related"]:
        conn.execute(
            "INSERT INTO links (from_id, to_id, rel_type) VALUES (?, ?, ?)",
            (page["id"], to_id, "related"),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rebuild.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/rebuild.py tests/test_rebuild.py
git commit -m "feat: load_page() inserts page into all four normalized tables"
```

---

### Task 5: Rebuild orchestration and FTS population

**Files:**
- Modify: `scripts/rebuild.py`
- Modify: `tests/test_rebuild.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_rebuild.py`:
```python
from rebuild import rebuild

AI_DIR = str(FIXTURES.parent)  # tests/fixtures/sample/.ai/


def test_rebuild_populates_all_pages(tmp_path):
    db_path = str(tmp_path / "memex.db")
    rebuild(AI_DIR, db_path, SCHEMA_PATH)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    assert count == 2
    conn.close()


def test_rebuild_fts_search(tmp_path):
    db_path = str(tmp_path / "memex.db")
    rebuild(AI_DIR, db_path, SCHEMA_PATH)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    results = conn.execute(
        "SELECT id FROM pages_fts WHERE pages_fts MATCH ?", ("database",)
    ).fetchall()
    assert len(results) == 1
    assert results[0]["id"] == "sample:wiki:db-schema"
    conn.close()


def test_rebuild_skips_pages_without_id(tmp_path):
    import textwrap, shutil
    # Copy fixture dir and add a malformed page
    fixture_copy = tmp_path / "sample" / ".ai"
    shutil.copytree(FIXTURES.parent, fixture_copy)
    bad_page = fixture_copy / "wiki" / "no-id.md"
    bad_page.write_text(textwrap.dedent("""\
        ---
        title: No ID
        status: draft
        created: 2026-05-09
        updated: 2026-05-09
        ---
        Body.
    """))
    db_path = str(tmp_path / "memex.db")
    rebuild(str(fixture_copy), db_path, SCHEMA_PATH)

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    assert count == 2  # malformed page skipped, original 2 loaded
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rebuild.py::test_rebuild_populates_all_pages -v`
Expected: `ImportError: cannot import name 'rebuild'`

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/rebuild.py`:
```python
import glob as glob_module


def rebuild(ai_dir: str, db_path: str, schema_path: str) -> None:
    """Walk .ai/ directory, parse all .md files, and populate memex.db."""
    conn = connect(db_path, schema_path)

    pattern = os.path.join(ai_dir, "**", "*.md")
    md_files = glob_module.glob(pattern, recursive=True)

    pages = []
    for file_path in sorted(md_files):
        page = parse_page(file_path)
        if not page["id"]:
            print(f"WARNING: skipping {file_path} — missing id field")
            continue
        pages.append(page)

    for page in pages:
        load_page(conn, page)

    # Rebuild FTS index from pages table content
    conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rebuild.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/rebuild.py tests/test_rebuild.py
git commit -m "feat: rebuild() orchestrates full walk, load, and FTS population"
```

---

### Task 6: CLI entry point and smoke test

**Files:**
- Modify: `scripts/rebuild.py`
- Create: `.gitignore`

- [ ] **Step 1: Add CLI to rebuild.py**

Add to the bottom of `scripts/rebuild.py`:
```python
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Rebuild memex.db from .ai/ markdown files."
    )
    parser.add_argument("ai_dir", help="Path to the project's .ai/ directory")
    parser.add_argument(
        "--db", default=None,
        help="Path to output .db file (default: <ai_dir>/memex.db)",
    )
    parser.add_argument(
        "--schema", default=None,
        help="Path to schema.sql (default: <script_dir>/../db/schema.sql)",
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = args.db or os.path.join(args.ai_dir, "memex.db")
    schema_path = args.schema or os.path.join(script_dir, "..", "db", "schema.sql")

    rebuild(args.ai_dir, db_path, schema_path)
    print(f"Rebuilt {db_path}")
```

- [ ] **Step 2: Create .gitignore**

Create `.gitignore` at the Memex repo root:
```
.ai/memex.db
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: Smoke-test the CLI against the Memex repo itself**

Run from the Memex repo root:
```bash
python scripts/rebuild.py .ai/
```
Expected output: `Rebuilt .ai/memex.db`

Verify the DB was populated:
```bash
python -c "
import sqlite3
conn = sqlite3.connect('.ai/memex.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT id, title, status FROM pages').fetchall()
for r in rows:
    print(r['id'], '|', r['title'], '|', r['status'])
"
```
Expected: one line per `.ai/wiki/*.md` file, showing id, title, and status.

- [ ] **Step 4: Verify WAL files created**

Run: `dir .ai\` (Windows) or `ls .ai/`
Expected: `.ai/memex.db`, `.ai/memex.db-wal`, `.ai/memex.db-shm` present.

- [ ] **Step 5: Commit**

```bash
git add scripts/rebuild.py .gitignore
git commit -m "feat: CLI entry point for rebuild script; add .gitignore"
```

---

## Self-review checklist (do not skip)

- [ ] All tasks produce working, committable code on their own
- [ ] No TBDs or placeholders anywhere in the plan
- [ ] `connect()` defined in Task 2 matches signature used in Tasks 3–6 ✓
- [ ] `parse_page()` defined in Task 3 matches keys consumed by `load_page()` in Task 4 ✓
- [ ] `load_page()` defined in Task 4 matches usage in `rebuild()` Task 5 ✓
- [ ] FTS `INSERT INTO pages_fts(pages_fts) VALUES('rebuild')` is correct SQLite FTS5 rebuild syntax ✓
- [ ] WAL pragma behavior tested (Task 2, `test_connect_sets_wal_mode`) ✓
- [ ] Missing-id case tested and handled (Task 5, `test_rebuild_skips_pages_without_id`) ✓
