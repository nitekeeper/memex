# Memex v2 — Plan 1: Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Memex Core — the CRUD substrate that provisions and hosts SQLite stores, with WAL discipline, a universal migrations tracker, an agent/role registry, and a registry of stores. Standalone usable: at the end of Plan 1, an agent can create stores, register agents, and read/write rows.

**Architecture:** A small Python package under `scripts/` with stateless CRUD modules (one per table), a thin `db.py` connection layer that enforces WAL pragmas on every connection, a `stores.py` provisioning module that runs consumer-supplied `.sql` migrations, and an `install.py` bootstrap that initializes `~/.memex/`. Skills under `skills/core/*` are thin SKILL.md wrappers over Python CLI invocations.

**Tech Stack:** Python 3.10+ (stdlib only — `sqlite3`, `json`, `pathlib`, `argparse`, `uuid`), pytest for tests, Claude Code plugin manifest for skill registration.

**Reference:** spec at `docs/specs/2026-05-16-memex-v2-redesign-design.md` (sections §3, §4, §5.1, §5.4, §8.1, §9.1, §11).

---

## File Structure

```
memex/
├── pyproject.toml                          # NEW: Python package config
├── scripts/
│   ├── __init__.py                         # NEW
│   ├── db.py                               # NEW: connection helpers, pragmas
│   ├── registry.py                         # NEW: store registry CRUD
│   ├── roles.py                            # NEW: roles CRUD (Atelier pattern)
│   ├── agents.py                           # NEW: agents CRUD
│   ├── stores.py                           # NEW: create-store, migrate, query, insert, update, delete
│   └── install.py                          # NEW: ~/.memex/ bootstrap
├── db/
│   ├── agents.sql                          # NEW: agents.db schema (roles + agents tables)
│   └── migrations_table.sql                # NEW: universal migrations table snippet
├── skills/
│   └── core/
│       ├── create-store/SKILL.md           # NEW
│       ├── migrate/SKILL.md                # NEW
│       ├── query/SKILL.md                  # NEW
│       ├── insert/SKILL.md                 # NEW
│       ├── update/SKILL.md                 # NEW
│       ├── delete/SKILL.md                 # NEW
│       ├── list-stores/SKILL.md            # NEW
│       ├── register-role/SKILL.md          # NEW
│       ├── register-agent/SKILL.md         # NEW
│       └── get-agent/SKILL.md              # NEW
├── tests/
│   ├── __init__.py                         # NEW
│   ├── conftest.py                         # NEW: shared fixtures
│   ├── test_db.py                          # NEW
│   ├── test_registry.py                    # NEW
│   ├── test_roles.py                       # NEW
│   ├── test_agents.py                      # NEW
│   ├── test_stores_create.py               # NEW
│   ├── test_stores_migrate.py              # NEW
│   ├── test_stores_crud.py                 # NEW
│   ├── test_install.py                     # NEW
│   └── test_smoke.py                       # NEW: end-to-end
└── plugin.json                             # MODIFY (or CREATE): plugin manifest
```

**Module boundaries:**
- `db.py` — connection helpers only. Knows pragmas. Knows nothing about schema.
- `registry.py` — store registry only. CRUD on `~/.memex/registry.json` (or `registry.db`).
- `roles.py`, `agents.py` — table-scoped CRUD. Mirror Atelier's `roles.py` pattern (stateless, dict returns, CLI entry).
- `stores.py` — provisioning and generic CRUD over any registered store.
- `install.py` — one-shot bootstrap. Creates `~/.memex/`, seeds the 5 internal roles+agents.
- Skills are thin wrappers; all logic lives in scripts.

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `scripts/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the failing test**

`tests/conftest.py`:

```python
import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def tmp_memex_home(monkeypatch, tmp_path):
    """Isolated ~/.memex/ root for tests."""
    home = tmp_path / "memex_home"
    home.mkdir()
    monkeypatch.setenv("MEMEX_HOME", str(home))
    return home


@pytest.fixture
def tmp_store_path(tmp_path):
    """Disposable SQLite store path."""
    return tmp_path / "store.db"
```

`tests/test_db.py`:

```python
from scripts import db


def test_module_importable():
    assert hasattr(db, "get_connection")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL with `AttributeError: module 'scripts.db' has no attribute 'get_connection'` (since `db.py` doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:

```toml
[project]
name = "memex"
version = "2.0.0-dev"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`scripts/__init__.py`: (empty)

`tests/__init__.py`: (empty)

`scripts/db.py`:

```python
def get_connection():
    raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py::test_module_importable -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml scripts/__init__.py scripts/db.py tests/__init__.py tests/conftest.py tests/test_db.py
git commit -m "chore: scaffold Memex Core Python package"
```

---

## Task 2: `db.py` — connection with WAL pragmas

**Files:**
- Modify: `scripts/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db.py`:

```python
import sqlite3
from scripts.db import get_connection


def test_get_connection_returns_sqlite_connection(tmp_store_path):
    conn = get_connection(str(tmp_store_path))
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_get_connection_enables_wal(tmp_store_path):
    conn = get_connection(str(tmp_store_path))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()


def test_get_connection_synchronous_normal(tmp_store_path):
    conn = get_connection(str(tmp_store_path))
    val = conn.execute("PRAGMA synchronous").fetchone()[0]
    # NORMAL = 1
    assert val == 1
    conn.close()


def test_get_connection_foreign_keys_on(tmp_store_path):
    conn = get_connection(str(tmp_store_path))
    val = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert val == 1
    conn.close()


def test_get_connection_returns_dict_rows(tmp_store_path):
    conn = get_connection(str(tmp_store_path))
    conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'x')")
    row = conn.execute("SELECT * FROM t").fetchone()
    assert row["a"] == 1
    assert row["b"] == "x"
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: All four tests FAIL (NotImplementedError or AttributeError).

- [ ] **Step 3: Write minimal implementation**

Replace `scripts/db.py`:

```python
"""Connection helpers with Memex-standard pragmas."""
from __future__ import annotations
import sqlite3
from pathlib import Path


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with Memex pragmas applied.

    Pragmas:
      - journal_mode = WAL
      - synchronous  = NORMAL
      - foreign_keys = ON
      - temp_store   = MEMORY

    Returns a connection with row_factory set to sqlite3.Row (dict-like access).
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/db.py tests/test_db.py
git commit -m "feat(core): db.get_connection with WAL + synchronous=NORMAL + FK enforcement"
```

---

## Task 3: `db.py` — `MEMEX_HOME` resolver

**Files:**
- Modify: `scripts/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db.py`:

```python
from scripts.db import memex_home


def test_memex_home_respects_env(tmp_memex_home):
    assert memex_home() == tmp_memex_home


def test_memex_home_defaults_to_user_home(monkeypatch, tmp_path):
    monkeypatch.delenv("MEMEX_HOME", raising=False)
    fake_home = tmp_path / "userhome"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows
    assert memex_home() == fake_home / ".memex"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py::test_memex_home_respects_env -v`
Expected: FAIL with `ImportError: cannot import name 'memex_home'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/db.py`:

```python
import os


def memex_home() -> Path:
    """Resolve the Memex home directory.

    Order: $MEMEX_HOME if set, else $HOME/.memex (POSIX) or
    $USERPROFILE/.memex (Windows).
    """
    explicit = os.environ.get("MEMEX_HOME")
    if explicit:
        return Path(explicit)
    user_home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if not user_home:
        raise RuntimeError("Cannot resolve user home directory")
    return Path(user_home) / ".memex"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/db.py tests/test_db.py
git commit -m "feat(core): db.memex_home resolver with MEMEX_HOME override"
```

---

## Task 4: Universal `migrations` table snippet

**Files:**
- Create: `db/migrations_table.sql`

- [ ] **Step 1: Write the failing test**

Create `tests/test_migrations_snippet.py`:

```python
from pathlib import Path


def test_migrations_snippet_exists():
    p = Path("db/migrations_table.sql")
    assert p.exists()


def test_migrations_snippet_uses_if_not_exists():
    sql = Path("db/migrations_table.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS migrations" in sql


def test_migrations_snippet_columns():
    sql = Path("db/migrations_table.sql").read_text()
    for col in ("filename", "applied_at"):
        assert col in sql
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_migrations_snippet.py -v`
Expected: FAIL (file does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `db/migrations_table.sql`:

```sql
-- Universal migrations tracker. Memex DBA injects this into every store
-- BEFORE running consumer-supplied migrations. IF NOT EXISTS makes consumer
-- migrations that declare their own `migrations` table a safe no-op
-- (provided they also use IF NOT EXISTS).
CREATE TABLE IF NOT EXISTS migrations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL UNIQUE,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_migrations_snippet.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add db/migrations_table.sql tests/test_migrations_snippet.py
git commit -m "feat(core): universal migrations tracker SQL snippet"
```

---

## Task 5: `agents.db` schema (roles + agents tables)

**Files:**
- Create: `db/agents.sql`

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents_schema.py`:

```python
import sqlite3
from pathlib import Path
from scripts.db import get_connection


def test_agents_schema_applies_cleanly(tmp_store_path):
    sql = Path("db/agents.sql").read_text()
    conn = get_connection(str(tmp_store_path))
    conn.executescript(sql)
    conn.commit()
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "roles" in tables
    assert "agents" in tables
    conn.close()


def test_agents_role_fk_enforced(tmp_store_path):
    sql = Path("db/agents.sql").read_text()
    conn = get_connection(str(tmp_store_path))
    conn.executescript(sql)
    # Insert an agent referencing a nonexistent role_id — should raise IntegrityError.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO agents (id, name, role_id, profile) VALUES (?, ?, ?, ?)",
            ("a1", "x", 999, "profile")
        )
        conn.commit()
    conn.close()
```

Add `import pytest` at top of the test file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_agents_schema.py -v`
Expected: FAIL (file does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `db/agents.sql`:

```sql
-- agents.db: universal role and agent registry.
-- Memex seeds 5 internal roles+agents on install (see install.py).
-- Consumers (Atelier, etc.) append their own.

CREATE TABLE IF NOT EXISTS roles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    description  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agents (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    role_id      INTEGER NOT NULL REFERENCES roles(id),
    profile      TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS agents_role_idx ON agents(role_id);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_agents_schema.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add db/agents.sql tests/test_agents_schema.py
git commit -m "feat(core): agents.db schema (roles + agents) with FK"
```

---

## Task 6: `roles.py` CRUD module

**Files:**
- Create: `scripts/roles.py`
- Create: `tests/test_roles.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_roles.py`:

```python
import pytest
from pathlib import Path
from scripts.db import get_connection
from scripts import roles


@pytest.fixture
def agents_db(tmp_path):
    """Disposable agents.db with schema applied."""
    p = tmp_path / "agents.db"
    sql = Path("db/agents.sql").read_text()
    conn = get_connection(str(p))
    conn.executescript(sql)
    conn.commit()
    conn.close()
    return str(p)


def test_create_role(agents_db):
    r = roles.create_role(agents_db, "Librarian", "Indexing authority")
    assert r["id"] > 0
    assert r["name"] == "Librarian"
    assert r["description"] == "Indexing authority"


def test_get_role(agents_db):
    created = roles.create_role(agents_db, "Archivist", "Custodian of history")
    fetched = roles.get_role(agents_db, created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["name"] == "Archivist"


def test_get_role_returns_none_when_missing(agents_db):
    assert roles.get_role(agents_db, 9999) is None


def test_list_roles_orders_by_name(agents_db):
    roles.create_role(agents_db, "Zeta", "z")
    roles.create_role(agents_db, "Alpha", "a")
    roles.create_role(agents_db, "Mu", "m")
    listed = roles.list_roles(agents_db)
    assert [r["name"] for r in listed] == ["Alpha", "Mu", "Zeta"]


def test_search_roles_matches_name_or_description(agents_db):
    roles.create_role(agents_db, "Librarian", "catalogs documents")
    roles.create_role(agents_db, "Archivist", "preserves history")
    results = roles.search_roles(agents_db, "catalog")
    assert len(results) == 1
    assert results[0]["name"] == "Librarian"


def test_update_role_partial(agents_db):
    r = roles.create_role(agents_db, "X", "original")
    roles.update_role(agents_db, r["id"], description="updated")
    fetched = roles.get_role(agents_db, r["id"])
    assert fetched["description"] == "updated"
    assert fetched["name"] == "X"  # unchanged


def test_delete_role(agents_db):
    r = roles.create_role(agents_db, "X", "y")
    assert roles.delete_role(agents_db, r["id"]) is True
    assert roles.get_role(agents_db, r["id"]) is None


def test_delete_role_returns_false_when_missing(agents_db):
    assert roles.delete_role(agents_db, 9999) is False


def test_create_role_unique_name_raises(agents_db):
    import sqlite3
    roles.create_role(agents_db, "Duplicate", "first")
    with pytest.raises(sqlite3.IntegrityError):
        roles.create_role(agents_db, "Duplicate", "second")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_roles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.roles'`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/roles.py`:

```python
"""roles table CRUD. Pattern mirrors Atelier's scripts/roles.py."""
from __future__ import annotations
from datetime import datetime, timezone
from scripts.db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(cursor, row):
    return dict(zip([col[0] for col in cursor.description], row))


def create_role(db_path: str, name: str, description: str) -> dict:
    conn = get_connection(db_path)
    now = _now()
    cur = conn.execute(
        "INSERT INTO roles (name, description, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        (name, description, now, now),
    )
    conn.commit()
    role_id = cur.lastrowid
    conn.close()
    return get_role(db_path, role_id)


def get_role(db_path: str, role_id: int) -> dict | None:
    conn = get_connection(db_path)
    cur = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def list_roles(db_path: str) -> list[dict]:
    conn = get_connection(db_path)
    cur = conn.execute("SELECT * FROM roles ORDER BY name")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def search_roles(db_path: str, query: str) -> list[dict]:
    pattern = f"%{query}%"
    conn = get_connection(db_path)
    cur = conn.execute(
        "SELECT * FROM roles WHERE name LIKE ? OR description LIKE ? ORDER BY name",
        (pattern, pattern),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_role(db_path: str, role_id: int, **kwargs) -> dict | None:
    allowed = {"name", "description"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_role(db_path, role_id)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn = get_connection(db_path)
    conn.execute(
        f"UPDATE roles SET {set_clause} WHERE id = ?",
        (*updates.values(), role_id),
    )
    conn.commit()
    conn.close()
    return get_role(db_path, role_id)


def delete_role(db_path: str, role_id: int) -> bool:
    conn = get_connection(db_path)
    cur = conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


if __name__ == "__main__":
    import sys
    import json
    from scripts.db import memex_home

    db_path = str(memex_home() / "agents.db")
    cmd = sys.argv[1]

    if cmd == "create":
        print(json.dumps(create_role(db_path, sys.argv[2], sys.argv[3]), indent=2))
    elif cmd == "get":
        result = get_role(db_path, int(sys.argv[2]))
        print(json.dumps(result, indent=2) if result else "Not found")
    elif cmd == "list":
        print(json.dumps(list_roles(db_path), indent=2))
    elif cmd == "search":
        print(json.dumps(search_roles(db_path, sys.argv[2]), indent=2))
    elif cmd == "delete":
        print("Deleted" if delete_role(db_path, int(sys.argv[2])) else "Not found")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_roles.py -v`
Expected: 9 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/roles.py tests/test_roles.py
git commit -m "feat(core): roles CRUD module + CLI"
```

---

## Task 7: `agents.py` CRUD module

**Files:**
- Create: `scripts/agents.py`
- Create: `tests/test_agents.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents.py`:

```python
import pytest
from pathlib import Path
from scripts.db import get_connection
from scripts import roles, agents


@pytest.fixture
def agents_db_with_role(tmp_path):
    p = tmp_path / "agents.db"
    sql = Path("db/agents.sql").read_text()
    conn = get_connection(str(p))
    conn.executescript(sql)
    conn.commit()
    conn.close()
    role = roles.create_role(str(p), "Librarian", "Indexing authority")
    return str(p), role["id"]


def test_create_agent(agents_db_with_role):
    db, role_id = agents_db_with_role
    a = agents.create_agent(db, "lib-1", "Dr. Test", role_id, "profile text")
    assert a["id"] == "lib-1"
    assert a["name"] == "Dr. Test"
    assert a["role_id"] == role_id
    assert a["profile"] == "profile text"


def test_get_agent(agents_db_with_role):
    db, role_id = agents_db_with_role
    agents.create_agent(db, "lib-1", "X", role_id, "p")
    a = agents.get_agent(db, "lib-1")
    assert a["name"] == "X"


def test_get_agent_returns_none_when_missing(agents_db_with_role):
    db, _ = agents_db_with_role
    assert agents.get_agent(db, "nope") is None


def test_list_agents_ordered_by_id(agents_db_with_role):
    db, role_id = agents_db_with_role
    agents.create_agent(db, "z", "Z", role_id, "p")
    agents.create_agent(db, "a", "A", role_id, "p")
    listed = agents.list_agents(db)
    assert [a["id"] for a in listed] == ["a", "z"]


def test_update_agent_profile(agents_db_with_role):
    db, role_id = agents_db_with_role
    agents.create_agent(db, "lib-1", "X", role_id, "original")
    agents.update_agent(db, "lib-1", profile="updated")
    a = agents.get_agent(db, "lib-1")
    assert a["profile"] == "updated"


def test_delete_agent(agents_db_with_role):
    db, role_id = agents_db_with_role
    agents.create_agent(db, "lib-1", "X", role_id, "p")
    assert agents.delete_agent(db, "lib-1") is True
    assert agents.get_agent(db, "lib-1") is None


def test_create_agent_requires_valid_role(agents_db_with_role):
    import sqlite3
    db, _ = agents_db_with_role
    with pytest.raises(sqlite3.IntegrityError):
        agents.create_agent(db, "x", "X", 99999, "p")


def test_list_by_role(agents_db_with_role):
    db, role_id = agents_db_with_role
    other_role = roles.create_role(db, "Other", "x")
    agents.create_agent(db, "a", "A", role_id, "p")
    agents.create_agent(db, "b", "B", other_role["id"], "p")
    listed = agents.list_by_role(db, role_id)
    assert [a["id"] for a in listed] == ["a"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_agents.py -v`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/agents.py`:

```python
"""agents table CRUD. Pattern mirrors roles.py."""
from __future__ import annotations
from datetime import datetime, timezone
from scripts.db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_agent(db_path: str, agent_id: str, name: str, role_id: int, profile: str) -> dict:
    conn = get_connection(db_path)
    now = _now()
    conn.execute(
        "INSERT INTO agents (id, name, role_id, profile, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (agent_id, name, role_id, profile, now, now),
    )
    conn.commit()
    conn.close()
    return get_agent(db_path, agent_id)


def get_agent(db_path: str, agent_id: str) -> dict | None:
    conn = get_connection(db_path)
    cur = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def list_agents(db_path: str) -> list[dict]:
    conn = get_connection(db_path)
    cur = conn.execute("SELECT * FROM agents ORDER BY id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def list_by_role(db_path: str, role_id: int) -> list[dict]:
    conn = get_connection(db_path)
    cur = conn.execute(
        "SELECT * FROM agents WHERE role_id = ? ORDER BY id", (role_id,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_agent(db_path: str, agent_id: str, **kwargs) -> dict | None:
    allowed = {"name", "role_id", "profile"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_agent(db_path, agent_id)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn = get_connection(db_path)
    conn.execute(
        f"UPDATE agents SET {set_clause} WHERE id = ?",
        (*updates.values(), agent_id),
    )
    conn.commit()
    conn.close()
    return get_agent(db_path, agent_id)


def delete_agent(db_path: str, agent_id: str) -> bool:
    conn = get_connection(db_path)
    cur = conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


if __name__ == "__main__":
    import sys
    import json
    from scripts.db import memex_home

    db_path = str(memex_home() / "agents.db")
    cmd = sys.argv[1]

    if cmd == "create":
        print(json.dumps(
            create_agent(db_path, sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]),
            indent=2,
        ))
    elif cmd == "get":
        result = get_agent(db_path, sys.argv[2])
        print(json.dumps(result, indent=2) if result else "Not found")
    elif cmd == "list":
        print(json.dumps(list_agents(db_path), indent=2))
    elif cmd == "delete":
        print("Deleted" if delete_agent(db_path, sys.argv[2]) else "Not found")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_agents.py -v`
Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/agents.py tests/test_agents.py
git commit -m "feat(core): agents CRUD module + CLI"
```

---

## Task 8: `registry.py` — store registry

**Files:**
- Create: `scripts/registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry.py`:

```python
import json
import pytest
from scripts import registry


def test_register_store(tmp_memex_home):
    registry.register_store("alpha", "/abs/path/alpha.db", schema_version="v1")
    listed = registry.list_stores()
    assert any(s["name"] == "alpha" for s in listed)


def test_get_store_returns_dict(tmp_memex_home):
    registry.register_store("alpha", "/abs/path/alpha.db", schema_version="v1")
    s = registry.get_store("alpha")
    assert s["name"] == "alpha"
    assert s["path"] == "/abs/path/alpha.db"
    assert s["schema_version"] == "v1"


def test_get_store_returns_none_when_missing(tmp_memex_home):
    assert registry.get_store("nope") is None


def test_register_duplicate_raises(tmp_memex_home):
    registry.register_store("alpha", "/p1", "v1")
    with pytest.raises(ValueError):
        registry.register_store("alpha", "/p2", "v1")


def test_unregister_store(tmp_memex_home):
    registry.register_store("alpha", "/p1", "v1")
    assert registry.unregister_store("alpha") is True
    assert registry.get_store("alpha") is None


def test_registry_persists_as_json(tmp_memex_home):
    registry.register_store("alpha", "/p", "v1")
    raw = (tmp_memex_home / "registry.json").read_text()
    data = json.loads(raw)
    assert "alpha" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_registry.py -v`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/registry.py`:

```python
"""Store registry: maps store names → absolute paths + schema version.

Backed by ~/.memex/registry.json. Single-process write semantics
(short JSON read-modify-write; no inter-process locking in v2.0).
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from scripts.db import memex_home


def _registry_path() -> Path:
    return memex_home() / "registry.json"


def _load() -> dict:
    p = _registry_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _save(data: dict) -> None:
    p = _registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def register_store(name: str, path: str, schema_version: str) -> dict:
    """Add a store to the registry. Raises ValueError if name exists."""
    data = _load()
    if name in data:
        raise ValueError(f"Store already registered: {name}")
    record = {
        "name": name,
        "path": path,
        "schema_version": schema_version,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    data[name] = record
    _save(data)
    return record


def get_store(name: str) -> dict | None:
    return _load().get(name)


def list_stores() -> list[dict]:
    return list(_load().values())


def unregister_store(name: str) -> bool:
    data = _load()
    if name not in data:
        return False
    del data[name]
    _save(data)
    return True


def update_schema_version(name: str, new_version: str) -> dict | None:
    data = _load()
    if name not in data:
        return None
    data[name]["schema_version"] = new_version
    _save(data)
    return data[name]


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1]

    if cmd == "register":
        print(json.dumps(register_store(sys.argv[2], sys.argv[3], sys.argv[4]), indent=2))
    elif cmd == "get":
        result = get_store(sys.argv[2])
        print(json.dumps(result, indent=2) if result else "Not found")
    elif cmd == "list":
        print(json.dumps(list_stores(), indent=2))
    elif cmd == "unregister":
        print("Removed" if unregister_store(sys.argv[2]) else "Not found")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_registry.py -v`
Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/registry.py tests/test_registry.py
git commit -m "feat(core): store registry persisted as ~/.memex/registry.json"
```

---

## Task 9: `stores.py` — create_store

**Files:**
- Create: `scripts/stores.py`
- Create: `tests/test_stores_create.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_stores_create.py`:

```python
import pytest
from pathlib import Path
from scripts import stores, registry
from scripts.db import get_connection


def test_create_store_creates_file(tmp_memex_home, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text("CREATE TABLE t (a INTEGER);")

    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))

    assert target.exists()


def test_create_store_runs_migrations(tmp_memex_home, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text("CREATE TABLE t (a INTEGER, b TEXT);")

    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))

    conn = get_connection(str(target))
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "t" in tables
    assert "migrations" in tables


def test_create_store_records_applied_migrations(tmp_memex_home, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text("CREATE TABLE t (a INTEGER);")
    (migrations_dir / "002_more.sql").write_text("CREATE TABLE u (b TEXT);")

    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))

    conn = get_connection(str(target))
    applied = [r["filename"] for r in conn.execute("SELECT filename FROM migrations ORDER BY filename")]
    conn.close()
    assert applied == ["001_init.sql", "002_more.sql"]


def test_create_store_registers_in_registry(tmp_memex_home, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text("CREATE TABLE t (a INTEGER);")

    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))

    rec = registry.get_store("alpha")
    assert rec is not None
    assert rec["path"] == str(target)


def test_create_store_refuses_existing_name(tmp_memex_home, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text("CREATE TABLE t (a INTEGER);")

    stores.create_store("alpha", str(tmp_path / "a.db"), str(migrations_dir))
    with pytest.raises(ValueError):
        stores.create_store("alpha", str(tmp_path / "b.db"), str(migrations_dir))


def test_create_store_applies_migrations_in_lexical_order(tmp_memex_home, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    # Filenames intentionally out of insertion order; lexical sort should fix.
    (migrations_dir / "002_second.sql").write_text("CREATE TABLE b (x INTEGER);")
    (migrations_dir / "001_first.sql").write_text("CREATE TABLE a (x INTEGER);")
    (migrations_dir / "003_third.sql").write_text("ALTER TABLE a ADD COLUMN y TEXT;")

    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))

    conn = get_connection(str(target))
    applied = [r["filename"] for r in conn.execute("SELECT filename FROM migrations ORDER BY id")]
    conn.close()
    assert applied == ["001_first.sql", "002_second.sql", "003_third.sql"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stores_create.py -v`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/stores.py`:

```python
"""Store provisioning and generic CRUD.

create_store: provision a new SQLite file, install the universal
`migrations` table, apply consumer-supplied SQL migration files in
lexical order, register the store in the global registry.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from scripts.db import get_connection
from scripts import registry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrations_table_sql() -> str:
    return Path("db/migrations_table.sql").read_text()


def create_store(name: str, path: str, migrations_dir: str, schema_version: str = "v1") -> dict:
    """Create a new SQLite store and register it.

    Steps:
      1. Open connection (DBA pragmas applied).
      2. Install universal `migrations` table.
      3. Run each .sql file in migrations_dir in lexical order.
      4. Record each as applied.
      5. Register in global registry.
    """
    if registry.get_store(name) is not None:
        raise ValueError(f"Store already registered: {name}")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(path)

    # Step 1+2: universal migrations table.
    conn.executescript(_migrations_table_sql())
    conn.commit()

    # Step 3+4: apply migrations in lexical order.
    sql_files = sorted(Path(migrations_dir).glob("*.sql"))
    for sql_file in sql_files:
        conn.executescript(sql_file.read_text())
        conn.execute(
            "INSERT INTO migrations (filename, applied_at) VALUES (?, ?)",
            (sql_file.name, _now()),
        )
    conn.commit()
    conn.close()

    # Step 5: register.
    return registry.register_store(name, path, schema_version)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stores_create.py -v`
Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/stores.py tests/test_stores_create.py
git commit -m "feat(core): stores.create_store with migration application + registry"
```

---

## Task 10: `stores.py` — migrate (additive)

**Files:**
- Modify: `scripts/stores.py`
- Create: `tests/test_stores_migrate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_stores_migrate.py`:

```python
import pytest
from pathlib import Path
from scripts import stores
from scripts.db import get_connection


def _make_store(tmp_memex_home, tmp_path, initial_sql="CREATE TABLE t (a INTEGER);"):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text(initial_sql)
    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))
    return target, migrations_dir


def test_migrate_applies_new_files(tmp_memex_home, tmp_path):
    target, migrations_dir = _make_store(tmp_memex_home, tmp_path)
    (migrations_dir / "002_added.sql").write_text("CREATE TABLE u (b TEXT);")

    stores.migrate("alpha", str(migrations_dir))

    conn = get_connection(str(target))
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "u" in tables


def test_migrate_skips_already_applied(tmp_memex_home, tmp_path):
    target, migrations_dir = _make_store(tmp_memex_home, tmp_path)
    # Calling migrate with no new files should be a no-op.
    stores.migrate("alpha", str(migrations_dir))

    conn = get_connection(str(target))
    applied = [r["filename"] for r in conn.execute("SELECT filename FROM migrations ORDER BY id")]
    conn.close()
    assert applied == ["001_init.sql"]


def test_migrate_idempotent(tmp_memex_home, tmp_path):
    target, migrations_dir = _make_store(tmp_memex_home, tmp_path)
    (migrations_dir / "002_added.sql").write_text("CREATE TABLE u (b TEXT);")

    stores.migrate("alpha", str(migrations_dir))
    stores.migrate("alpha", str(migrations_dir))  # second run

    conn = get_connection(str(target))
    rows = conn.execute("SELECT COUNT(*) AS n FROM migrations").fetchone()
    conn.close()
    assert rows["n"] == 2  # 001 + 002, not 4


def test_migrate_unknown_store_raises(tmp_memex_home, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    with pytest.raises(ValueError):
        stores.migrate("does-not-exist", str(migrations_dir))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stores_migrate.py -v`
Expected: FAIL (`migrate` not defined).

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/stores.py`:

```python
def migrate(name: str, migrations_dir: str) -> list[str]:
    """Apply unapplied .sql files from migrations_dir to a registered store.

    Returns the list of newly-applied filenames.
    """
    rec = registry.get_store(name)
    if rec is None:
        raise ValueError(f"Unknown store: {name}")

    conn = get_connection(rec["path"])
    applied_set = {
        r["filename"] for r in conn.execute("SELECT filename FROM migrations")
    }

    sql_files = sorted(Path(migrations_dir).glob("*.sql"))
    newly_applied: list[str] = []
    for sql_file in sql_files:
        if sql_file.name in applied_set:
            continue
        conn.executescript(sql_file.read_text())
        conn.execute(
            "INSERT INTO migrations (filename, applied_at) VALUES (?, ?)",
            (sql_file.name, _now()),
        )
        newly_applied.append(sql_file.name)
    conn.commit()
    conn.close()
    return newly_applied
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stores_migrate.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/stores.py tests/test_stores_migrate.py
git commit -m "feat(core): stores.migrate applies unapplied migrations idempotently"
```

---

## Task 11: `stores.py` — generic CRUD (query, insert, update, delete)

**Files:**
- Modify: `scripts/stores.py`
- Create: `tests/test_stores_crud.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_stores_crud.py`:

```python
import pytest
from pathlib import Path
from scripts import stores
from scripts.db import get_connection


@pytest.fixture
def store_with_table(tmp_memex_home, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text(
        "CREATE TABLE items ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL, "
        "qty INTEGER NOT NULL DEFAULT 0"
        ");"
    )
    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))
    return "alpha"


def test_insert_returns_row_with_id(store_with_table):
    row = stores.insert(store_with_table, "items", {"name": "widget", "qty": 5})
    assert row["id"] > 0
    assert row["name"] == "widget"
    assert row["qty"] == 5


def test_query_returns_list_of_dicts(store_with_table):
    stores.insert(store_with_table, "items", {"name": "a", "qty": 1})
    stores.insert(store_with_table, "items", {"name": "b", "qty": 2})

    rows = stores.query(store_with_table, "SELECT * FROM items ORDER BY name")
    assert len(rows) == 2
    assert rows[0]["name"] == "a"


def test_query_supports_params(store_with_table):
    stores.insert(store_with_table, "items", {"name": "a", "qty": 1})
    stores.insert(store_with_table, "items", {"name": "b", "qty": 99})

    rows = stores.query(store_with_table, "SELECT * FROM items WHERE qty > ?", (50,))
    assert len(rows) == 1
    assert rows[0]["name"] == "b"


def test_update_changes_rows(store_with_table):
    row = stores.insert(store_with_table, "items", {"name": "a", "qty": 1})
    stores.update(store_with_table, "items", row["id"], {"qty": 99})

    refetched = stores.query(store_with_table, "SELECT * FROM items WHERE id = ?", (row["id"],))
    assert refetched[0]["qty"] == 99


def test_delete_removes_row(store_with_table):
    row = stores.insert(store_with_table, "items", {"name": "a", "qty": 1})
    assert stores.delete(store_with_table, "items", row["id"]) is True

    refetched = stores.query(store_with_table, "SELECT * FROM items WHERE id = ?", (row["id"],))
    assert refetched == []


def test_delete_returns_false_when_missing(store_with_table):
    assert stores.delete(store_with_table, "items", 99999) is False


def test_query_unknown_store_raises(tmp_memex_home):
    with pytest.raises(ValueError):
        stores.query("no-such-store", "SELECT 1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stores_crud.py -v`
Expected: FAIL (functions not defined).

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/stores.py`:

```python
def _resolve(name: str) -> str:
    rec = registry.get_store(name)
    if rec is None:
        raise ValueError(f"Unknown store: {name}")
    return rec["path"]


def query(name: str, sql: str, params: tuple = ()) -> list[dict]:
    """Execute SELECT against a registered store. Returns list of dict rows."""
    conn = get_connection(_resolve(name))
    cur = conn.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def insert(name: str, table: str, row: dict) -> dict:
    """Insert a row. Returns the inserted row (including the new PK).

    Assumes the table has an integer PRIMARY KEY AUTOINCREMENT column
    named `id`. For tables with TEXT PKs (like `agents`), the caller
    supplies `id` in `row` and we return the same row.
    """
    cols = list(row.keys())
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    conn = get_connection(_resolve(name))
    cur = conn.execute(
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
        tuple(row[c] for c in cols),
    )
    conn.commit()
    new_id = row.get("id", cur.lastrowid)
    pk_col = "id"
    fetched = conn.execute(f"SELECT * FROM {table} WHERE {pk_col} = ?", (new_id,)).fetchone()
    conn.close()
    return dict(fetched) if fetched else row


def update(name: str, table: str, row_id, updates: dict) -> dict | None:
    if not updates:
        return None
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn = get_connection(_resolve(name))
    conn.execute(
        f"UPDATE {table} SET {set_clause} WHERE id = ?",
        (*updates.values(), row_id),
    )
    conn.commit()
    fetched = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    return dict(fetched) if fetched else None


def delete(name: str, table: str, row_id) -> bool:
    conn = get_connection(_resolve(name))
    cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stores_crud.py -v`
Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/stores.py tests/test_stores_crud.py
git commit -m "feat(core): stores.query/insert/update/delete generic CRUD primitives"
```

---

## Task 12: `install.py` — `~/.memex/` bootstrap

**Files:**
- Create: `scripts/install.py`
- Create: `tests/test_install.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_install.py`:

```python
import pytest
from scripts import install, registry, roles, agents
from scripts.db import memex_home


def test_install_creates_memex_home(tmp_memex_home):
    install.run()
    assert memex_home().is_dir()
    assert (memex_home() / "agents.db").exists()
    assert (memex_home() / "raw").is_dir()
    assert (memex_home() / "backups").is_dir()
    assert (memex_home() / "audits").is_dir()


def test_install_registers_agents_db(tmp_memex_home):
    install.run()
    rec = registry.get_store("agents")
    assert rec is not None


def test_install_idempotent(tmp_memex_home):
    install.run()
    install.run()  # second call must not error
    rec = registry.get_store("agents")
    assert rec is not None


def test_install_does_not_seed_internal_agents_in_core(tmp_memex_home):
    """Plan 1 (Core) does NOT seed the 5 Memex internal agents.
    That happens in Plan 2 (Index + agents).
    Core only sets up infrastructure.
    """
    install.run()
    agents_db = str(memex_home() / "agents.db")
    listed = roles.list_roles(agents_db)
    # Core install creates the schema but seeds nothing yet.
    assert listed == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_install.py -v`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/install.py`:

```python
"""One-shot ~/.memex/ bootstrap.

Plan 1 scope: creates directory tree, agents.db (schema only), registers
agents.db in the registry. Does NOT seed internal agent profiles — that
is Plan 2's responsibility.
"""
from __future__ import annotations
from pathlib import Path
from scripts.db import get_connection, memex_home
from scripts import registry


def run() -> None:
    home = memex_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "raw").mkdir(exist_ok=True)
    (home / "backups").mkdir(exist_ok=True)
    (home / "audits").mkdir(exist_ok=True)
    (home / "templates").mkdir(exist_ok=True)

    agents_db_path = home / "agents.db"
    agents_sql = Path("db/agents.sql").read_text()
    conn = get_connection(str(agents_db_path))
    conn.executescript(agents_sql)
    conn.commit()
    conn.close()

    if registry.get_store("agents") is None:
        registry.register_store("agents", str(agents_db_path), schema_version="v1")


if __name__ == "__main__":
    run()
    print(f"Memex Core installed at {memex_home()}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_install.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/install.py tests/test_install.py
git commit -m "feat(core): install.run bootstraps ~/.memex/ (no internal-agent seed yet)"
```

---

## Task 13: Skill — `memex:core:create-store`

**Files:**
- Create: `skills/core/create-store/SKILL.md`

- [ ] **Step 1: Write the failing test**

Create `tests/test_skills_present.py`:

```python
from pathlib import Path


def test_create_store_skill_exists():
    p = Path("skills/core/create-store/SKILL.md")
    assert p.exists()


def test_create_store_skill_has_frontmatter():
    content = Path("skills/core/create-store/SKILL.md").read_text()
    assert content.startswith("---")
    assert "name: memex:core:create-store" in content
    assert "description:" in content


def test_create_store_skill_references_stores_module():
    content = Path("skills/core/create-store/SKILL.md").read_text()
    assert "scripts/stores.py" in content or "scripts.stores" in content
    assert "create_store" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_skills_present.py -v`
Expected: FAIL (file does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `skills/core/create-store/SKILL.md`:

```markdown
---
name: memex:core:create-store
description: Create a new Memex-managed SQLite store from a directory of SQL migration files. Use when a consumer (Atelier, Brain, custom) needs a fresh project- or domain-scoped store. Memex creates the file with WAL pragmas, installs the universal migrations table, applies each .sql file in lexical order, and registers the store in the global registry.
---

# memex:core:create-store

## When to use

A consumer needs a new SQLite store provisioned. Typical callers:
- A workspace agent setting up `<repo>/.memex/store.db` for project work.
- An installer seeding a default store like `~/.memex/article.db`.
- A test fixture creating a disposable store.

## Inputs

- `name` — globally unique store name (e.g., `atelier-projectX`, `article`)
- `path` — absolute filesystem path for the new SQLite file
- `migrations_dir` — directory containing `.sql` migration files. Filenames sort lexically; conventional pattern is `001_<topic>.sql`, `002_<topic>.sql`, etc.

## What happens

1. Memex DBA opens a new SQLite connection at `path` with WAL + synchronous=NORMAL + foreign_keys=ON.
2. The universal `migrations` table is installed first (idempotent, `IF NOT EXISTS`).
3. Each `.sql` file in `migrations_dir` is applied in lexical order. Each file's `executescript` runs in a single transaction; if any statement fails, the whole call aborts and the partial state is rolled back.
4. Each successfully-applied file is recorded in the `migrations` table.
5. The store is registered in `~/.memex/registry.json` with its name, absolute path, and schema version (defaults to `v1`).

## Invocation

This skill calls `scripts/stores.py:create_store(name, path, migrations_dir)`.

CLI equivalent:

```bash
python -c "from scripts.stores import create_store; create_store('alpha', '/abs/path/alpha.db', '/abs/path/migrations/')"
```

## Errors

- `ValueError: Store already registered` — the `name` is already in the registry. Pick a different name or use `memex:core:migrate` to apply further migrations to the existing store.
- `sqlite3.OperationalError` — a migration file contains invalid SQL. The store is left in whatever partial state the failing executescript reached; recommend deleting the file and retrying.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_skills_present.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add skills/core/create-store/SKILL.md tests/test_skills_present.py
git commit -m "docs(core): SKILL.md for memex:core:create-store"
```

---

## Task 14: Skills — remaining 9 `memex:core:*` SKILL.md files

**Files:**
- Create: `skills/core/migrate/SKILL.md`
- Create: `skills/core/query/SKILL.md`
- Create: `skills/core/insert/SKILL.md`
- Create: `skills/core/update/SKILL.md`
- Create: `skills/core/delete/SKILL.md`
- Create: `skills/core/list-stores/SKILL.md`
- Create: `skills/core/register-role/SKILL.md`
- Create: `skills/core/register-agent/SKILL.md`
- Create: `skills/core/get-agent/SKILL.md`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_skills_present.py`:

```python
SKILL_NAMES = [
    "migrate",
    "query",
    "insert",
    "update",
    "delete",
    "list-stores",
    "register-role",
    "register-agent",
    "get-agent",
]


def test_all_core_skills_present():
    for skill in SKILL_NAMES:
        p = Path(f"skills/core/{skill}/SKILL.md")
        assert p.exists(), f"Missing skill: {skill}"


def test_all_core_skills_have_frontmatter_name():
    for skill in SKILL_NAMES:
        content = Path(f"skills/core/{skill}/SKILL.md").read_text()
        expected_name = f"name: memex:core:{skill}"
        assert expected_name in content, f"Skill {skill} missing correct frontmatter name"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_skills_present.py::test_all_core_skills_present -v`
Expected: FAIL (skills missing).

- [ ] **Step 3: Write minimal implementation**

`skills/core/migrate/SKILL.md`:

```markdown
---
name: memex:core:migrate
description: Apply additional SQL migration files to an existing Memex-managed store. Idempotent — already-applied migrations (tracked in the store's `migrations` table) are skipped. Use when a consumer's schema evolves and new .sql files need to be applied to an in-place store without recreating it.
---

# memex:core:migrate

## When to use

A registered store exists and the consumer's migration directory has new files that haven't been applied. Typical callers:
- Atelier ships a new migration; existing project stores need to be brought current.
- Memex itself ships an update to its bundled brain.sql; existing brain.db installs need to be migrated.

## Inputs

- `name` — registered store name
- `migrations_dir` — directory containing `.sql` files (same as create-store)

## What happens

1. Memex resolves the store's path from the registry.
2. Reads the `migrations` table to find already-applied filenames.
3. Scans `migrations_dir` in lexical order.
4. For each file not already applied: executes the SQL, records the application in `migrations`.
5. Returns the list of newly-applied filenames.

## Invocation

`scripts/stores.py:migrate(name, migrations_dir)`

## Errors

- `ValueError: Unknown store` — `name` is not registered. Use `memex:core:list-stores` to see what's registered.
- `sqlite3.OperationalError` — a new migration contains invalid SQL. Subsequent migrations are not applied.
```

`skills/core/query/SKILL.md`:

```markdown
---
name: memex:core:query
description: Run a SELECT query against any registered Memex store. Returns rows as a list of dicts. Use for read-only operations; for full-text or vector search, use memex:index:search instead.
---

# memex:core:query

## When to use

Read rows from a specific table in a specific registered store. NOT for cross-store federated search — use `memex:index:search` for that.

## Inputs

- `name` — registered store name
- `sql` — SELECT statement (no validation beyond what SQLite gives)
- `params` — optional tuple of bind parameters

## What happens

1. Resolves store path from registry.
2. Opens a read connection.
3. Executes the SELECT with bound parameters.
4. Returns all rows as a list of dicts.

## Invocation

`scripts/stores.py:query(name, sql, params)`

## Notes

- The skill does NOT enforce that the SQL is a SELECT. Misuse can mutate state. Callers are trusted to use it for reads only; writes go through `memex:core:insert`, `update`, `delete`, or the higher-level `memex:index:write`.
```

`skills/core/insert/SKILL.md`:

```markdown
---
name: memex:core:insert
description: Insert a row into a table of a registered Memex store. Use for non-document tables (lookup tables, configuration, agents, roles). For document rows that need to be indexed, use memex:index:write instead — that routes through the Librarian.
---

# memex:core:insert

## When to use

The row being inserted is NOT a document that should be indexed. Examples:
- Adding a role to `agents.db.roles`
- Adding a registered agent to `agents.db.agents`
- Writing to a consumer's internal lookup/configuration table

For document rows (articles, decisions, meeting minutes, captures), use `memex:index:write` — Memex requires every document to pass through the Librarian.

## Inputs

- `name` — registered store name
- `table` — target table name
- `row` — dict of column → value

## What happens

1. Resolves store path.
2. INSERT INTO table (col, …) VALUES (?, …) with bind parameters.
3. COMMITs.
4. Returns the inserted row (including any auto-generated `id`).

## Invocation

`scripts/stores.py:insert(name, table, row)`
```

`skills/core/update/SKILL.md`:

```markdown
---
name: memex:core:update
description: Update a single row by integer `id` PK in a registered Memex store. Use for partial updates of non-document rows; document content updates should re-trigger indexing via memex:index:write.
---

# memex:core:update

## Inputs

- `name` — registered store
- `table` — target table
- `row_id` — value of the `id` column
- `updates` — dict of column → new value

## Behavior

UPDATE table SET col=?, … WHERE id = ?. Returns the post-update row, or None if `row_id` didn't match.

## Invocation

`scripts/stores.py:update(name, table, row_id, updates)`

## Notes

- Only works on tables with an `id` PK column. For tables with TEXT PKs (like `agents.id`), perform the update via raw query OR add a dedicated CRUD module.
```

`skills/core/delete/SKILL.md`:

```markdown
---
name: memex:core:delete
description: Delete a row by integer `id` PK from a registered Memex store. Returns true if a row was deleted, false otherwise. Document deletes should also notify the Librarian (deferred to Plan 2).
---

# memex:core:delete

## Inputs

- `name`, `table`, `row_id`

## Behavior

DELETE FROM table WHERE id = ?. Returns True if a row was deleted.

## Invocation

`scripts/stores.py:delete(name, table, row_id)`

## Notes

- For document tables (rows that have an `index_id` column), the corresponding Index entry will become an orphan after this call. The Data Steward will detect it on the next audit (Plan 2 introduces this).
```

`skills/core/list-stores/SKILL.md`:

```markdown
---
name: memex:core:list-stores
description: List every registered Memex store on this machine — name, absolute path, schema version, registration time.
---

# memex:core:list-stores

## Inputs

None.

## Behavior

Reads `~/.memex/registry.json`. Returns a list of dicts:
```
[
  {"name": "agents", "path": "/home/.../agents.db", "schema_version": "v1", "registered_at": "..."},
  ...
]
```

## Invocation

`scripts/registry.py:list_stores()`
```

`skills/core/register-role/SKILL.md`:

```markdown
---
name: memex:core:register-role
description: Register a new role in the global agents.db roles table. Roles are universal (Memex-managed schema, multi-tenant rows). Consumers (Atelier, future plugins) call this on install to seed their own role taxonomies.
---

# memex:core:register-role

## When to use

A consumer is being installed and needs to register one or more roles into the shared agents.db. Example: Atelier seeds 60 dev-shop roles. Memex itself seeds 5 internal roles in Plan 2 (Librarian, Reference Librarian, Archivist, DBA, Data Steward).

## Inputs

- `name` — role name (UNIQUE constraint; conflicts raise IntegrityError)
- `description` — short description of the role's scope

## Behavior

INSERT INTO roles (name, description, …) VALUES (…). Returns the inserted row.

## Invocation

`scripts/roles.py:create_role(db_path, name, description)`
where `db_path` is `~/.memex/agents.db`.
```

`skills/core/register-agent/SKILL.md`:

```markdown
---
name: memex:core:register-agent
description: Register a new agent in the global agents.db agents table. Every Memex write requires an agent_id; this is how agents (human or LLM, internal or consumer-provided) come into existence.
---

# memex:core:register-agent

## When to use

- Plugin install seeds the 5 internal agents (Plan 2).
- Consumer install seeds consumer-specific agents (Atelier's 60).
- First Brain invocation triggers onboarding to register the human (Plan 3).
- A multi-agent system spawns a new agent identity dynamically.

## Inputs

- `agent_id` — TEXT PK (e.g., `librarian-1`, `human-user`, `atelier-pm-1`)
- `name` — display name
- `role_id` — FK into roles.id; the agent's role must exist first
- `profile` — markdown persona/system-prompt-fragment

## Behavior

INSERT INTO agents. Returns the inserted row.

## Invocation

`scripts/agents.py:create_agent(db_path, agent_id, name, role_id, profile)`
where `db_path` is `~/.memex/agents.db`.

## Errors

- `IntegrityError: UNIQUE constraint failed: agents.id` — duplicate agent_id.
- `IntegrityError: FOREIGN KEY constraint failed` — `role_id` doesn't exist in roles.
```

`skills/core/get-agent/SKILL.md`:

```markdown
---
name: memex:core:get-agent
description: Fetch an agent's full profile (including markdown profile body) by agent_id. Used by the Librarian, Reference Librarian, and other Memex internal agents to read created_by profiles for context-aware decision-making.
---

# memex:core:get-agent

## When to use

You need an agent's role and profile content. The Librarian reads `created_by` agent profiles to inform classification decisions; the Reference Librarian uses them to inform ranking.

## Inputs

- `agent_id` — TEXT PK

## Behavior

SELECT * FROM agents WHERE id = ?. Returns dict, or None if not found.

## Invocation

`scripts/agents.py:get_agent(db_path, agent_id)`
where `db_path` is `~/.memex/agents.db`.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_skills_present.py -v`
Expected: All PASSED (12 file-existence + frontmatter tests).

- [ ] **Step 5: Commit**

```bash
git add skills/core/
git commit -m "docs(core): SKILL.md for the 9 remaining memex:core:* skills"
```

---

## Task 15: Plugin manifest

**Files:**
- Create or Modify: `plugin.json` (or whatever Claude Code's manifest filename convention is for the installed plugin)

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugin_manifest.py`:

```python
import json
from pathlib import Path


def test_plugin_manifest_exists():
    assert Path("plugin.json").exists()


def test_plugin_manifest_is_valid_json():
    data = json.loads(Path("plugin.json").read_text())
    assert "name" in data
    assert "version" in data


def test_plugin_manifest_lists_core_skills():
    data = json.loads(Path("plugin.json").read_text())
    skills = data.get("skills", [])
    skill_names = {s.get("name") for s in skills}
    for required in [
        "memex:core:create-store",
        "memex:core:migrate",
        "memex:core:query",
        "memex:core:insert",
        "memex:core:update",
        "memex:core:delete",
        "memex:core:list-stores",
        "memex:core:register-role",
        "memex:core:register-agent",
        "memex:core:get-agent",
    ]:
        assert required in skill_names, f"Missing skill in manifest: {required}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugin_manifest.py -v`
Expected: FAIL (plugin.json missing or incomplete).

- [ ] **Step 3: Write minimal implementation**

Create or update `plugin.json`:

```json
{
  "name": "memex",
  "version": "2.0.0-dev",
  "description": "Memex v2 — personal knowledge runtime and shared memory plane for the agent fleet. Core CRUD substrate (Plan 1); Index + Librarian (Plan 2); Brain (Plan 3) ship in subsequent plans.",
  "skills": [
    { "name": "memex:core:create-store",   "path": "skills/core/create-store/SKILL.md" },
    { "name": "memex:core:migrate",        "path": "skills/core/migrate/SKILL.md" },
    { "name": "memex:core:query",          "path": "skills/core/query/SKILL.md" },
    { "name": "memex:core:insert",         "path": "skills/core/insert/SKILL.md" },
    { "name": "memex:core:update",         "path": "skills/core/update/SKILL.md" },
    { "name": "memex:core:delete",         "path": "skills/core/delete/SKILL.md" },
    { "name": "memex:core:list-stores",    "path": "skills/core/list-stores/SKILL.md" },
    { "name": "memex:core:register-role",  "path": "skills/core/register-role/SKILL.md" },
    { "name": "memex:core:register-agent", "path": "skills/core/register-agent/SKILL.md" },
    { "name": "memex:core:get-agent",      "path": "skills/core/get-agent/SKILL.md" }
  ],
  "install": {
    "script": "scripts/install.py",
    "entrypoint": "run"
  }
}
```

> Note: if Claude Code's plugin manifest format differs from this assumed JSON shape, adjust to match the official convention. The test ensures the file exists and contains the 10 skill names; restructure as needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plugin_manifest.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add plugin.json tests/test_plugin_manifest.py
git commit -m "feat(core): plugin manifest with 10 memex:core:* skills + install entrypoint"
```

---

## Task 16: End-to-end smoke test

**Files:**
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_smoke.py`:

```python
"""End-to-end Memex Core smoke test.

Walks the full Plan 1 surface: install → register role → register agent →
create-store → insert → query → migrate → update → delete → list-stores.
"""
import pytest
from pathlib import Path
from scripts import install, roles, agents, stores, registry
from scripts.db import memex_home


def test_e2e_core_lifecycle(tmp_memex_home, tmp_path):
    # 1. Install
    install.run()

    agents_db = str(memex_home() / "agents.db")

    # 2. Register a role
    role = roles.create_role(agents_db, "Test Role", "for smoke test")
    assert role["id"] > 0

    # 3. Register an agent
    a = agents.create_agent(agents_db, "smoke-1", "Smoke Test", role["id"], "profile")
    assert a["id"] == "smoke-1"

    # 4. Create a new store
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_items.sql").write_text(
        "CREATE TABLE items ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL"
        ");"
    )
    target = tmp_path / "smoke-store.db"
    stores.create_store("smoke-store", str(target), str(migrations_dir))

    # 5. Insert
    item = stores.insert("smoke-store", "items", {"name": "widget"})
    assert item["id"] > 0

    # 6. Query
    rows = stores.query("smoke-store", "SELECT * FROM items")
    assert len(rows) == 1
    assert rows[0]["name"] == "widget"

    # 7. Migrate
    (migrations_dir / "002_color.sql").write_text("ALTER TABLE items ADD COLUMN color TEXT;")
    applied = stores.migrate("smoke-store", str(migrations_dir))
    assert applied == ["002_color.sql"]

    # 8. Update
    stores.update("smoke-store", "items", item["id"], {"name": "gizmo"})
    rows = stores.query("smoke-store", "SELECT * FROM items WHERE id = ?", (item["id"],))
    assert rows[0]["name"] == "gizmo"

    # 9. Delete
    assert stores.delete("smoke-store", "items", item["id"]) is True
    rows = stores.query("smoke-store", "SELECT * FROM items")
    assert rows == []

    # 10. List stores includes both
    names = {s["name"] for s in registry.list_stores()}
    assert "agents" in names
    assert "smoke-store" in names
```

- [ ] **Step 2: Run tests to verify they fail or pass**

Run: `pytest tests/test_smoke.py -v`
Expected: PASS if all prior tasks completed correctly. If anything fails, the failing step indicates which prior task has a regression.

- [ ] **Step 3: (No implementation change — this is an integration test against existing code)**

- [ ] **Step 4: Re-run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass across every test_*.py file.

- [ ] **Step 5: Commit**

```bash
git add tests/test_smoke.py
git commit -m "test(core): end-to-end smoke test exercising the full Plan 1 surface"
```

---

## Task 17: README — Plan 1 acceptance criteria

**Files:**
- Create: `docs/CORE.md`

- [ ] **Step 1: Write the failing test**

Create `tests/test_core_docs.py`:

```python
from pathlib import Path


def test_core_doc_exists():
    assert Path("docs/CORE.md").exists()


def test_core_doc_lists_acceptance_criteria():
    content = Path("docs/CORE.md").read_text()
    for required in [
        "create-store",
        "migrate",
        "query",
        "insert",
        "update",
        "delete",
        "register-role",
        "register-agent",
        "get-agent",
        "list-stores",
    ]:
        assert required in content, f"Doc missing reference to {required}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_core_docs.py -v`
Expected: FAIL (file missing).

- [ ] **Step 3: Write minimal implementation**

Create `docs/CORE.md`:

```markdown
# Memex Core (Plan 1)

Memex Core is the CRUD substrate. It provisions and hosts SQLite stores
defined by consumer-supplied SQL migration files. It owns the agents and
roles tables (shared across consumers) and the store registry.

## What Plan 1 ships

| Skill | Purpose |
|---|---|
| `memex:core:create-store` | Provision a new SQLite store from a migrations directory |
| `memex:core:migrate` | Apply additional migrations to an existing store |
| `memex:core:query` | SELECT from any registered store |
| `memex:core:insert` | INSERT into a non-document table |
| `memex:core:update` | UPDATE a row by id |
| `memex:core:delete` | DELETE a row by id |
| `memex:core:list-stores` | List every registered store |
| `memex:core:register-role` | Add a role to the global agents.db.roles table |
| `memex:core:register-agent` | Add an agent to agents.db.agents |
| `memex:core:get-agent` | Fetch an agent's profile by id |

## What Plan 1 does NOT ship

- The 5 Memex-internal agent seeds (Librarian, Reference Librarian, Archivist, DBA, Data Steward) — that's Plan 2.
- index.db, FTS5, embeddings — Plan 2.
- Brain skills (ingest/ask/capture/lint/synthesize) — Plan 3.
- Plugin install scripts beyond `scripts/install.py:run()` — Plan 4.

## Acceptance criteria for Plan 1

1. `pytest tests/` passes with all tests green.
2. `python scripts/install.py` is idempotent and creates `~/.memex/` with
   `agents.db` and `registry.json`.
3. The 10 SKILL.md files exist with correct frontmatter `name:` fields.
4. The plugin manifest lists all 10 skills.
5. The end-to-end smoke test (`tests/test_smoke.py`) exercises the full lifecycle:
   install → register role → register agent → create-store → insert → query → migrate → update → delete → list-stores.

## How agents use it

```python
# From within Memex internals or a consumer skill:
from scripts import install, roles, agents, stores

install.run()  # idempotent

agents_db = str(memex_home() / "agents.db")
roles.create_role(agents_db, "Engineer", "writes code")
agents.create_agent(agents_db, "eng-1", "Dr. X", role_id, "profile…")

stores.create_store("my-project", "/abs/path/my-project.db", "/abs/path/migrations/")
stores.insert("my-project", "tasks", {"title": "do thing", "status": "open"})
rows = stores.query("my-project", "SELECT * FROM tasks WHERE status = ?", ("open",))
```
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_core_docs.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add docs/CORE.md tests/test_core_docs.py
git commit -m "docs(core): Plan 1 acceptance criteria and usage notes"
```

---

## Plan 1 acceptance checklist (final)

After all 17 tasks above pass, Plan 1 is complete when:

- [ ] `pytest tests/` reports 100% green across every test file
- [ ] `python scripts/install.py` runs to completion idempotently
- [ ] `~/.memex/agents.db` exists and contains `roles` and `agents` tables
- [ ] `~/.memex/registry.json` exists and lists `agents`
- [ ] `scripts/roles.py list` and `scripts/agents.py list` execute against the live DB and return JSON
- [ ] All 10 `skills/core/*/SKILL.md` files have correct frontmatter
- [ ] `plugin.json` registers all 10 skills
- [ ] End-to-end smoke test passes
- [ ] Final commit is clean (no unstaged changes)

Plan 2 (Index + 5 internal agents) builds on this foundation. Specifically,
Plan 2 will:
- Add `index.db` schema migration
- Seed the 5 internal roles + agents into `agents.db` via `register-role` and `register-agent`
- Implement the 5 internal agent subagents
- Add `memex:index:write`, `memex:index:search`, `memex:index:archive` skills

The seam between Plan 1 and Plan 2 is the Core CRUD surface. Plan 2 makes
no changes to Plan 1's files — only additions.
