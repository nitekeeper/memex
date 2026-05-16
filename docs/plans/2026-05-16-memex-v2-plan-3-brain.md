# Memex v2 — Plan 3: Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Memex Brain — the human-facing second-brain skill layer. Brain stores articles, captures, and syntheses in the default `article.db` store, all routed through the Librarian. End state: a human can ingest an article via `memex:brain:ingest`, ask a question via `memex:brain:ask`, capture a free-form note via `memex:brain:capture`, run a health-check via `memex:brain:lint`, and produce a cross-document synthesis via `memex:brain:synthesize`. First Brain invocation triggers human-agent onboarding. Plan 3 also implements the previously-stubbed `memex:steward:reconcile-orphan`.

**Architecture:** Brain procedures are thin wrappers over Plan 2's `memex:index:*` procedures. `ingest` adds hash-based rerun safety on top of `index:write`. `ask` and `synthesize` use LLM post-processing on `index:search` results. `capture` is `index:write` with minimal payload. `lint` calls `steward:audit-store` scoped to `article.db`. Per spec §8.0 the plugin manifest registers only `memex:run`; Brain's 5 procedures live at `internal/brain/<name>/SKILL.md` and are reached on demand via the user-facing intent routing table inside `skills/run/SKILL.md`. Plan 3 extends that table rather than registering top-level skills.

**Tech Stack:** Python 3.10+, same dependencies as Plans 1 + 2. No new external libraries.

**Reference:** spec at `docs/specs/2026-05-16-memex-v2-redesign-design.md` (sections §5.3, §6 application-side flows, §8.3, §9.2).

**Depends on:** Plan 1 (Core) and Plan 2 (Index + Internal agents).

---

## File Structure

```
memex/
├── db/
│   └── brain.sql                                  # NEW: articles + captures + syntheses
├── scripts/
│   ├── brain.py                                   # NEW: brain operations
│   └── onboarding.py                              # NEW: first-invocation human registration
├── internal/
│   ├── brain/
│   │   ├── ingest/SKILL.md                        # NEW
│   │   ├── ask/SKILL.md                           # NEW
│   │   ├── capture/SKILL.md                       # NEW
│   │   ├── lint/SKILL.md                          # NEW
│   │   └── synthesize/SKILL.md                    # NEW
│   └── steward/
│       └── reconcile-orphan/                      # MODIFY: actual implementation
├── skills/
│   └── run/SKILL.md                               # MODIFY: extend routing table
├── scripts/install.py                             # MODIFY: extend to create article.db
├── scripts/agents/data_steward.py                 # MODIFY: add reconcile_orphan function
├── prompts/
│   └── synthesizer.md                             # NEW: synthesis prompt template
└── tests/
    ├── test_brain_schema.py                       # NEW
    ├── test_onboarding.py                         # NEW
    ├── test_brain_ingest.py                       # NEW
    ├── test_brain_ask.py                          # NEW
    ├── test_brain_capture.py                      # NEW
    ├── test_brain_lint.py                         # NEW
    ├── test_brain_synthesize.py                   # NEW
    ├── test_reconcile_orphan.py                   # NEW
    ├── test_brain_skills.py                       # NEW: SKILL.md presence
    └── test_smoke_plan3.py                        # NEW: end-to-end
```

---

## Task 1: `brain.sql` — article.db schema

**Files:**
- Create: `db/brain.sql`
- Create: `tests/test_brain_schema.py`

- [ ] **Step 1: Write the failing test**

`tests/test_brain_schema.py`:

```python
from pathlib import Path
from scripts.db import get_connection


def test_brain_schema_applies(tmp_path):
    sql = Path("db/brain.sql").read_text()
    db = tmp_path / "article.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    conn.commit()
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    for t in ("articles", "captures", "syntheses"):
        assert t in tables
    conn.close()


def test_brain_tables_have_index_id(tmp_path):
    sql = Path("db/brain.sql").read_text()
    db = tmp_path / "article.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    for table in ("articles", "captures", "syntheses"):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        assert "index_id" in cols, f"{table} missing index_id"
    conn.close()


def test_articles_has_source_hash(tmp_path):
    sql = Path("db/brain.sql").read_text()
    db = tmp_path / "article.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(articles)")}
    assert "source_hash" in cols
    assert "source_url" in cols
    assert "raw_path" in cols
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_brain_schema.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`db/brain.sql`:

```sql
-- article.db: default Brain store.
-- Created on plugin install. Schema is owned by Memex Brain.

CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id     TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    source_url   TEXT,
    source_hash  TEXT,          -- canonicalized content hash for rerun safety
    body         TEXT NOT NULL,
    raw_path     TEXT,          -- pointer to ~/.memex/raw/...
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS articles_source_hash_idx ON articles(source_hash);

CREATE TABLE IF NOT EXISTS captures (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id     TEXT NOT NULL UNIQUE,
    title        TEXT,
    body         TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS syntheses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id     TEXT NOT NULL UNIQUE,
    topic        TEXT NOT NULL,
    body         TEXT NOT NULL,
    inputs_json  TEXT NOT NULL,   -- JSON array of source index_ids
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_brain_schema.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add db/brain.sql tests/test_brain_schema.py
git commit -m "feat(brain): article.db schema (articles + captures + syntheses)"
```

---

## Task 2: Extend `install.py` to create article.db

**Files:**
- Modify: `scripts/install.py`
- Modify: `tests/test_install.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_install.py`:

```python
def test_install_creates_article_db(tmp_memex_home):
    install.run()
    assert (memex_home() / "article.db").exists()


def test_install_registers_article_in_registry(tmp_memex_home):
    install.run()
    rec = registry.get_store("article")
    assert rec is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_install.py::test_install_creates_article_db -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/install.py` (inside the `run()` function, after the index.db block):

```python
    # article.db (Plan 3 addition)
    article_db_path = home / "article.db"
    if not article_db_path.exists():
        conn = get_connection(str(article_db_path))
        conn.executescript(Path("db/migrations_table.sql").read_text())
        conn.executescript(Path("db/brain.sql").read_text())
        conn.execute(
            "INSERT INTO migrations (filename) VALUES (?)",
            ("brain.sql",),
        )
        conn.commit()
        conn.close()
    if registry.get_store("article") is None:
        registry.register_store("article", str(article_db_path), schema_version="v1")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_install.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/install.py tests/test_install.py
git commit -m "feat(brain): install.run creates and registers article.db"
```

---

## Task 3: `onboarding.py` — human registration flow

**Files:**
- Create: `scripts/onboarding.py`
- Create: `tests/test_onboarding.py`

- [ ] **Step 1: Write the failing test**

`tests/test_onboarding.py`:

```python
import pytest
from unittest.mock import patch
from scripts import install, onboarding, agents, roles
from scripts.db import memex_home


def test_needs_onboarding_when_no_human_agent(tmp_memex_home):
    install.run()
    assert onboarding.needs_onboarding() is True


def test_needs_onboarding_false_after_registration(tmp_memex_home):
    install.run()
    agents_db = str(memex_home() / "agents.db")
    role = roles.create_role(agents_db, "User", "Human user")
    agents.create_agent(agents_db, "human-test", "Test User", role["id"], "test profile")
    assert onboarding.needs_onboarding() is False


def test_register_human_creates_role_if_missing(tmp_memex_home):
    install.run()
    onboarding.register_human(agent_id="human-user", name="user", role_name="User")
    agents_db = str(memex_home() / "agents.db")
    r = agents.get_agent(agents_db, "human-user")
    assert r is not None
    assert r["name"] == "user"


def test_register_human_reuses_existing_role(tmp_memex_home):
    install.run()
    agents_db = str(memex_home() / "agents.db")
    existing = roles.create_role(agents_db, "Researcher", "researcher role")
    onboarding.register_human(agent_id="human-user", name="user", role_name="Researcher")
    r = agents.get_agent(agents_db, "human-user")
    assert r["role_id"] == existing["id"]


def test_register_human_idempotent(tmp_memex_home):
    install.run()
    onboarding.register_human(agent_id="human-x", name="X", role_name="User")
    # Second call should not raise
    onboarding.register_human(agent_id="human-x", name="X (updated)", role_name="User")
    agents_db = str(memex_home() / "agents.db")
    r = agents.get_agent(agents_db, "human-x")
    assert r["name"] == "X (updated)"


def test_get_human_returns_registered_agent(tmp_memex_home):
    install.run()
    onboarding.register_human(agent_id="human-user", name="user", role_name="User")
    h = onboarding.get_human()
    assert h["id"] == "human-user"


def test_get_human_returns_none_when_not_registered(tmp_memex_home):
    install.run()
    assert onboarding.get_human() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_onboarding.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`scripts/onboarding.py`:

```python
"""Human-user onboarding for Memex Brain.

First Brain invocation triggers needs_onboarding() check. If true,
the caller (Brain skill wrapper) prompts the user for id/name/role and
calls register_human(). After successful registration, future Brain calls
skip onboarding.
"""
from __future__ import annotations
from scripts import roles, agents
from scripts.db import memex_home

# Memex's 5 internal agents that should be filtered out when looking
# for "the human."
_INTERNAL_AGENT_IDS = {
    "librarian-1", "reference-librarian-1", "archivist-1",
    "dba-1", "data-steward-1",
}


def _agents_db() -> str:
    return str(memex_home() / "agents.db")


def needs_onboarding() -> bool:
    """True if no human (non-internal) agent is registered."""
    return get_human() is None


def get_human() -> dict | None:
    """Return the first registered non-internal agent, or None."""
    listed = agents.list_agents(_agents_db())
    for a in listed:
        if a["id"] not in _INTERNAL_AGENT_IDS:
            return a
    return None


def register_human(agent_id: str, name: str, role_name: str, profile: str = "") -> dict:
    """Register a human agent. Idempotent: existing agent_id is updated."""
    db = _agents_db()
    # Ensure role exists
    existing_roles = {r["name"]: r["id"] for r in roles.list_roles(db)}
    if role_name in existing_roles:
        role_id = existing_roles[role_name]
    else:
        new_role = roles.create_role(db, role_name, f"Human role: {role_name}")
        role_id = new_role["id"]

    if not profile:
        profile = f"Human user. Registered via Memex Brain onboarding."

    if agents.get_agent(db, agent_id) is None:
        return agents.create_agent(db, agent_id, name, role_id, profile)
    else:
        return agents.update_agent(db, agent_id, name=name, role_id=role_id, profile=profile)


if __name__ == "__main__":
    import sys
    if sys.argv[1] == "needs":
        print("yes" if needs_onboarding() else "no")
    elif sys.argv[1] == "register":
        # python -m scripts.onboarding register <id> <name> <role>
        print(register_human(sys.argv[2], sys.argv[3], sys.argv[4]))
    elif sys.argv[1] == "get":
        h = get_human()
        print(h if h else "Not registered")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_onboarding.py -v`
Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/onboarding.py tests/test_onboarding.py
git commit -m "feat(brain): human-user onboarding (needs_onboarding, register_human, get_human)"
```

---

## Task 4: `brain.py` — ingest

**Files:**
- Create: `scripts/brain.py`
- Create: `tests/test_brain_ingest.py`

- [ ] **Step 1: Write the failing test**

`tests/test_brain_ingest.py`:

```python
import json
import hashlib
import pytest
from unittest.mock import patch
from scripts import install, brain, onboarding, stores
from scripts.db import memex_home


@pytest.fixture
def installed_with_human(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")
    return memex_home()


def test_ingest_new_article_writes_to_article_db(installed_with_human):
    mock_lib = json.dumps({
        "index_id": "idx-1",
        "key": "test-article",
        "domain": "article",
        "searchable": "test searchable",
        "metadata": {},
        "relations": []
    })
    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        result = brain.ingest(
            title="Test Article",
            body="this is the body",
            source_url="https://example.com/a",
            caller_agent_id="human-test",
        )

    rows = stores.query("article", "SELECT * FROM articles WHERE index_id = ?", (result["index_id"],))
    assert len(rows) == 1
    assert rows[0]["title"] == "Test Article"
    assert rows[0]["source_url"] == "https://example.com/a"


def test_ingest_computes_source_hash(installed_with_human):
    mock_lib = json.dumps({
        "index_id": "idx-1",
        "key": "k",
        "domain": "article",
        "searchable": "s",
        "metadata": {},
        "relations": []
    })
    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        result = brain.ingest(
            title="X", body="hello", source_url="https://x", caller_agent_id="human-test",
        )

    rows = stores.query("article", "SELECT source_hash FROM articles WHERE index_id = ?", (result["index_id"],))
    assert rows[0]["source_hash"] is not None
    expected = hashlib.sha256(b"hello").hexdigest()
    assert rows[0]["source_hash"] == expected


def test_ingest_rerun_with_same_content_returns_skipped(installed_with_human):
    """Re-ingest of the same canonical content is a no-op."""
    mock_lib = json.dumps({
        "index_id": "idx-1", "key": "k", "domain": "article",
        "searchable": "s", "metadata": {}, "relations": []
    })
    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        r1 = brain.ingest(title="X", body="hello", source_url="https://x", caller_agent_id="human-test")
        r2 = brain.ingest(title="X", body="hello", source_url="https://x", caller_agent_id="human-test")

    assert r2["status"] == "skipped"
    assert r2["existing_index_id"] == r1["index_id"]


def test_ingest_rerun_with_different_content_creates_new_row(installed_with_human):
    """Different content → new row (no in-place merge per spec)."""
    responses = [
        json.dumps({"index_id": "idx-a", "key": "k", "domain": "article", "searchable": "s", "metadata": {}, "relations": []}),
        json.dumps({"index_id": "idx-b", "key": "k", "domain": "article", "searchable": "s", "metadata": {}, "relations": []}),
    ]
    call_count = {"n": 0}
    def mock_llm(prompt):
        r = responses[call_count["n"]]
        call_count["n"] += 1
        return r

    with patch("scripts.agents.librarian._invoke_llm", side_effect=mock_llm), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        r1 = brain.ingest(title="X", body="version 1", source_url="https://x", caller_agent_id="human-test")
        r2 = brain.ingest(title="X", body="version 2", source_url="https://x", caller_agent_id="human-test")

    assert r1["index_id"] != r2["index_id"]
    assert r2["status"] == "ingested"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_brain_ingest.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`scripts/brain.py`:

```python
"""Memex Brain operations: ingest, ask, capture, lint, synthesize.

Brain is a consumer of Memex's Index + Librarian. All writes route
through memex:index:write. All reads route through memex:index:search.
"""
from __future__ import annotations
import hashlib
import json
import re
from scripts import stores
from scripts.agents import librarian, reference_librarian, archivist
from scripts.agents import data_steward
from scripts.db import memex_home


def _canonical_hash(body: str) -> str:
    """Compute a stable hash for a body, normalized for rerun safety."""
    text = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _find_existing_by_hash(source_hash: str) -> dict | None:
    rows = stores.query("article", "SELECT * FROM articles WHERE source_hash = ? LIMIT 1", (source_hash,))
    return rows[0] if rows else None


def ingest(
    title: str,
    body: str,
    caller_agent_id: str,
    source_url: str | None = None,
) -> dict:
    """Ingest an article into article.db. Returns dict with status+index_id."""
    source_hash = _canonical_hash(body)
    existing = _find_existing_by_hash(source_hash)
    if existing is not None:
        return {
            "status": "skipped",
            "reason": "source_hash matches existing article",
            "existing_index_id": existing["index_id"],
        }

    # Archive raw payload
    archive_result = archivist.archive(body.encode("utf-8"), filename=f"{_slugify(title)}.md")

    payload = {
        "title": title,
        "body": body,
        "source_url": source_url,
        "source_hash": source_hash,
        "raw_path": archive_result["path"],
        "created_by": caller_agent_id,
    }

    result = librarian.index_write(
        payload=payload,
        target_store="article",
        target_table="articles",
        caller_agent_id=caller_agent_id,
    )
    return {"status": "ingested", **result}


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text or "untitled"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_brain_ingest.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/brain.py tests/test_brain_ingest.py
git commit -m "feat(brain): brain.ingest with source-hash rerun safety and Librarian routing"
```

---

## Task 5: `brain.py` — capture

**Files:**
- Modify: `scripts/brain.py`
- Create: `tests/test_brain_capture.py`

- [ ] **Step 1: Write the failing test**

`tests/test_brain_capture.py`:

```python
import json
import pytest
from unittest.mock import patch
from scripts import install, brain, onboarding, stores


@pytest.fixture
def installed_with_human(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")


def test_capture_writes_to_captures_table(installed_with_human):
    mock_lib = json.dumps({
        "index_id": "idx-c1",
        "key": "k",
        "domain": "capture",
        "searchable": "s",
        "metadata": {},
        "relations": []
    })
    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        result = brain.capture(
            body="quick thought about X",
            caller_agent_id="human-test",
        )

    rows = stores.query("article", "SELECT * FROM captures WHERE index_id = ?", (result["index_id"],))
    assert len(rows) == 1
    assert rows[0]["body"] == "quick thought about X"


def test_capture_supports_optional_title(installed_with_human):
    mock_lib = json.dumps({
        "index_id": "idx-c2",
        "key": "k",
        "domain": "capture",
        "searchable": "s",
        "metadata": {},
        "relations": []
    })
    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        result = brain.capture(
            body="thought",
            caller_agent_id="human-test",
            title="My Thought",
        )

    rows = stores.query("article", "SELECT * FROM captures WHERE index_id = ?", (result["index_id"],))
    assert rows[0]["title"] == "My Thought"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_brain_capture.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/brain.py`:

```python
def capture(body: str, caller_agent_id: str, title: str | None = None) -> dict:
    """Capture a free-form note into article.db.captures.

    Lighter than ingest — no source URL, no hash check, but still routes
    through the Librarian.
    """
    payload = {
        "title": title,
        "body": body,
        "created_by": caller_agent_id,
    }
    result = librarian.index_write(
        payload=payload,
        target_store="article",
        target_table="captures",
        caller_agent_id=caller_agent_id,
    )
    return {"status": "captured", **result}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_brain_capture.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/brain.py tests/test_brain_capture.py
git commit -m "feat(brain): brain.capture for free-form notes"
```

---

## Task 6: `brain.py` — ask

**Files:**
- Modify: `scripts/brain.py`
- Create: `tests/test_brain_ask.py`

- [ ] **Step 1: Write the failing test**

`tests/test_brain_ask.py`:

```python
import json
import pytest
from unittest.mock import patch
from scripts import install, brain, onboarding
from scripts.db import memex_home, get_connection


@pytest.fixture
def installed_with_human(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")


def test_ask_returns_results_from_index(installed_with_human):
    # Seed an index entry
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("idx-a", "k", "article", "article", "articles", "1", "cats are interesting", "librarian-1"),
    )
    conn.commit()
    conn.close()

    mock_plan = json.dumps({
        "fts_query": "cats",
        "vector_query": None,
        "filters": {},
        "limit": 5,
    })
    with patch("scripts.agents.reference_librarian._invoke_llm", return_value=mock_plan):
        results = brain.ask("tell me about cats")

    ids = [r["index_id"] for r in results]
    assert "idx-a" in ids


def test_ask_returns_empty_when_nothing_matches(installed_with_human):
    mock_plan = json.dumps({
        "fts_query": "nonexistent",
        "vector_query": None,
        "filters": {},
        "limit": 5,
    })
    with patch("scripts.agents.reference_librarian._invoke_llm", return_value=mock_plan):
        results = brain.ask("anything?")
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_brain_ask.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/brain.py`:

```python
def ask(query: str) -> list[dict]:
    """Ask a question. Routes through the Reference Librarian."""
    return reference_librarian.ask(query)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_brain_ask.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/brain.py tests/test_brain_ask.py
git commit -m "feat(brain): brain.ask delegates to Reference Librarian"
```

---

## Task 7: `brain.py` — lint

**Files:**
- Modify: `scripts/brain.py`
- Create: `tests/test_brain_lint.py`

- [ ] **Step 1: Write the failing test**

`tests/test_brain_lint.py`:

```python
import pytest
from pathlib import Path
from scripts import install, brain
from scripts.db import memex_home, get_connection


def test_lint_returns_report_path(tmp_memex_home):
    install.run()
    report_path = brain.lint()
    assert Path(report_path).exists()


def test_lint_detects_brain_orphans(tmp_memex_home):
    install.run()
    # Create an index entry pointing to a nonexistent article row
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("idx-orphan", "x", "article", "article", "articles", "99999", "txt", "librarian-1"),
    )
    conn.commit()
    conn.close()

    report_path = brain.lint()
    content = Path(report_path).read_text()
    assert "idx-orphan" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_brain_lint.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/brain.py`:

```python
def lint() -> str:
    """Run a Data Steward audit and return the report path."""
    index_db = str(memex_home() / "index.db")
    return data_steward.audit(index_db)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_brain_lint.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/brain.py tests/test_brain_lint.py
git commit -m "feat(brain): brain.lint runs Data Steward audit"
```

---

## Task 8: `brain.py` — synthesize

**Files:**
- Modify: `scripts/brain.py`
- Create: `prompts/synthesizer.md`
- Create: `tests/test_brain_synthesize.py`

- [ ] **Step 1: Write the failing test**

`tests/test_brain_synthesize.py`:

```python
import json
import pytest
from unittest.mock import patch
from scripts import install, brain, onboarding, stores
from scripts.db import memex_home, get_connection


@pytest.fixture
def installed_with_human_and_sources(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")

    # Seed two article rows and matching index entries
    conn = get_connection(str(memex_home() / "index.db"))
    for idx, body in [("idx-s1", "first source body"), ("idx-s2", "second source body")]:
        conn.execute(
            "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (idx, idx, "article", "article", "articles", "1", body, "librarian-1"),
        )
    conn.commit()
    conn.close()


def test_synthesize_writes_to_syntheses_table(installed_with_human_and_sources):
    mock_synthesis = "Combined view: both sources discuss bodies."
    mock_lib = json.dumps({
        "index_id": "idx-syn-1",
        "key": "synthesis-1",
        "domain": "synthesis",
        "searchable": "synthesis text",
        "metadata": {},
        "relations": [
            {"to_index_id": "idx-s1", "rel_type": "synthesizes"},
            {"to_index_id": "idx-s2", "rel_type": "synthesizes"},
        ]
    })
    with patch("scripts.brain._invoke_synthesizer", return_value=mock_synthesis), \
         patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        result = brain.synthesize(
            topic="bodies",
            input_index_ids=["idx-s1", "idx-s2"],
            caller_agent_id="human-test",
        )

    rows = stores.query("article", "SELECT * FROM syntheses WHERE index_id = ?", (result["index_id"],))
    assert len(rows) == 1
    assert rows[0]["body"] == mock_synthesis
    assert rows[0]["topic"] == "bodies"
    assert json.loads(rows[0]["inputs_json"]) == ["idx-s1", "idx-s2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_brain_synthesize.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`prompts/synthesizer.md`:

```markdown
# Synthesizer Prompt

You are tasked with producing a coherent synthesis across multiple
documents on a given topic.

## Inputs

- **Topic:** {{TOPIC}}
- **Sources (markdown, each prefixed with its index_id):**

{{SOURCES}}

## Task

Produce a unified prose synthesis that:
- Identifies the through-line(s) across sources.
- Notes contradictions or tensions explicitly.
- Cites sources by their index_id in inline brackets, e.g., [idx-s1].
- Stays grounded — do not introduce claims not present in the sources.
- Length: 2–6 paragraphs.

Output the synthesis text only — no JSON wrapper, no headers, no commentary.
```

Append to `scripts/brain.py`:

```python
import json
from pathlib import Path


def _invoke_synthesizer(prompt: str) -> str:
    """LLM invocation for synthesis. Mocked in tests; production wires to subagent."""
    raise NotImplementedError("Synthesizer LLM invocation TBD")


def _fetch_source_bodies(index_ids: list[str]) -> list[dict]:
    """Fetch the full row for each index_id from its target store."""
    sources = []
    for idx in index_ids:
        rows = stores.query("article", "SELECT * FROM articles WHERE index_id = ?", (idx,))
        if rows:
            sources.append({"index_id": idx, "body": rows[0]["body"], "title": rows[0].get("title", "")})
    return sources


def synthesize(
    topic: str,
    input_index_ids: list[str],
    caller_agent_id: str,
) -> dict:
    """Produce a multi-source synthesis on a topic. Stores in syntheses table."""
    sources = _fetch_source_bodies(input_index_ids)
    sources_md = "\n\n".join([
        f"### [{s['index_id']}] {s.get('title', '')}\n\n{s['body']}"
        for s in sources
    ])

    template = Path("prompts/synthesizer.md").read_text()
    prompt = template.replace("{{TOPIC}}", topic).replace("{{SOURCES}}", sources_md)

    synthesis_body = _invoke_synthesizer(prompt)

    payload = {
        "topic": topic,
        "body": synthesis_body,
        "inputs_json": json.dumps(input_index_ids),
        "created_by": caller_agent_id,
    }
    result = librarian.index_write(
        payload=payload,
        target_store="article",
        target_table="syntheses",
        caller_agent_id=caller_agent_id,
    )
    return {"status": "synthesized", **result}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_brain_synthesize.py -v`
Expected: 1 PASSED.

- [ ] **Step 5: Commit**

```bash
git add prompts/synthesizer.md scripts/brain.py tests/test_brain_synthesize.py
git commit -m "feat(brain): brain.synthesize cross-document synthesis with provenance"
```

---

## Task 9: `data_steward.reconcile_orphan` — implementation

**Files:**
- Modify: `scripts/agents/data_steward.py`
- Create: `tests/test_reconcile_orphan.py`

- [ ] **Step 1: Write the failing test**

`tests/test_reconcile_orphan.py`:

```python
import pytest
from scripts import install
from scripts.agents import data_steward
from scripts.db import memex_home, get_connection


def _seed_orphan(index_id: str, store: str = "no-store", table: str = "t", row_id: str = "1"):
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (index_id, "k", "article", store, table, row_id, "txt", "librarian-1"),
    )
    conn.commit()
    conn.close()


def test_reconcile_delete_index_removes_documents_row(tmp_memex_home):
    install.run()
    _seed_orphan("idx-o1")

    data_steward.reconcile_orphan("idx-o1", action="delete-index")

    conn = get_connection(str(memex_home() / "index.db"))
    row = conn.execute("SELECT * FROM documents WHERE index_id = ?", ("idx-o1",)).fetchone()
    conn.close()
    assert row is None


def test_reconcile_delete_index_also_removes_relations(tmp_memex_home):
    install.run()
    _seed_orphan("idx-o2")
    _seed_orphan("idx-o2-target")
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
        ("idx-o2", "idx-o2-target", "cites"),
    )
    conn.commit()
    conn.close()

    data_steward.reconcile_orphan("idx-o2", action="delete-index")

    conn = get_connection(str(memex_home() / "index.db"))
    rels = conn.execute(
        "SELECT * FROM relations WHERE from_index_id = ? OR to_index_id = ?", ("idx-o2", "idx-o2")
    ).fetchall()
    conn.close()
    assert rels == []


def test_reconcile_note_leaves_data_unchanged(tmp_memex_home):
    install.run()
    _seed_orphan("idx-o3")

    data_steward.reconcile_orphan("idx-o3", action="note", note_text="acknowledged: known orphan")

    conn = get_connection(str(memex_home() / "index.db"))
    row = conn.execute("SELECT * FROM documents WHERE index_id = ?", ("idx-o3",)).fetchone()
    conn.close()
    assert row is not None  # still there


def test_reconcile_unknown_action_raises(tmp_memex_home):
    install.run()
    _seed_orphan("idx-o4")
    with pytest.raises(ValueError):
        data_steward.reconcile_orphan("idx-o4", action="explode")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reconcile_orphan.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/agents/data_steward.py`:

```python
def reconcile_orphan(index_id: str, action: str, note_text: str | None = None) -> dict:
    """Resolve a flagged orphan.

    Actions:
      - delete-index: remove the documents row AND its relations (target row already gone)
      - reindex: re-run Librarian on the orphaned target row (Plan 3+; raises NotImplementedError for now if the target row also missing)
      - note: leave as-is but record acknowledgment in audits/

    Returns dict describing the action taken.
    """
    valid_actions = {"delete-index", "reindex", "note"}
    if action not in valid_actions:
        raise ValueError(f"Unknown action: {action}. Valid: {valid_actions}")

    index_db = str(memex_home() / "index.db")
    if action == "delete-index":
        conn = get_connection(index_db)
        # Delete relations first (FK)
        conn.execute(
            "DELETE FROM relations WHERE from_index_id = ? OR to_index_id = ?",
            (index_id, index_id),
        )
        conn.execute("DELETE FROM documents WHERE index_id = ?", (index_id,))
        conn.commit()
        conn.close()
        return {"action": "delete-index", "index_id": index_id, "result": "removed"}

    elif action == "note":
        # Append to a "reconciliation-log" file in audits/
        audits_dir = memex_home() / "audits"
        audits_dir.mkdir(parents=True, exist_ok=True)
        log_path = audits_dir / "reconciliation-log.md"
        from datetime import datetime, timezone
        entry = f"\n- {datetime.now(timezone.utc).isoformat()} | index_id={index_id} | action=note | text={note_text or ''}\n"
        with open(log_path, "a") as f:
            f.write(entry)
        return {"action": "note", "index_id": index_id, "result": "logged"}

    elif action == "reindex":
        # Reverse-orphan case: row exists in target store but not in index.
        # Full implementation would re-invoke Librarian on the target row.
        # Plan 3 stub: raise NotImplementedError pointing to Plan 4 enhancement.
        raise NotImplementedError("reindex action requires Plan 4 re-embedding tooling")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reconcile_orphan.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/agents/data_steward.py tests/test_reconcile_orphan.py
git commit -m "feat(brain): data_steward.reconcile_orphan with delete-index and note actions"
```

---

## Task 10: `memex:brain:*` SKILL.md files

**Files:**
- Create: `internal/brain/ingest/SKILL.md`
- Create: `internal/brain/ask/SKILL.md`
- Create: `internal/brain/capture/SKILL.md`
- Create: `internal/brain/lint/SKILL.md`
- Create: `internal/brain/synthesize/SKILL.md`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_skills_present.py`:

```python
BRAIN_SKILLS = ["ingest", "ask", "capture", "lint", "synthesize"]


def test_brain_skills_present():
    for s in BRAIN_SKILLS:
        p = Path(f"internal/brain/{s}/SKILL.md")
        assert p.exists(), f"Missing: brain/{s}"


def test_brain_skills_frontmatter():
    for s in BRAIN_SKILLS:
        content = Path(f"internal/brain/{s}/SKILL.md").read_text()
        assert f"name: memex:brain:{s}" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`internal/brain/ingest/SKILL.md`:

```markdown
---
name: memex:brain:ingest
description: Add an external article or source to your personal Brain. Routes through the Archivist (preserves raw), Librarian (assigns index_id, classifies, links), and Memex Core (writes to article.db). Hash-based rerun safety: re-ingesting the same content is a silent no-op.
---

# memex:brain:ingest

## When to use

You read something worth keeping — an article, a blog post, a paper, a clipped page — and want it findable in your personal Brain. Daily second-brain action.

## Inputs

- `title` — article title
- `body` — article body text (markdown preferred)
- `source_url` — optional; original URL for provenance
- `caller_agent_id` — your registered human agent id (set during onboarding)

## What happens

1. Onboarding check: if no human agent registered, prompts you. Once.
2. Source-hash check: if the canonical body matches an already-ingested article, returns `{"status": "skipped", "existing_index_id": ...}` with no further work.
3. Archivist writes raw body to `~/.memex/raw/`.
4. Librarian indexes (assigns index_id, classifies domain, extracts relations to prior articles).
5. Memex Core inserts a row in `article.db.articles` with `index_id`, `source_hash`, and `raw_path`.
6. Returns `{"status": "ingested", "index_id": ..., "key": ..., "domain": ..., "relations": [...]}`.

## Invocation

`scripts/brain.py:ingest(title, body, caller_agent_id, source_url)`

## Onboarding

If `caller_agent_id` is not registered:
- Prompt: "What's your agent id? (e.g., `human-user`)"
- Prompt: "Display name?"
- Prompt: "Role? (default: User; can be Researcher, Owner, Editor, or custom)"
- Calls `scripts/onboarding.py:register_human()`, then retries the ingest.
```

`internal/brain/ask/SKILL.md`:

```markdown
---
name: memex:brain:ask
description: Ask a natural-language question against your Brain. Routes through the Reference Librarian which decomposes the query, runs FTS5 + vector retrieval across the Index, ranks results, and returns citation-ready hits with full content fetched from target stores.
---

# memex:brain:ask

## When to use

You want to find or remember something. Replaces v1 blueprint's wiki/web/training waterfall — Brain trusts the Index first; web fallback is the caller's responsibility (Brain does not auto-search the web in v0.2).

## Inputs

- `query` — natural-language question

## What happens

1. Reference Librarian builds an FTS5 + vector query plan.
2. Plan executes against `~/.memex/index.db`.
3. Top candidates' full rows are fetched from their target stores.
4. Returns ranked list with provenance.

## Invocation

`scripts/brain.py:ask(query)`

## Output

```json
[
  {
    "index_id": "...",
    "store": "article",
    "key": "...",
    "domain": "article",
    "title": "...",
    "body": "...",
    "relevance": 0.83
  },
  ...
]
```
```

`internal/brain/capture/SKILL.md`:

```markdown
---
name: memex:brain:capture
description: Capture a free-form note, observation, or snippet to your Brain. Lighter than ingest — no source URL, no hash check, but still indexed by the Librarian.
---

# memex:brain:capture

## When to use

A thought worth keeping that isn't sourced from elsewhere. Personal observations, working hypotheses, draft snippets.

## Inputs

- `body` — the note text
- `caller_agent_id` — your agent id
- `title` — optional

## What happens

Indexed by Librarian, stored in `article.db.captures`.

## Invocation

`scripts/brain.py:capture(body, caller_agent_id, title)`
```

`internal/brain/lint/SKILL.md`:

```markdown
---
name: memex:brain:lint
description: Run a Data Steward audit over your Brain. Detects orphans (index entries without matching article/capture/synthesis rows), broken relations, and integrity drift. Read-only; reports findings; does not auto-fix.
---

# memex:brain:lint

## When to use

Periodic maintenance. Recommended monthly or after bulk activity.

## Inputs

None.

## What happens

Invokes `memex:steward:audit`, scoped (in this v0.2 implementation) to the full Index. Returns the report path.

## Invocation

`scripts/brain.py:lint()`
```

`internal/brain/synthesize/SKILL.md`:

```markdown
---
name: memex:brain:synthesize
description: Produce a cross-document synthesis on a topic. Given a list of source index_ids, the Synthesizer LLM produces a unified prose synthesis with inline citations; the result is indexed as a new `synthesis` document.
---

# memex:brain:synthesize

## When to use

You have multiple sources on a topic and want to see the through-line. Higher-order than `ask` — produces a written synthesis, not just a result list.

## Inputs

- `topic` — short topic descriptor
- `input_index_ids` — list of source index_ids (typically results of a prior `ask`)
- `caller_agent_id`

## What happens

1. Fetches full source bodies from `article.db.articles` for each input index_id.
2. Synthesizer LLM produces prose synthesis with `[idx-...]` citations.
3. Synthesis is stored in `article.db.syntheses` with `inputs_json` recording provenance.
4. Librarian indexes the synthesis as `domain: synthesis` with `synthesizes` relations back to inputs.

## Invocation

`scripts/brain.py:synthesize(topic, input_index_ids, caller_agent_id)`
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_skills_present.py -v`
Expected: All PASSED.

- [ ] **Step 5: Commit**

```bash
git add internal/brain/
git commit -m "docs(brain): SKILL.md for memex:brain:ingest, ask, capture, lint, synthesize"
```

---

## Task 11: Update `memex:run` routing for Brain procedures

**Files:**
- Modify: `skills/run/SKILL.md`
- Modify: `tests/test_skills_present.py`

> Per spec §8.0 the plugin manifest registers ONLY `memex:run`. `plugin.json` is NOT touched in Plan 3. Brain's 5 procedures live at `internal/brain/<name>/SKILL.md` and become reachable by appending a user-facing intent routing section to the body of `skills/run/SKILL.md`. Unlike Plan 1's CRUD routing and Plan 2's agent-facing operation routing, Brain routing maps natural-language user intents (e.g. "ingest this article", "ask about X") onto procedures — these are the daily second-brain entry points for the human user.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_skills_present.py`:

```python
BRAIN_PROCEDURES = ["ingest", "ask", "capture", "lint", "synthesize"]


def test_run_skill_routes_to_brain_procedures():
    """memex:run must contain routing entries for every Brain procedure,
    so the human user can invoke them via natural-language intent without
    Claude Code auto-loading their descriptions."""
    run_content = Path("skills/run/SKILL.md").read_text(encoding="utf-8")
    for name in BRAIN_PROCEDURES:
        expected = f"internal/brain/{name}/SKILL.md"
        assert expected in run_content, (
            f"memex:run missing routing entry for {expected}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Append a new section to `skills/run/SKILL.md` (after the Plan 2 "v2 Index, Steward, and DBA routing" section):

```markdown
## v2 Brain user-facing intent routing

Plan 3 adds the Memex Brain — the opinionated second-brain layer. These
5 procedures are the daily entry points for the human user. They live
at `internal/brain/<name>/SKILL.md` and are reached via natural-language
intent expressed to `memex:run`. The user does NOT invoke
`memex:brain:ingest` as a top-level skill — that name no longer exists
in `plugin.json`. Instead the user says e.g. "ingest this article" and
`memex:run` routes to the corresponding procedure.

| User intent | Internal procedure |
|---|---|
| Add an external article / source / page to my Brain | `internal/brain/ingest/SKILL.md` |
| Ask a natural-language question against my Brain | `internal/brain/ask/SKILL.md` |
| Capture a free-form note or observation | `internal/brain/capture/SKILL.md` |
| Run a Brain health-check / lint / audit | `internal/brain/lint/SKILL.md` |
| Produce a cross-document synthesis on a topic | `internal/brain/synthesize/SKILL.md` |

The Python implementations live in `scripts/brain.py`. Each SKILL.md is
a short documentation wrapper; `memex:run` reads it on demand for the
procedure contract, then calls the implementation.
```

- [ ] **Step 4: Run tests to verify they pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/run/SKILL.md tests/test_skills_present.py
git commit -m "feat(brain): extend memex:run routing for Brain user-facing intents"
```

---

## Task 12: End-to-end smoke test (Plan 3)

**Files:**
- Create: `tests/test_smoke_plan3.py`

- [ ] **Step 1: Write the failing test**

```python
import json
import pytest
from unittest.mock import patch
from scripts import install, brain, onboarding, stores


def test_e2e_full_brain_lifecycle(tmp_memex_home):
    """install → onboard → ingest → ask → capture → synthesize → lint."""
    install.run()
    onboarding.register_human("human-test", "Test", "User")

    mock_lib_responses = iter([
        json.dumps({"index_id": "idx-a1", "key": "first-article", "domain": "article", "searchable": "first body", "metadata": {}, "relations": []}),
        json.dumps({"index_id": "idx-a2", "key": "second-article", "domain": "article", "searchable": "second body", "metadata": {}, "relations": []}),
        json.dumps({"index_id": "idx-c1", "key": "capture-1", "domain": "capture", "searchable": "captured thought", "metadata": {}, "relations": []}),
        json.dumps({"index_id": "idx-syn", "key": "synthesis-1", "domain": "synthesis", "searchable": "synthesis text", "metadata": {}, "relations": []}),
    ])

    with patch("scripts.agents.librarian._invoke_llm", side_effect=lambda p: next(mock_lib_responses)), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"), \
         patch("scripts.agents.reference_librarian._invoke_llm",
               return_value=json.dumps({"fts_query": "body", "vector_query": None, "filters": {}, "limit": 10})), \
         patch("scripts.brain._invoke_synthesizer", return_value="Synthesized view of both sources."):

        # 1. Ingest two articles
        r1 = brain.ingest("First", "first body", "human-test", source_url="https://a")
        r2 = brain.ingest("Second", "second body", "human-test", source_url="https://b")
        assert r1["index_id"] == "idx-a1"
        assert r2["index_id"] == "idx-a2"

        # 2. Ask
        results = brain.ask("body")
        ids = {r["index_id"] for r in results}
        assert "idx-a1" in ids or "idx-a2" in ids

        # 3. Capture
        c = brain.capture("captured thought", "human-test")
        assert c["index_id"] == "idx-c1"

        # 4. Synthesize
        s = brain.synthesize(topic="bodies", input_index_ids=["idx-a1", "idx-a2"], caller_agent_id="human-test")
        assert s["index_id"] == "idx-syn"

        # 5. Lint
        report = brain.lint()
        from pathlib import Path
        assert Path(report).exists()
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_smoke_plan3.py -v`
Expected: PASS.

- [ ] **Step 3-4: Full suite**

Run: `pytest tests/ -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_smoke_plan3.py
git commit -m "test(brain): end-to-end Brain lifecycle smoke test"
```

---

## Task 13: Plan 3 doc

**Files:**
- Create: `docs/BRAIN.md`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


def test_brain_doc_exists():
    assert Path("docs/BRAIN.md").exists()


def test_brain_doc_lists_skills():
    content = Path("docs/BRAIN.md").read_text()
    for s in ["ingest", "ask", "capture", "lint", "synthesize"]:
        assert s in content
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`docs/BRAIN.md`:

```markdown
# Memex Brain (Plan 3)

Brain is Memex's opinionated second-brain layer. It owns `article.db`
and exposes five procedures for daily use.

## Invocation

Per spec §8.0, only `memex:run` is registered as a top-level Claude
Code skill. Brain procedures live at `internal/brain/<name>/SKILL.md`
and are reached on demand via the natural-language intent routing
table inside `skills/run/SKILL.md`. To use Brain, the user expresses
an intent to `memex:run` — e.g. "ingest this article", "ask about X",
"capture a thought" — and `memex:run` reads the matching procedure
file and follows it.

## Procedures

| Procedure | Path | Purpose |
|---|---|---|
| memex:brain:ingest | internal/brain/ingest/SKILL.md | Add an external article (with hash-based rerun safety) |
| memex:brain:ask | internal/brain/ask/SKILL.md | Natural-language query, ranked results |
| memex:brain:capture | internal/brain/capture/SKILL.md | Free-form note |
| memex:brain:lint | internal/brain/lint/SKILL.md | Data Steward audit scoped to Brain |
| memex:brain:synthesize | internal/brain/synthesize/SKILL.md | Multi-source synthesis with provenance |

## Storage

`~/.memex/article.db` with three tables:
- `articles` — external sources, with `source_hash` + `raw_path`
- `captures` — free-form notes
- `syntheses` — generated synthesis documents with `inputs_json` provenance

All routed through the Librarian on write; through the Reference
Librarian on read.

## Onboarding

First Brain invocation triggers a one-time prompt to register the
human user as an agent. Subsequent invocations skip onboarding.

## Acceptance criteria

1. `pytest tests/` 100% green.
2. `install.run()` creates article.db.
3. First brain.ingest without registered human triggers onboarding.
4. brain.ingest is idempotent on identical content.
5. brain.ask returns results from index.db.
6. brain.synthesize produces a syntheses row with inputs_json provenance.
7. brain.lint generates an audit report.

## What Plan 3 ships beyond what brainstorming committed to

Adds `data_steward.reconcile_orphan` (was deferred from Plan 2).
```

- [ ] **Step 4: Run tests to verify they pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/BRAIN.md tests/test_brain_docs.py
git commit -m "docs(brain): Plan 3 acceptance criteria"
```

---

## Plan 3 acceptance checklist

- [ ] `pytest tests/` 100% green
- [ ] `install.run()` creates and registers article.db
- [ ] Onboarding flow registers a human agent on first invocation
- [ ] All 5 Brain procedures functional with mocked LLM, present at `internal/brain/<name>/SKILL.md`
- [ ] reconcile-orphan supports delete-index and note actions
- [ ] `skills/run/SKILL.md` contains user-facing intent routing for all 5 Brain procedures
- [ ] `plugin.json` still registers only `memex:run` (per spec §8.0) — no per-Brain skill entries

Plan 4 (Packaging) provides the install scripts, v1 plugin migration, and user-facing docs.
