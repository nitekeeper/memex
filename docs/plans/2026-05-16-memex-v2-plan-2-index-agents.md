# Memex v2 — Plan 2: Index + Internal Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the mandatory write-path gateway (Index + Librarian), the read-path retrieval layer (Reference Librarian), the immutable raw archive (Archivist), the storage-substrate ops layer (DBA), and the integrity auditor (Data Steward). End state: every document flows through the Librarian to receive an `index_id` before landing in a target store; queries route through the Reference Librarian via the federated Index; raw archive and audit machinery run.

**Architecture:** `index.db` is a new SQLite store (created via Plan 1's `create-store`) holding `documents`, `relations`, FTS5, and embedding columns. Five internal agents are seeded into `agents.db` and implemented as a mix of (a) deterministic Python modules under `scripts/agents/` for Archivist/DBA/Data Steward and (b) LLM-driven subagent harnesses for Librarian and Reference Librarian. Procedures under `internal/index/`, `internal/steward/`, and `internal/dba/` are thin wrappers reached on demand via the routing table inside `skills/run/SKILL.md` (Plan 1's single-skill registration model — see spec §8.0). Only `memex:run` is registered in `plugin.json`; Plan 2 extends `memex:run`'s routing table to cover the 9 new procedures.

**Tech Stack:** Python 3.10+, `sqlite3` stdlib (with FTS5 virtual table), `hashlib` for content hashing, OpenAI `text-embedding-3-small` as the v2.0 embedding model (1536-dim, packed as little-endian float32 BLOB); abstraction in `scripts/embeddings.py` enables swapping for Voyage/Anthropic/local without touching call sites. LLM subagent invocation via Claude Code's Task tool.

**Reference:** spec at `docs/specs/2026-05-16-memex-v2-redesign-design.md` (sections §3.2, §5.2, §6, §7, §8.2, §8.4, §10, §11).

**Depends on:** Plan 1 (Memex Core) — uses `memex:core:create-store`, `memex:core:register-role`, `memex:core:register-agent`, `memex:core:query`, `memex:core:insert`.

---

## File Structure

```
memex/
├── db/
│   ├── index.sql                                  # NEW: index.db schema
│   └── internal_agents_seed.py                    # NEW: 5 seed rows
├── scripts/
│   ├── embeddings.py                              # NEW: encode / cosine helpers
│   ├── agents/
│   │   ├── __init__.py                            # NEW
│   │   ├── archivist.py                           # NEW: deterministic raw archive
│   │   ├── dba.py                                 # NEW: pragma ops, integrity
│   │   ├── data_steward.py                        # NEW: audit primitives + report writer
│   │   ├── librarian.py                           # NEW: LLM harness for indexing
│   │   └── reference_librarian.py                 # NEW: LLM harness for retrieval
│   └── install.py                                 # MODIFY: extend Plan 1 install
├── internal/
│   ├── index/
│   │   ├── write/SKILL.md                         # NEW
│   │   ├── search/SKILL.md                        # NEW
│   │   └── archive/SKILL.md                       # NEW
│   ├── steward/
│   │   ├── audit/SKILL.md                         # NEW
│   │   ├── audit-store/SKILL.md                   # NEW
│   │   └── reconcile-orphan/SKILL.md              # NEW
│   └── dba/
│       ├── checkpoint/SKILL.md                    # NEW
│       ├── integrity-check/SKILL.md               # NEW
│       └── vacuum/SKILL.md                        # NEW
├── skills/
│   └── run/SKILL.md                               # MODIFY: extend routing table
├── prompts/
│   ├── librarian.md                               # NEW: system prompt body
│   └── reference_librarian.md                     # NEW: system prompt body
├── tests/
│   ├── test_index_schema.py                       # NEW
│   ├── test_internal_agents_seed.py               # NEW
│   ├── test_embeddings.py                         # NEW
│   ├── test_archivist.py                          # NEW
│   ├── test_dba.py                                # NEW
│   ├── test_data_steward.py                       # NEW
│   ├── test_librarian_harness.py                  # NEW: prompt construction, tool wiring, response parsing
│   ├── test_reference_librarian_harness.py        # NEW
│   ├── test_index_skills.py                       # NEW: SKILL.md presence
│   └── test_smoke_plan2.py                        # NEW: end-to-end with mocked LLM
```

> `plugin.json` is NOT modified by Plan 2. Per spec §8.0, the manifest registers only `memex:run`. Plan 2's nine procedures are reached via the routing table inside `skills/run/SKILL.md`, which Task 12 extends.

**Module boundaries:**
- `embeddings.py` — encode/decode/cosine only. Pluggable provider.
- `agents/archivist.py` — hash + write to `~/.memex/raw/`. No LLM.
- `agents/dba.py` — SQLite pragmas, integrity, vacuum, checkpoint. No LLM.
- `agents/data_steward.py` — audit SQL queries + report writing. No LLM (judgment is in the report, not in the queries).
- `agents/librarian.py` — LLM-driven extraction. Builds a prompt using `~/.memex/agents.db` profile, invokes subagent, parses structured response, writes Index rows.
- `agents/reference_librarian.py` — LLM-driven query decomposition. Builds prompt, invokes subagent, parses query plan, executes against index.db, ranks.

---

## Task 1: `index.db` schema

**Files:**
- Create: `db/index.sql`
- Create: `tests/test_index_schema.py`

- [ ] **Step 1: Write the failing test**

`tests/test_index_schema.py`:

```python
import sqlite3
from pathlib import Path
from scripts.db import get_connection


def test_index_schema_applies_cleanly(tmp_path):
    sql = Path("db/index.sql").read_text()
    db = tmp_path / "index.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    conn.commit()
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()
    assert "documents" in tables
    assert "relations" in tables


def test_index_schema_has_fts5(tmp_path):
    sql = Path("db/index.sql").read_text()
    db = tmp_path / "index.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    conn.commit()
    has_fts = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='documents_fts' AND type='table'"
    ).fetchone()
    conn.close()
    assert has_fts is not None


def test_index_documents_has_embedding_blob(tmp_path):
    sql = Path("db/index.sql").read_text()
    db = tmp_path / "index.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    cur = conn.execute("PRAGMA table_info(documents)")
    cols = {r["name"]: r["type"] for r in cur.fetchall()}
    conn.close()
    assert cols.get("embedding") == "BLOB"
    assert cols.get("index_id") == "TEXT"


def test_relations_pk_composite(tmp_path):
    sql = Path("db/index.sql").read_text()
    db = tmp_path / "index.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    conn.commit()
    # Inserting the same triple twice must fail due to composite PK.
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("a", "k1", "article", "brain", "articles", "1", "x", "system"),
    )
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("b", "k2", "article", "brain", "articles", "2", "y", "system"),
    )
    conn.execute(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
        ("a", "b", "cites"),
    )
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
            ("a", "b", "cites"),
        )
        conn.commit()
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_index_schema.py -v`
Expected: FAIL (`db/index.sql` does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `db/index.sql`:

```sql
-- index.db: federated metadata + FTS5 + embeddings + cross-store relations.
-- Created via memex:core:create-store with this file as the sole migration.
-- The Librarian (librarian-1) owns writes; Reference Librarian (reference-librarian-1) reads.

CREATE TABLE IF NOT EXISTS documents (
    index_id     TEXT PRIMARY KEY,
    key          TEXT,
    domain       TEXT NOT NULL,
    store        TEXT NOT NULL,
    table_name   TEXT NOT NULL,
    row_id       TEXT NOT NULL,
    searchable   TEXT,
    metadata     TEXT,
    embedding    BLOB,
    created_by   TEXT NOT NULL,            -- FK semantically to agents.db.agents.id; not enforced cross-DB
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS documents_domain_idx ON documents(domain);
CREATE INDEX IF NOT EXISTS documents_store_idx  ON documents(store);
CREATE INDEX IF NOT EXISTS documents_key_idx    ON documents(key);

CREATE TABLE IF NOT EXISTS relations (
    from_index_id  TEXT NOT NULL REFERENCES documents(index_id),
    to_index_id    TEXT NOT NULL REFERENCES documents(index_id),
    rel_type       TEXT NOT NULL,
    confidence     REAL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (from_index_id, to_index_id, rel_type)
);

CREATE INDEX IF NOT EXISTS relations_to_idx ON relations(to_index_id);

-- FTS5 over documents.searchable. Manual sync via triggers below.
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    searchable, content='documents', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, searchable) VALUES (new.rowid, new.searchable);
END;
CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, searchable) VALUES('delete', old.rowid, old.searchable);
END;
CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, searchable) VALUES('delete', old.rowid, old.searchable);
    INSERT INTO documents_fts(rowid, searchable) VALUES (new.rowid, new.searchable);
END;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_index_schema.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add db/index.sql tests/test_index_schema.py
git commit -m "feat(index): index.db schema with documents, relations, FTS5, embeddings"
```

---

## Task 2: Internal-agent seed data

**Files:**
- Create: `db/internal_agents_seed.py`
- Create: `tests/test_internal_agents_seed.py`

- [ ] **Step 1: Write the failing test**

`tests/test_internal_agents_seed.py`:

```python
from db.internal_agents_seed import INTERNAL_AGENTS


def test_seed_has_five_entries():
    assert len(INTERNAL_AGENTS) == 5


def test_seed_role_names_match_spec():
    names = {e["role_name"] for e in INTERNAL_AGENTS}
    assert names == {
        "Librarian",
        "Reference Librarian",
        "Archivist",
        "Database Administrator",
        "Data Steward",
    }


def test_seed_agent_ids_match_spec():
    ids = {e["agent_id"] for e in INTERNAL_AGENTS}
    assert ids == {
        "librarian-1",
        "reference-librarian-1",
        "archivist-1",
        "dba-1",
        "data-steward-1",
    }


def test_each_entry_has_complete_fields():
    required = {"role_name", "role_desc", "agent_id", "agent_name", "agent_profile"}
    for e in INTERNAL_AGENTS:
        assert set(e.keys()) >= required, f"Missing fields in {e.get('agent_id')}"
        for k in required:
            assert isinstance(e[k], str) and e[k].strip(), f"Empty {k} in {e.get('agent_id')}"


def test_profiles_are_substantial():
    """Each profile is a multi-paragraph operational spec (not a one-liner)."""
    for e in INTERNAL_AGENTS:
        assert len(e["agent_profile"]) > 800, f"{e['agent_id']} profile too short"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_internal_agents_seed.py -v`
Expected: FAIL (`db/internal_agents_seed.py` missing).

- [ ] **Step 3: Write minimal implementation**

Create `db/internal_agents_seed.py`. Copy the 5 profiles verbatim from spec Appendix A. (Profile text omitted here for brevity — use the spec file as the source of truth. Each entry is a dict with: `role_name`, `role_desc`, `agent_id`, `agent_name`, `agent_profile`.)

```python
"""Seed data for Memex's 5 internal agents.

Profile text is the canonical source. Edit here, re-run install.py to
update existing installs (install.py is idempotent; updates existing
agents.profile via update_agent).
"""

INTERNAL_AGENTS = [
    {
        "role_name": "Librarian",
        "role_desc": "Centralized indexing authority. Catalogs every document submitted to Memex, extracting keys, domains, searchable text, metadata, and cross-store relationships. Sole custodian of the federated Index.",
        "agent_id": "librarian-1",
        "agent_name": "Dr. Lakshmi Iyer-Ranganathan",
        "agent_profile": _LIBRARIAN_PROFILE,  # defined below; full text from spec Appendix A.1
    },
    {
        "role_name": "Reference Librarian",
        "role_desc": "Synchronous retrieval authority. Constructs queries against the Index, ranks candidate documents, returns citation-ready results to calling agents. Powers all read paths.",
        "agent_id": "reference-librarian-1",
        "agent_name": "Dr. Eleanor Whitfield",
        "agent_profile": _REFERENCE_LIBRARIAN_PROFILE,  # spec A.2
    },
    {
        "role_name": "Archivist",
        "role_desc": "Custodian of immutable history. Owns the raw document archive, version history, and retention policies. Ensures every indexed document has an unalterable source-of-truth original.",
        "agent_id": "archivist-1",
        "agent_name": "Dr. Heinrich Mühlbauer",
        "agent_profile": _ARCHIVIST_PROFILE,  # spec A.3
    },
    {
        "role_name": "Database Administrator",
        "role_desc": "Owner of the physical storage substrate. Manages SQLite file creation, WAL/pragma discipline, schema migrations, integrity checks, backups, and performance across every Memex-managed database.",
        "agent_id": "dba-1",
        "agent_name": "Dr. Rajesh Subramanian",
        "agent_profile": _DBA_PROFILE,  # spec A.4
    },
    {
        "role_name": "Data Steward",
        "role_desc": "Periodic integrity auditor. Detects schema drift across stores, orphans between stores and the Index, broken cross-store references, and duplicate or near-duplicate index entries. Reports findings; never auto-fixes without authorization.",
        "agent_id": "data-steward-1",
        "agent_name": "Dr. Ingrid Bergström",
        "agent_profile": _DATA_STEWARD_PROFILE,  # spec A.5
    },
]
```

Define each `_*_PROFILE` constant as a triple-quoted string containing the verbatim profile body from spec Appendix A. The full text is in `docs/specs/2026-05-16-memex-v2-redesign-design.md`. The implementing engineer should copy paragraph-for-paragraph.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_internal_agents_seed.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add db/internal_agents_seed.py tests/test_internal_agents_seed.py
git commit -m "feat(index): seed data for 5 Memex-internal agents (Librarian, Ref Lib, Archivist, DBA, Data Steward)"
```

---

## Task 3: Extend `install.py` to seed agents + create index.db

**Files:**
- Modify: `scripts/install.py`
- Modify: `tests/test_install.py`

- [ ] **Step 1: Write the failing test**

Replace `tests/test_install.py::test_install_does_not_seed_internal_agents_in_core` with the post-Plan-2 reality. Append to `tests/test_install.py`:

```python
def test_install_seeds_five_internal_roles(tmp_memex_home):
    install.run()
    agents_db = str(memex_home() / "agents.db")
    listed = roles.list_roles(agents_db)
    role_names = {r["name"] for r in listed}
    assert role_names == {
        "Librarian", "Reference Librarian", "Archivist",
        "Database Administrator", "Data Steward",
    }


def test_install_seeds_five_internal_agents(tmp_memex_home):
    install.run()
    agents_db = str(memex_home() / "agents.db")
    listed = agents.list_agents(agents_db)
    agent_ids = {a["id"] for a in listed}
    assert agent_ids == {
        "librarian-1", "reference-librarian-1", "archivist-1",
        "dba-1", "data-steward-1",
    }


def test_install_creates_index_db(tmp_memex_home):
    install.run()
    assert (memex_home() / "index.db").exists()


def test_install_registers_index_in_registry(tmp_memex_home):
    install.run()
    rec = registry.get_store("index")
    assert rec is not None
    assert rec["path"] == str(memex_home() / "index.db")


def test_install_is_idempotent_with_seeds(tmp_memex_home):
    install.run()
    install.run()  # second call must not duplicate or error
    agents_db = str(memex_home() / "agents.db")
    listed = agents.list_agents(agents_db)
    assert len(listed) == 5  # not 10
```

Remove the obsolete `test_install_does_not_seed_internal_agents_in_core` test from Plan 1.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_install.py -v`
Expected: FAIL on the new tests.

- [ ] **Step 3: Write minimal implementation**

Modify `scripts/install.py` to extend the Plan 1 implementation:

```python
"""One-shot ~/.memex/ bootstrap. Extended in Plan 2 to seed internal agents
and create index.db."""
from __future__ import annotations
from pathlib import Path
from scripts.db import get_connection, memex_home
from scripts import registry, roles, agents, stores
from db.internal_agents_seed import INTERNAL_AGENTS


def run() -> None:
    home = memex_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "raw").mkdir(exist_ok=True)
    (home / "backups").mkdir(exist_ok=True)
    (home / "audits").mkdir(exist_ok=True)
    (home / "templates").mkdir(exist_ok=True)

    # agents.db (Plan 1 functionality, preserved)
    agents_db_path = home / "agents.db"
    if not agents_db_path.exists():
        agents_sql = Path("db/agents.sql").read_text()
        conn = get_connection(str(agents_db_path))
        conn.executescript(agents_sql)
        conn.commit()
        conn.close()
    if registry.get_store("agents") is None:
        registry.register_store("agents", str(agents_db_path), schema_version="v1")

    # Seed roles + agents (Plan 2 addition). Idempotent — checks existence.
    _seed_internal(str(agents_db_path))

    # index.db (Plan 2 addition). Created via memex:core:create-store mechanics
    # but bootstrapped directly here to avoid registering ourselves twice.
    index_db_path = home / "index.db"
    if not index_db_path.exists():
        # Use stores.create_store with a temporary migrations dir holding index.sql.
        # Simpler: open and executescript directly (we own this path).
        conn = get_connection(str(index_db_path))
        conn.executescript(Path("db/migrations_table.sql").read_text())
        conn.executescript(Path("db/index.sql").read_text())
        conn.execute(
            "INSERT INTO migrations (filename) VALUES (?)",
            ("index.sql",),
        )
        conn.commit()
        conn.close()
    if registry.get_store("index") is None:
        registry.register_store("index", str(index_db_path), schema_version="v1")


def _seed_internal(agents_db_path: str) -> None:
    """Idempotent seed of internal roles + agents."""
    existing_roles = {r["name"]: r["id"] for r in roles.list_roles(agents_db_path)}
    for entry in INTERNAL_AGENTS:
        if entry["role_name"] in existing_roles:
            role_id = existing_roles[entry["role_name"]]
        else:
            r = roles.create_role(agents_db_path, entry["role_name"], entry["role_desc"])
            role_id = r["id"]

        if agents.get_agent(agents_db_path, entry["agent_id"]) is None:
            agents.create_agent(
                agents_db_path,
                entry["agent_id"],
                entry["agent_name"],
                role_id,
                entry["agent_profile"],
            )
        else:
            # Update profile in place (handles seed-text updates across versions)
            agents.update_agent(
                agents_db_path,
                entry["agent_id"],
                profile=entry["agent_profile"],
                name=entry["agent_name"],
                role_id=role_id,
            )


if __name__ == "__main__":
    run()
    print(f"Memex installed at {memex_home()}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_install.py -v`
Expected: All PASSED (5 new tests + the 3 still-valid Plan 1 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/install.py tests/test_install.py
git commit -m "feat(index): install.run seeds 5 internal agents and creates index.db"
```

---

## Task 4: `embeddings.py` — encode + cosine

**Files:**
- Create: `scripts/embeddings.py`
- Create: `tests/test_embeddings.py`

- [ ] **Step 1: Write the failing test**

`tests/test_embeddings.py`:

```python
import struct
import pytest
from unittest.mock import patch, MagicMock
from scripts import embeddings


def test_encode_returns_blob():
    with patch("scripts.embeddings._call_provider", return_value=[0.1, 0.2, 0.3]):
        result = embeddings.encode("hello")
    assert isinstance(result, bytes)
    assert len(result) == 12  # 3 floats × 4 bytes


def test_decode_round_trips():
    vec_in = [0.5, -0.5, 1.0, 0.0]
    blob = embeddings._pack(vec_in)
    vec_out = embeddings._unpack(blob)
    assert vec_out == pytest.approx(vec_in, rel=1e-6)


def test_cosine_identical_vectors_is_one():
    a = [1.0, 0.0, 0.0]
    assert embeddings.cosine(embeddings._pack(a), embeddings._pack(a)) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors_is_zero():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert embeddings.cosine(embeddings._pack(a), embeddings._pack(b)) == pytest.approx(0.0)


def test_cosine_opposite_vectors_is_negative_one():
    a = [1.0, 0.0, 0.0]
    b = [-1.0, 0.0, 0.0]
    assert embeddings.cosine(embeddings._pack(a), embeddings._pack(b)) == pytest.approx(-1.0)


def test_encode_caches_model_in_registry():
    """When encode runs, the model+dim must be recorded in ~/.memex/registry.json
    under a known key so re-embed/migration tooling can detect changes."""
    with patch("scripts.embeddings._call_provider", return_value=[0.0] * 1536):
        embeddings.encode("hello")
    from scripts import registry
    info = registry._load().get("__embedding_model__")
    assert info is not None
    assert info["dim"] == 1536
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embeddings.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/embeddings.py`:

```python
"""Embedding encode/cosine helpers with pluggable provider.

v2.0 default: OpenAI text-embedding-3-small (1536-dim).
Provider is selected via env var MEMEX_EMBEDDING_PROVIDER (default: 'openai').
Alternative providers (voyage, anthropic, local) implement _call_provider
under their respective module path; this file imports them lazily.

Vectors are packed as little-endian float32 BLOBs in index.db.documents.embedding.
"""
from __future__ import annotations
import os
import math
import struct
import json
from typing import List
from scripts.db import memex_home

DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIM = 1536


def _pack(vec: List[float]) -> bytes:
    """Pack a list of floats as little-endian float32 BLOB."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack(blob: bytes) -> List[float]:
    """Unpack a float32 BLOB to a list of floats."""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def _call_provider(text: str) -> List[float]:
    """Call the configured embedding provider. Returns a list of floats."""
    provider = os.environ.get("MEMEX_EMBEDDING_PROVIDER", "openai")
    if provider == "openai":
        return _openai_encode(text)
    elif provider == "voyage":
        return _voyage_encode(text)
    elif provider == "local":
        return _local_encode(text)
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


def _openai_encode(text: str) -> List[float]:
    """Call OpenAI text-embedding-3-small. Requires OPENAI_API_KEY env var.
    Lazy import so the package isn't required when using a different provider."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.embeddings.create(input=text, model=DEFAULT_MODEL)
    return resp.data[0].embedding


def _voyage_encode(text: str) -> List[float]:
    """Stub: implement when switching to Voyage. Imports lazily."""
    raise NotImplementedError("Voyage provider not yet wired")


def _local_encode(text: str) -> List[float]:
    """Stub: implement with sentence-transformers when switching to local."""
    raise NotImplementedError("Local provider not yet wired")


def _record_model_info(dim: int) -> None:
    """Record the active embedding model + dimensionality in registry.json
    under a reserved key. Used by re-embed tooling to detect changes."""
    from scripts import registry
    data = registry._load()
    data["__embedding_model__"] = {
        "provider": os.environ.get("MEMEX_EMBEDDING_PROVIDER", "openai"),
        "model": DEFAULT_MODEL,
        "dim": dim,
    }
    registry._save(data)


def encode(text: str) -> bytes:
    """Encode text → float32 BLOB. Records model info on first call."""
    vec = _call_provider(text)
    _record_model_info(len(vec))
    return _pack(vec)


def cosine(blob_a: bytes, blob_b: bytes) -> float:
    """Cosine similarity between two packed embedding BLOBs."""
    a = _unpack(blob_a)
    b = _unpack(blob_b)
    if len(a) != len(b):
        raise ValueError(f"Dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -v`
Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/embeddings.py tests/test_embeddings.py
git commit -m "feat(index): embeddings module with OpenAI default + pluggable provider, cosine helper"
```

---

## Task 5: `archivist.py` — content-addressable raw write

**Files:**
- Create: `scripts/agents/__init__.py`
- Create: `scripts/agents/archivist.py`
- Create: `tests/test_archivist.py`

- [ ] **Step 1: Write the failing test**

`tests/test_archivist.py`:

```python
import hashlib
import pytest
from scripts.agents import archivist


def test_archive_returns_path_and_hash(tmp_memex_home):
    payload = b"hello world\n"
    result = archivist.archive(payload, filename="hello.txt")
    assert result["hash"] == hashlib.sha256(payload).hexdigest()
    assert result["path"].endswith("hello.txt")
    assert (tmp_memex_home / "raw").is_dir()


def test_archive_writes_to_hash_prefixed_subdir(tmp_memex_home):
    payload = b"unique-content-A"
    result = archivist.archive(payload, filename="a.txt")
    from pathlib import Path
    path = Path(result["path"])
    # Should be under ~/.memex/raw/<hash-prefix>/a.txt
    assert path.parent.parent == tmp_memex_home / "raw"
    assert len(path.parent.name) == 2  # 2-char hash prefix


def test_archive_is_idempotent_on_same_content(tmp_memex_home):
    payload = b"same content"
    r1 = archivist.archive(payload, filename="x.txt")
    r2 = archivist.archive(payload, filename="x.txt")
    assert r1["path"] == r2["path"]
    assert r1["hash"] == r2["hash"]


def test_archive_versions_on_filename_collision_different_content(tmp_memex_home):
    """Same filename, different content → both preserved with different hashes."""
    r1 = archivist.archive(b"version 1", filename="doc.md")
    r2 = archivist.archive(b"version 2", filename="doc.md")
    assert r1["path"] != r2["path"]
    assert r1["hash"] != r2["hash"]


def test_archive_canonicalizes_text_before_hashing(tmp_memex_home):
    """Canonicalization strips leading/trailing whitespace and normalizes line endings."""
    a = archivist.archive(b"hello\r\nworld\r\n", filename="x.txt")
    b = archivist.archive(b"hello\nworld\n", filename="x.txt")
    assert a["hash"] == b["hash"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_archivist.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/agents/__init__.py`: (empty)

Create `scripts/agents/archivist.py`:

```python
"""Archivist — deterministic raw archive writer.

Owns ~/.memex/raw/. Content-addressable: each unique canonical-form
payload stored under raw/<hash-prefix>/<filename>. Same content → same path
(idempotent). Different content with same filename → new versioned path.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from scripts.db import memex_home


def _canonicalize(payload: bytes) -> bytes:
    """Normalize line endings and strip outer whitespace before hashing.

    The same canonicalization is applied on re-ingest to detect 'no real change'
    cases regardless of CRLF vs LF or trailing newline differences.
    """
    text = payload.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return text.encode("utf-8")


def _hash(canonical: bytes) -> str:
    return hashlib.sha256(canonical).hexdigest()


def archive(payload: bytes, filename: str) -> dict:
    """Write a payload to the raw archive.

    Returns:
        {"hash": <sha256 of canonical>, "path": <absolute path of stored file>}

    Idempotency: same canonical → same path → no rewrite if file already exists.
    """
    canonical = _canonicalize(payload)
    h = _hash(canonical)
    prefix = h[:2]
    raw_root = memex_home() / "raw" / prefix
    raw_root.mkdir(parents=True, exist_ok=True)

    # Use hash in the filename to avoid version-overwrite when content differs
    # but caller-supplied filename is reused. Pattern: <stem>-<hash8>.<suffix>
    name_path = Path(filename)
    stem = name_path.stem
    suffix = "".join(name_path.suffixes)
    versioned = f"{stem}-{h[:8]}{suffix}"
    target = raw_root / versioned

    if not target.exists():
        target.write_bytes(payload)
    return {"hash": h, "path": str(target)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_archivist.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/agents/__init__.py scripts/agents/archivist.py tests/test_archivist.py
git commit -m "feat(index): archivist content-addressable raw archive with canonicalization"
```

---

## Task 6: `dba.py` — pragma ops + integrity + checkpoint + vacuum

**Files:**
- Create: `scripts/agents/dba.py`
- Create: `tests/test_dba.py`

- [ ] **Step 1: Write the failing test**

`tests/test_dba.py`:

```python
import pytest
from scripts.agents import dba
from scripts.db import get_connection


def test_integrity_check_passes_on_clean_db(tmp_path):
    db = tmp_path / "clean.db"
    conn = get_connection(str(db))
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    result = dba.integrity_check(str(db))
    assert result == "ok"


def test_checkpoint_passive_succeeds(tmp_path):
    db = tmp_path / "wal.db"
    conn = get_connection(str(db))
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.commit()
    conn.close()

    # PASSIVE checkpoint returns (busy, log_pages, checkpointed_pages)
    result = dba.checkpoint(str(db), mode="PASSIVE")
    assert isinstance(result, dict)
    assert "busy" in result
    assert "log_pages" in result
    assert "checkpointed" in result


def test_vacuum_succeeds(tmp_path):
    db = tmp_path / "v.db"
    conn = get_connection(str(db))
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.commit()
    conn.close()

    # Should not raise; reduces file size after data churn
    dba.vacuum(str(db))


def test_foreign_key_check_returns_violations(tmp_path):
    db = tmp_path / "fk.db"
    conn = get_connection(str(db))
    conn.executescript("""
        CREATE TABLE parent (id INTEGER PRIMARY KEY);
        CREATE TABLE child (
            id INTEGER PRIMARY KEY,
            parent_id INTEGER REFERENCES parent(id)
        );
    """)
    conn.commit()
    # Bypass FK enforcement temporarily to insert bad data
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("INSERT INTO child (id, parent_id) VALUES (1, 999)")
    conn.commit()
    conn.close()

    violations = dba.foreign_key_check(str(db))
    assert len(violations) == 1
    assert violations[0]["table"] == "child"


def test_journal_mode_is_wal(tmp_path):
    db = tmp_path / "w.db"
    conn = get_connection(str(db))
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.commit()
    conn.close()

    assert dba.journal_mode(str(db)) == "wal"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dba.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/agents/dba.py`:

```python
"""Database Administrator — deterministic SQLite operational primitives.

No LLM involvement. The DBA's profile defines the operating rules; this
module implements them as Python functions.
"""
from __future__ import annotations
from scripts.db import get_connection


def integrity_check(db_path: str) -> str:
    """Run PRAGMA integrity_check. Returns 'ok' on clean DB, otherwise
    a concatenated string of issues."""
    conn = get_connection(db_path)
    rows = [r[0] for r in conn.execute("PRAGMA integrity_check")]
    conn.close()
    if rows == ["ok"]:
        return "ok"
    return "; ".join(rows)


def foreign_key_check(db_path: str) -> list[dict]:
    """Run PRAGMA foreign_key_check. Returns a list of violation dicts
    (empty list if no violations).

    Each row: (table, rowid, parent, fkid)
    """
    conn = get_connection(db_path)
    cur = conn.execute("PRAGMA foreign_key_check")
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


def checkpoint(db_path: str, mode: str = "PASSIVE") -> dict:
    """Run a WAL checkpoint. Mode is one of PASSIVE | FULL | RESTART | TRUNCATE.
    Returns dict with busy / log_pages / checkpointed counts."""
    conn = get_connection(db_path)
    row = conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
    conn.close()
    return {
        "busy": row[0],
        "log_pages": row[1],
        "checkpointed": row[2],
    }


def vacuum(db_path: str) -> None:
    """Run VACUUM. Reclaims free space."""
    conn = get_connection(db_path)
    conn.execute("VACUUM")
    conn.commit()
    conn.close()


def analyze(db_path: str) -> None:
    """Run ANALYZE. Updates query planner statistics."""
    conn = get_connection(db_path)
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()


def journal_mode(db_path: str) -> str:
    conn = get_connection(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    return mode.lower()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dba.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/agents/dba.py tests/test_dba.py
git commit -m "feat(index): DBA module — integrity, FK check, checkpoint, vacuum, analyze"
```

---

## Task 7: `data_steward.py` — orphan detection + report writer

**Files:**
- Create: `scripts/agents/data_steward.py`
- Create: `tests/test_data_steward.py`

- [ ] **Step 1: Write the failing test**

`tests/test_data_steward.py`:

```python
import pytest
from pathlib import Path
from scripts import install, stores, registry
from scripts.agents import data_steward
from scripts.db import get_connection, memex_home


@pytest.fixture
def post_install(tmp_memex_home):
    install.run()
    return memex_home()


def _seed_doc(index_db: str, index_id: str, store: str, table: str, row_id: str):
    conn = get_connection(index_db)
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (index_id, "k", "article", store, table, row_id, "text", "librarian-1"),
    )
    conn.commit()
    conn.close()


def test_find_orphans_index_has_no_target_row(post_install, tmp_path):
    # Set up a registered store with one row.
    md = tmp_path / "m"; md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, index_id TEXT, body TEXT);"
    )
    stores.create_store("test-store", str(tmp_path / "ts.db"), str(md))
    row = stores.insert("test-store", "items", {"index_id": "idx-A", "body": "x"})

    # Add an index entry that points to a row that doesn't exist.
    index_db = str(post_install / "index.db")
    _seed_doc(index_db, "idx-MISSING", "test-store", "items", "9999")

    orphans = data_steward.find_orphans(index_db)
    ids = {o["index_id"] for o in orphans}
    assert "idx-MISSING" in ids
    assert "idx-A" not in ids


def test_find_reverse_orphans_store_row_without_index_entry(post_install, tmp_path):
    md = tmp_path / "m"; md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, index_id TEXT, body TEXT);"
    )
    stores.create_store("test-store", str(tmp_path / "ts.db"), str(md))
    # Insert a row WITHOUT registering in index.db
    stores.insert("test-store", "items", {"index_id": "idx-LONELY", "body": "x"})

    index_db = str(post_install / "index.db")
    reverse_orphans = data_steward.find_reverse_orphans(index_db, "test-store", "items")
    ids = {o["index_id"] for o in reverse_orphans}
    assert "idx-LONELY" in ids


def test_find_broken_relations(post_install):
    index_db = str(post_install / "index.db")
    _seed_doc(index_db, "a", "x", "t", "1")
    # b never inserted into documents
    # Insert a relation a → b directly (bypass FK by disabling temporarily)
    conn = get_connection(index_db)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
        ("a", "b", "cites"),
    )
    conn.commit()
    conn.close()

    broken = data_steward.find_broken_relations(index_db)
    assert len(broken) == 1
    assert broken[0]["to_index_id"] == "b"


def test_audit_writes_report_to_audits_dir(post_install, tmp_path):
    index_db = str(post_install / "index.db")
    _seed_doc(index_db, "idx-MISSING", "no-such-store", "t", "1")

    report_path = data_steward.audit(index_db)
    assert Path(report_path).exists()
    assert "idx-MISSING" in Path(report_path).read_text()


def test_audit_report_has_structured_sections(post_install):
    index_db = str(post_install / "index.db")
    report_path = data_steward.audit(index_db)
    content = Path(report_path).read_text()
    # Sections required by spec §11 audit format
    assert "## Summary" in content
    assert "## Findings" in content or "(no findings)" in content.lower()
    assert "Severity" in content or "(no findings)" in content.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_data_steward.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/agents/data_steward.py`:

```python
"""Data Steward — periodic integrity auditor.

Detects:
  - Orphans: documents row references a store/table/row that doesn't exist
  - Reverse orphans: a store row with an index_id column whose value is not in documents
  - Broken relations: relations row pointing to a nonexistent index_id

Writes structured audit reports to ~/.memex/audits/AUD-YYYY-MM-DD-NNN.md.
Never auto-fixes. Reports findings + recommended actions.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from scripts import registry
from scripts.db import get_connection, memex_home


def _index_conn(index_db: str):
    return get_connection(index_db)


def find_orphans(index_db: str) -> list[dict]:
    """Find documents rows whose (store, table, row_id) does not resolve to
    an existing row in the target store."""
    conn = _index_conn(index_db)
    docs = [dict(r) for r in conn.execute(
        "SELECT index_id, store, table_name, row_id FROM documents"
    )]
    conn.close()

    orphans = []
    for d in docs:
        rec = registry.get_store(d["store"])
        if rec is None:
            orphans.append({**d, "reason": f"store '{d['store']}' not registered"})
            continue
        target_conn = get_connection(rec["path"])
        try:
            row = target_conn.execute(
                f"SELECT 1 FROM {d['table_name']} WHERE id = ?",
                (d["row_id"],),
            ).fetchone()
            if row is None:
                orphans.append({**d, "reason": "row_id not found in target table"})
        except Exception as e:
            orphans.append({**d, "reason": f"query error: {e}"})
        finally:
            target_conn.close()
    return orphans


def find_reverse_orphans(index_db: str, store: str, table: str) -> list[dict]:
    """Find rows in the named store/table with an index_id that doesn't
    appear in documents."""
    rec = registry.get_store(store)
    if rec is None:
        return []

    store_conn = get_connection(rec["path"])
    try:
        rows = [dict(r) for r in store_conn.execute(
            f"SELECT id, index_id FROM {table} WHERE index_id IS NOT NULL"
        )]
    except Exception:
        store_conn.close()
        return []
    store_conn.close()

    if not rows:
        return []

    conn = _index_conn(index_db)
    indexed_ids = {r["index_id"] for r in conn.execute("SELECT index_id FROM documents")}
    conn.close()

    return [{"index_id": r["index_id"], "row_id": r["id"], "store": store, "table_name": table}
            for r in rows if r["index_id"] not in indexed_ids]


def find_broken_relations(index_db: str) -> list[dict]:
    """Find relations rows whose from_index_id or to_index_id is not in documents."""
    conn = _index_conn(index_db)
    broken = [dict(r) for r in conn.execute("""
        SELECT r.from_index_id, r.to_index_id, r.rel_type
        FROM relations r
        LEFT JOIN documents df ON df.index_id = r.from_index_id
        LEFT JOIN documents dt ON dt.index_id = r.to_index_id
        WHERE df.index_id IS NULL OR dt.index_id IS NULL
    """)]
    conn.close()
    return broken


def audit(index_db: str) -> str:
    """Run a full audit and write a report. Returns the report path."""
    orphans = find_orphans(index_db)
    broken = find_broken_relations(index_db)

    audits_dir = memex_home() / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Find next sequential N for today
    existing = list(audits_dir.glob(f"AUD-{date_str}-*.md"))
    n = len(existing) + 1
    report_path = audits_dir / f"AUD-{date_str}-{n:03d}.md"

    findings = []
    for o in orphans:
        findings.append({
            "severity": 3,
            "category": "orphan",
            "detail": f"index_id `{o['index_id']}` → {o['store']}/{o['table_name']}/{o['row_id']} : {o['reason']}",
            "recommendation": "Re-attempt target store write, OR delete the documents row.",
        })
    for b in broken:
        findings.append({
            "severity": 4,
            "category": "broken_relation",
            "detail": f"{b['from_index_id']} -[{b['rel_type']}]-> {b['to_index_id']} (one or both index_ids missing)",
            "recommendation": "Delete the broken relations row.",
        })

    lines = [
        f"# Audit Report — {report_path.name}",
        f"",
        f"Audit run at: {datetime.now(timezone.utc).isoformat()}",
        f"Audited DB: {index_db}",
        f"",
        f"## Summary",
        f"",
        f"- Orphans found: {len(orphans)}",
        f"- Broken relations found: {len(broken)}",
        f"- Total findings: {len(findings)}",
        f"",
        f"## Findings",
        f"",
    ]
    if not findings:
        lines.append("(no findings)")
    else:
        for i, f in enumerate(findings, 1):
            lines.append(f"### Finding {i} (Severity {f['severity']}, {f['category']})")
            lines.append(f"")
            lines.append(f"**Detail:** {f['detail']}")
            lines.append(f"")
            lines.append(f"**Recommendation:** {f['recommendation']}")
            lines.append(f"")

    report_path.write_text("\n".join(lines))
    return str(report_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_data_steward.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/agents/data_steward.py tests/test_data_steward.py
git commit -m "feat(index): Data Steward audit primitives + structured report writer"
```

---

## Task 8: Librarian subagent — prompt + harness

**Files:**
- Create: `prompts/librarian.md`
- Create: `scripts/agents/librarian.py`
- Create: `tests/test_librarian_harness.py`

- [ ] **Step 1: Write the failing test**

`tests/test_librarian_harness.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from scripts.agents import librarian


def test_build_prompt_includes_agent_profile(tmp_memex_home):
    from scripts import install
    install.run()
    prompt = librarian.build_prompt(
        payload="hello world",
        target_store="article",
        caller_agent_id="librarian-1",
    )
    # Profile content should be embedded
    assert "Ranganathan" in prompt
    assert "hello world" in prompt
    assert "target_store" in prompt or "article" in prompt


def test_build_prompt_includes_existing_index_snippet(tmp_memex_home):
    """Prompt must include a snippet of existing index for context."""
    from scripts import install
    install.run()
    prompt = librarian.build_prompt(
        payload="hello",
        target_store="article",
        caller_agent_id="librarian-1",
        existing_index_snippet=[
            {"index_id": "x", "key": "prior-article", "domain": "article"}
        ],
    )
    assert "prior-article" in prompt


def test_parse_response_extracts_structured_output():
    mock_response = json.dumps({
        "index_id": "idx-abc",
        "key": "test-key",
        "domain": "article",
        "searchable": "test searchable text",
        "metadata": {"author": "X"},
        "relations": [
            {"to_index_id": "idx-other", "rel_type": "cites"}
        ]
    })
    parsed = librarian.parse_response(mock_response)
    assert parsed["index_id"] == "idx-abc"
    assert parsed["domain"] == "article"
    assert parsed["relations"][0]["rel_type"] == "cites"


def test_parse_response_raises_on_missing_required_field():
    bad_response = json.dumps({"index_id": "x"})  # missing domain, key, searchable
    with pytest.raises(ValueError):
        librarian.parse_response(bad_response)


def test_index_write_invokes_librarian_and_persists(tmp_memex_home, tmp_path):
    """End-to-end harness test with mocked LLM call."""
    from scripts import install, stores
    install.run()

    # Create a target store
    md = tmp_path / "m"; md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "index_id TEXT NOT NULL UNIQUE, "
        "title TEXT NOT NULL, "
        "body TEXT NOT NULL"
        ");"
    )
    stores.create_store("test-articles", str(tmp_path / "ta.db"), str(md))

    mock_llm = MagicMock(return_value=json.dumps({
        "index_id": "idx-test-1",
        "key": "hello-world",
        "domain": "article",
        "searchable": "hello world body content",
        "metadata": {"topic": "greeting"},
        "relations": []
    }))

    with patch("scripts.agents.librarian._invoke_llm", mock_llm), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00" * 4):
        result = librarian.index_write(
            payload={"title": "Hello", "body": "hello world body content"},
            target_store="test-articles",
            target_table="articles",
            caller_agent_id="librarian-1",
        )

    assert result["index_id"] == "idx-test-1"

    # Verify index.db row was written
    from scripts.db import memex_home
    from scripts.db import get_connection
    conn = get_connection(str(memex_home() / "index.db"))
    row = conn.execute("SELECT * FROM documents WHERE index_id = ?", ("idx-test-1",)).fetchone()
    conn.close()
    assert row is not None
    assert row["domain"] == "article"

    # Verify target store row was written
    rows = stores.query("test-articles", "SELECT * FROM articles WHERE index_id = ?", ("idx-test-1",))
    assert len(rows) == 1
    assert rows[0]["title"] == "Hello"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_librarian_harness.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

Create `prompts/librarian.md`:

```markdown
# Librarian Subagent Prompt

You are the Memex Librarian. Your profile is reproduced below — read it
carefully; it is the authoritative description of your role and constraints.

---

{{LIBRARIAN_PROFILE}}

---

## Task

A writing agent has submitted a document for indexing. Below is the
payload and metadata. Produce a JSON response with the fields required
by the Memex Index schema.

## Inputs

- **Target store:** `{{TARGET_STORE}}`
- **Caller agent id:** `{{CALLER_AGENT_ID}}`
- **Payload (JSON):**

```json
{{PAYLOAD_JSON}}
```

- **Existing index snippet (for context — up to 20 recently-related entries):**

```json
{{EXISTING_INDEX_SNIPPET}}
```

## Required output

Respond with a single JSON object, no surrounding text:

```json
{
  "index_id":   "<a stable unique identifier; UUIDv7 preferred>",
  "key":        "<human-readable slug, lowercase-dash>",
  "domain":     "<one of: article | decision | meeting | spec | plan | adr | capture | synthesis | ...>",
  "searchable": "<curated text for FTS5 indexing — title, key phrases, abstract>",
  "metadata":   { "<arbitrary JSON keys>": "<values>" },
  "relations":  [
    { "to_index_id": "<existing index_id from the snippet>", "rel_type": "<open-ended; pick semantic verb>" }
  ]
}
```

## Rules

- Only assert `relations` to index_ids that appear in the provided snippet.
  Never invent index_ids.
- `domain` should reflect the document's nature, not the target store.
  (A meeting transcript going into `brain.db` is still domain `meeting`.)
- If domain is unclear, return `"domain": "uncertain"` and explain in metadata.
- `rel_type` is open-ended — pick the verb that best captures the relationship.
  Examples: `cites`, `derives`, `supersedes`, `refutes`, `depends-on`, `informs`,
  `contains`, `mentions`. Be consistent with your prior choices in this index.
- Conservative on confidence: prefer fewer well-grounded relations over many
  speculative ones.
```

Create `scripts/agents/librarian.py`:

```python
"""Librarian — LLM-driven indexing harness.

build_prompt: assemble the prompt text from the template + caller context.
parse_response: validate and coerce the LLM's JSON output.
index_write: top-level orchestration — invoke LLM, write to index.db,
              delegate to Core for target-store insertion.
"""
from __future__ import annotations
import json
import uuid
from pathlib import Path
from scripts import registry, stores, agents as agents_mod
from scripts.db import get_connection, memex_home
from scripts import embeddings


_REQUIRED_FIELDS = {"index_id", "key", "domain", "searchable"}


def _load_template() -> str:
    return Path("prompts/librarian.md").read_text()


def _get_profile(agent_id: str) -> str:
    agents_db = str(memex_home() / "agents.db")
    record = agents_mod.get_agent(agents_db, agent_id)
    if record is None:
        raise ValueError(f"Agent not registered: {agent_id}")
    return record["profile"]


def _recent_index_snippet(limit: int = 20) -> list[dict]:
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    rows = [dict(r) for r in conn.execute(
        "SELECT index_id, key, domain FROM documents ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )]
    conn.close()
    return rows


def build_prompt(
    payload,
    target_store: str,
    caller_agent_id: str,
    existing_index_snippet: list[dict] | None = None,
) -> str:
    if existing_index_snippet is None:
        existing_index_snippet = _recent_index_snippet()
    template = _load_template()
    profile = _get_profile("librarian-1")
    return (template
        .replace("{{LIBRARIAN_PROFILE}}", profile)
        .replace("{{TARGET_STORE}}", target_store)
        .replace("{{CALLER_AGENT_ID}}", caller_agent_id)
        .replace("{{PAYLOAD_JSON}}", json.dumps(payload, ensure_ascii=False, indent=2))
        .replace("{{EXISTING_INDEX_SNIPPET}}", json.dumps(existing_index_snippet, ensure_ascii=False, indent=2))
    )


def parse_response(response_text: str) -> dict:
    """Parse and validate the Librarian's JSON output."""
    # Strip code fences if present
    s = response_text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0] if s.endswith("```") else s
    parsed = json.loads(s.strip())
    missing = _REQUIRED_FIELDS - set(parsed.keys())
    if missing:
        raise ValueError(f"Librarian response missing fields: {missing}")
    parsed.setdefault("metadata", {})
    parsed.setdefault("relations", [])
    return parsed


def _invoke_llm(prompt: str) -> str:
    """Invoke the Librarian subagent via Claude Code's Task tool.

    Plan 2's implementation wires this to the actual subagent invocation
    mechanism. For testing, this is mocked. The exact mechanism (Task tool
    vs inline skill) is deferred per spec §14.
    """
    raise NotImplementedError(
        "Subagent invocation TBD — patch this in tests; wire to Task tool in production."
    )


def _encode_embedding(text: str) -> bytes:
    """Wrapper for embeddings.encode — patched in tests to skip API calls."""
    return embeddings.encode(text)


def index_write(
    payload: dict,
    target_store: str,
    target_table: str,
    caller_agent_id: str,
) -> dict:
    """Top-level write path. Returns the dict Librarian produced (plus
    the target store row's PK).
    """
    prompt = build_prompt(payload, target_store, caller_agent_id)
    response = _invoke_llm(prompt)
    extracted = parse_response(response)

    # If LLM didn't supply index_id, generate one
    if not extracted.get("index_id"):
        extracted["index_id"] = str(uuid.uuid4())

    # Compute embedding from searchable text
    embedding_blob = _encode_embedding(extracted["searchable"])

    # Write to index.db
    index_db_path = str(memex_home() / "index.db")
    conn = get_connection(index_db_path)
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, metadata, embedding, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            extracted["index_id"],
            extracted.get("key"),
            extracted["domain"],
            target_store,
            target_table,
            "",  # row_id filled in after target-store insert
            extracted["searchable"],
            json.dumps(extracted["metadata"]),
            embedding_blob,
            caller_agent_id,
        ),
    )
    for rel in extracted.get("relations", []):
        conn.execute(
            "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
            (extracted["index_id"], rel["to_index_id"], rel["rel_type"]),
        )
    conn.commit()
    conn.close()

    # Delegate to Core for target store
    insert_row = {**payload, "index_id": extracted["index_id"]}
    inserted = stores.insert(target_store, target_table, insert_row)

    # Update documents.row_id with the actual PK now that we know it
    conn = get_connection(index_db_path)
    conn.execute(
        "UPDATE documents SET row_id = ? WHERE index_id = ?",
        (str(inserted.get("id", "")), extracted["index_id"]),
    )
    conn.commit()
    conn.close()

    return {**extracted, "row_id": inserted.get("id")}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_librarian_harness.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add prompts/librarian.md scripts/agents/librarian.py tests/test_librarian_harness.py
git commit -m "feat(index): Librarian subagent harness — prompt builder, response parser, index_write"
```

---

## Task 9: Reference Librarian subagent — prompt + harness

**Files:**
- Create: `prompts/reference_librarian.md`
- Create: `scripts/agents/reference_librarian.py`
- Create: `tests/test_reference_librarian_harness.py`

- [ ] **Step 1: Write the failing test**

`tests/test_reference_librarian_harness.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from scripts.agents import reference_librarian as rl


def test_build_prompt_includes_profile(tmp_memex_home):
    from scripts import install
    install.run()
    prompt = rl.build_prompt(query="what is X?", caller_agent_id="reference-librarian-1")
    assert "Whitfield" in prompt
    assert "what is X?" in prompt


def test_parse_query_plan():
    mock_plan = json.dumps({
        "fts_query": "machine learning",
        "vector_query": "machine learning",
        "filters": {"domain": "article"},
        "limit": 10,
    })
    parsed = rl.parse_query_plan(mock_plan)
    assert parsed["fts_query"] == "machine learning"
    assert parsed["filters"]["domain"] == "article"


def test_execute_query_plan_fts_only(tmp_memex_home, tmp_path):
    """Test execution with FTS5 only (no embedding)."""
    from scripts import install
    install.run()
    # Seed an index entry
    from scripts.db import get_connection, memex_home
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("a", "x", "article", "no-store", "t", "1", "machine learning is great", "librarian-1"),
    )
    conn.commit()
    conn.close()

    plan = {
        "fts_query": "machine learning",
        "vector_query": None,
        "filters": {},
        "limit": 5,
    }
    results = rl.execute_query_plan(plan, with_embedding=False)
    ids = [r["index_id"] for r in results]
    assert "a" in ids


def test_ask_returns_ranked_results(tmp_memex_home):
    from scripts import install
    install.run()
    # Seed two entries with overlapping content
    from scripts.db import get_connection, memex_home
    conn = get_connection(str(memex_home() / "index.db"))
    for index_id, text in [("a", "cats are interesting"), ("b", "dogs are fun")]:
        conn.execute(
            "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (index_id, index_id, "article", "no-store", "t", index_id, text, "librarian-1"),
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
        results = rl.ask("tell me about cats")

    ids = [r["index_id"] for r in results]
    assert "a" in ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reference_librarian_harness.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Create `prompts/reference_librarian.md`:

```markdown
# Reference Librarian Subagent Prompt

You are the Memex Reference Librarian. Profile below.

---

{{REFERENCE_LIBRARIAN_PROFILE}}

---

## Task

A user or agent has asked the following question:

> {{QUERY}}

Produce a JSON query plan to resolve it against the Memex Index.

## Output schema

```json
{
  "fts_query":    "<FTS5 query string>",
  "vector_query": "<text to be embedded for vector similarity search; null to skip>",
  "filters":      { "domain": "<optional>", "store": "<optional>" },
  "limit":        <integer; default 10>
}
```

## Rules

- If the query is ambiguous, return `"clarify": "<one short question>"`
  instead of a plan. Do not guess.
- FTS5 query supports MATCH syntax (e.g., `"machine learning" OR ai`).
- Be conservative; over-broad queries return noisy results.
```

Create `scripts/agents/reference_librarian.py`:

```python
"""Reference Librarian — LLM-driven retrieval harness."""
from __future__ import annotations
import json
from pathlib import Path
from scripts.db import get_connection, memex_home
from scripts import embeddings, agents as agents_mod


def _get_profile(agent_id: str) -> str:
    agents_db = str(memex_home() / "agents.db")
    return agents_mod.get_agent(agents_db, agent_id)["profile"]


def build_prompt(query: str, caller_agent_id: str) -> str:
    template = Path("prompts/reference_librarian.md").read_text()
    profile = _get_profile("reference-librarian-1")
    return (template
        .replace("{{REFERENCE_LIBRARIAN_PROFILE}}", profile)
        .replace("{{QUERY}}", query)
    )


def parse_query_plan(response_text: str) -> dict:
    s = response_text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0] if s.endswith("```") else s
    return json.loads(s.strip())


def _invoke_llm(prompt: str) -> str:
    raise NotImplementedError("Subagent invocation TBD — see Librarian harness.")


def execute_query_plan(plan: dict, with_embedding: bool = True) -> list[dict]:
    """Execute a query plan against index.db. Returns ranked results."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)

    # Build base FTS query
    fts_q = plan.get("fts_query") or ""
    filters = plan.get("filters") or {}
    limit = plan.get("limit") or 10

    where_clauses = []
    params: list = []
    if filters.get("domain"):
        where_clauses.append("d.domain = ?")
        params.append(filters["domain"])
    if filters.get("store"):
        where_clauses.append("d.store = ?")
        params.append(filters["store"])

    where_extra = (" AND " + " AND ".join(where_clauses)) if where_clauses else ""

    fts_rows: list[dict] = []
    if fts_q:
        sql = f"""
            SELECT d.index_id, d.key, d.domain, d.store, d.table_name, d.row_id,
                   d.searchable, d.embedding
            FROM documents_fts f
            JOIN documents d ON d.rowid = f.rowid
            WHERE documents_fts MATCH ?{where_extra}
            ORDER BY rank
            LIMIT ?
        """
        fts_rows = [dict(r) for r in conn.execute(sql, (fts_q, *params, limit))]

    if not with_embedding or not plan.get("vector_query"):
        conn.close()
        return fts_rows

    # Vector cosine
    qvec_blob = embeddings.encode(plan["vector_query"])
    sql_all = f"""
        SELECT index_id, key, domain, store, table_name, row_id, searchable, embedding
        FROM documents d
        WHERE embedding IS NOT NULL{where_extra}
    """
    all_rows = [dict(r) for r in conn.execute(sql_all, params)]
    conn.close()

    # Compute cosine
    scored = []
    for r in all_rows:
        if r["embedding"]:
            score = embeddings.cosine(qvec_blob, r["embedding"])
            scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    # Merge fts + vector (simple: union, dedupe by index_id, prefer higher rank)
    seen = {r["index_id"]: r for r in fts_rows}
    for score, r in scored[:limit]:
        if r["index_id"] not in seen:
            seen[r["index_id"]] = r
    return list(seen.values())[:limit]


def ask(query: str) -> list[dict]:
    """Top-level read path. Returns ranked results."""
    prompt = build_prompt(query, caller_agent_id="reference-librarian-1")
    plan_text = _invoke_llm(prompt)
    plan = parse_query_plan(plan_text)
    return execute_query_plan(plan, with_embedding=False)  # default off in v2.0 baseline; flip when embeddings backfilled
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reference_librarian_harness.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add prompts/reference_librarian.md scripts/agents/reference_librarian.py tests/test_reference_librarian_harness.py
git commit -m "feat(index): Reference Librarian harness — query plan + hybrid retrieval execution"
```

---

## Task 10: Skills — `memex:index:*` SKILL.md files

**Files:**
- Create: `internal/index/write/SKILL.md`
- Create: `internal/index/search/SKILL.md`
- Create: `internal/index/archive/SKILL.md`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_skills_present.py`:

```python
INDEX_SKILLS = ["write", "search", "archive"]


def test_index_skills_present():
    for s in INDEX_SKILLS:
        p = Path(f"internal/index/{s}/SKILL.md")
        assert p.exists(), f"Missing skill: index/{s}"


def test_index_skills_have_frontmatter_name():
    for s in INDEX_SKILLS:
        content = Path(f"internal/index/{s}/SKILL.md").read_text()
        assert f"name: memex:index:{s}" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_skills_present.py::test_index_skills_present -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`internal/index/write/SKILL.md`:

```markdown
---
name: memex:index:write
description: Submit a document for centralized indexing by the Memex Librarian, then persist to the target store. This is the MANDATORY write path for all documents — never write directly to a store's document table. Returns the assigned index_id, key, domain, and relations.
---

# memex:index:write

## When to use

Any document — article, decision, meeting, spec, plan, capture, synthesis — that should be findable later. If the row carries an `index_id` column, it MUST go through this skill.

## Inputs

- `payload` — dict containing the document fields (title, body, etc.)
- `target_store` — registered store name (e.g., `article`, `atelier-projectX`)
- `target_table` — table within the target store
- `caller_agent_id` — the registered agent making the write (for attribution)

## What happens

1. Archivist writes the raw payload to `~/.memex/raw/` (content-addressable, idempotent).
2. Librarian (LLM subagent) reads payload + existing index snippet, decides `index_id`, `key`, `domain`, `searchable`, `metadata`, `relations`.
3. Embedding is computed for `searchable` and packed into a BLOB.
4. Index row + relations rows are written to `~/.memex/index.db` (COMMIT).
5. Target store row is written via Memex Core with `index_id` populated (separate COMMIT — eventually consistent, see spec §6.1).
6. Returns: `{index_id, key, domain, relations, row_id}`.

## Invocation

`scripts/agents/librarian.py:index_write(payload, target_store, target_table, caller_agent_id)`

## Errors

- `ValueError: Unknown store` — `target_store` not registered.
- `IntegrityError` — duplicate `index_id` (rare; LLM should generate unique).
- `ValueError: Agent not registered` — `caller_agent_id` not in agents.db.

## Atomicity contract

Index write commits BEFORE target store write. If the target store write fails, the Index row exists without a corresponding store row — an orphan. The Data Steward's next audit will detect and report it. See spec §6.1.
```

`internal/index/search/SKILL.md`:

```markdown
---
name: memex:index:search
description: Ask the Memex Reference Librarian a natural-language question. Returns a ranked list of relevant documents across every registered store, with full content fetched from target stores. Replaces direct querying of any single store for read operations.
---

# memex:index:search

## When to use

Any read where the answer might span multiple stores, or where the caller doesn't know which store holds the relevant content. Brain's `ask` skill wraps this directly. Atelier or any consumer can also invoke it.

## Inputs

- `query` — natural-language question
- (optional) `filters` — dict, e.g., `{"domain": "article", "store": "brain"}` to constrain
- (optional) `limit` — max results (default 10)

## What happens

1. Reference Librarian (LLM subagent) parses the query, builds an FTS5 + vector query plan.
2. Plan executes against `~/.memex/index.db`.
3. Top N candidate `index_id`s are returned.
4. For each candidate, the target row is fetched from its store via Core.
5. If a row fetch fails (transient orphan), it is logged + skipped. Data Steward is notified asynchronously.
6. Returns ranked list of dicts: `[{index_id, store, key, domain, body, relevance, ...}, ...]`.

## Invocation

`scripts/agents/reference_librarian.py:ask(query)`

## Notes

- Hybrid retrieval (FTS5 + vector cosine) is used when embeddings are present. In v2.0, embeddings are computed on write; backfill is not yet implemented (see Plan 4 for re-embed tooling).
```

`internal/index/archive/SKILL.md`:

```markdown
---
name: memex:index:archive
description: Explicitly archive a raw payload to ~/.memex/raw/ via the Archivist. Normally invoked internally by memex:index:write — exposed for cases where archival is desired without indexing (e.g., evidentiary capture of inputs that aren't documents).
---

# memex:index:archive

## When to use

Rare. Most callers use `memex:index:write` instead, which archives + indexes in one call. Use this skill when you need to preserve a raw byte stream without producing an Index entry.

## Inputs

- `payload` — bytes (or string, will be UTF-8 encoded)
- `filename` — suggested filename; the actual stored path includes a hash suffix

## What happens

Archivist canonicalizes (line endings normalized, outer whitespace stripped), computes SHA-256, writes to `~/.memex/raw/<hash-prefix>/<stem>-<hash8>.<ext>`. Idempotent: same canonical payload → same path.

## Invocation

`scripts/agents/archivist.py:archive(payload, filename)`

Returns: `{"hash": "<sha256>", "path": "<absolute path>"}`
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_skills_present.py -v`
Expected: All PASSED.

- [ ] **Step 5: Commit**

```bash
git add internal/index/
git commit -m "docs(index): SKILL.md for memex:index:write, search, archive"
```

---

## Task 11: Skills — `memex:steward:*` and `memex:dba:*`

**Files:**
- Create: `internal/steward/audit/SKILL.md`
- Create: `internal/steward/audit-store/SKILL.md`
- Create: `internal/steward/reconcile-orphan/SKILL.md`
- Create: `internal/dba/checkpoint/SKILL.md`
- Create: `internal/dba/integrity-check/SKILL.md`
- Create: `internal/dba/vacuum/SKILL.md`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_skills_present.py`:

```python
STEWARD_SKILLS = ["audit", "audit-store", "reconcile-orphan"]
DBA_SKILLS = ["checkpoint", "integrity-check", "vacuum"]


def test_steward_skills_present():
    for s in STEWARD_SKILLS:
        p = Path(f"internal/steward/{s}/SKILL.md")
        assert p.exists()


def test_dba_skills_present():
    for s in DBA_SKILLS:
        p = Path(f"internal/dba/{s}/SKILL.md")
        assert p.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`internal/steward/audit/SKILL.md`:

```markdown
---
name: memex:steward:audit
description: Run a full integrity audit across the Memex Index and all registered stores. Detects orphans, broken relations, schema drift. Writes a structured audit report to ~/.memex/audits/. Read-only — never auto-fixes.
---

# memex:steward:audit

## When to use

- Scheduled maintenance (weekly/monthly recommended).
- After bulk operations (large ingests, mass deletes).
- Before a backup, to ensure clean snapshot.

## Inputs

None.

## Behavior

Invokes the Data Steward's audit primitives in sequence: find_orphans, find_broken_relations, retention policy verification (Plan 2 implements orphans + broken relations; retention verification is deferred).

## Invocation

`scripts/agents/data_steward.py:audit(index_db_path)`

Returns: absolute path to the generated report.
```

`internal/steward/audit-store/SKILL.md`:

```markdown
---
name: memex:steward:audit-store
description: Run an integrity audit scoped to a single registered store (reverse orphans + schema drift). Lighter than full audit.
---

# memex:steward:audit-store

## Inputs

- `store_name` — registered store to audit
- `table` — table within the store to scan for reverse orphans

## Invocation

`scripts/agents/data_steward.py:find_reverse_orphans(index_db_path, store_name, table)`
```

`internal/steward/reconcile-orphan/SKILL.md`:

```markdown
---
name: memex:steward:reconcile-orphan
description: Authorized fix-up of a flagged orphan (Index → missing-store-row, or store-row → missing-Index-entry). Requires explicit invocation; never automatic.
---

# memex:steward:reconcile-orphan

## When to use

After reviewing an audit report and deciding how to resolve a specific finding.

## Inputs

- `index_id` — the orphaned row's identifier
- `action` — one of:
  - `delete-index` — remove the documents row and its relations (target row is already gone)
  - `reindex` — re-run Librarian on the target store row (fixes reverse orphan)
  - `note` — leave as-is but mark the finding as acknowledged in the audit log

## Invocation

Implementation deferred to Plan 3 acceptance; v2.0 Plan 2 ships only the SKILL.md describing the contract.
```

`internal/dba/checkpoint/SKILL.md`:

```markdown
---
name: memex:dba:checkpoint
description: Run a WAL checkpoint on a registered store. Mode defaults to PASSIVE.
---

# memex:dba:checkpoint

## Inputs

- `store_name` — registered store
- `mode` — PASSIVE | FULL | RESTART | TRUNCATE (default PASSIVE)

## Invocation

`scripts/agents/dba.py:checkpoint(db_path, mode)`
```

`internal/dba/integrity-check/SKILL.md`:

```markdown
---
name: memex:dba:integrity-check
description: Run PRAGMA integrity_check on a registered store. Returns 'ok' if clean, otherwise a string describing issues.
---

# memex:dba:integrity-check

## Inputs

- `store_name`

## Invocation

`scripts/agents/dba.py:integrity_check(db_path)`
```

`internal/dba/vacuum/SKILL.md`:

```markdown
---
name: memex:dba:vacuum
description: Run VACUUM on a registered store to reclaim space and defragment. Should be run during maintenance windows, not under live load.
---

# memex:dba:vacuum

## Inputs

- `store_name`

## Invocation

`scripts/agents/dba.py:vacuum(db_path)`
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_skills_present.py -v`
Expected: All PASSED.

- [ ] **Step 5: Commit**

```bash
git add internal/steward/ internal/dba/
git commit -m "docs(index): SKILL.md for memex:steward:* and memex:dba:*"
```

---

## Task 12: Update `memex:run` routing for Plan 2 procedures

**Files:**
- Modify: `skills/run/SKILL.md`
- Modify: `tests/test_skills_present.py`

> Per spec §8.0 the plugin manifest registers ONLY `memex:run`. `plugin.json` is NOT touched in Plan 2. Plan 2's nine new procedures live at `internal/<category>/<name>/SKILL.md` and become reachable by appending routing rows to the body of `skills/run/SKILL.md`. Agents read `memex:run` on demand and follow the routing entries via the Read tool.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_skills_present.py`:

```python
PLAN2_PROCEDURES = [
    ("index", "write"),
    ("index", "search"),
    ("index", "archive"),
    ("steward", "audit"),
    ("steward", "audit-store"),
    ("steward", "reconcile-orphan"),
    ("dba", "checkpoint"),
    ("dba", "integrity-check"),
    ("dba", "vacuum"),
]


def test_run_skill_routes_to_plan2_procedures():
    """memex:run must contain routing entries for every Plan 2 procedure,
    so agents can discover them without Claude Code auto-loading their
    descriptions."""
    run_content = Path("skills/run/SKILL.md").read_text(encoding="utf-8")
    for category, name in PLAN2_PROCEDURES:
        expected = f"internal/{category}/{name}/SKILL.md"
        assert expected in run_content, (
            f"memex:run missing routing entry for {expected}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_skills_present.py::test_run_skill_routes_to_plan2_procedures -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Append a new section to `skills/run/SKILL.md` (after the existing "v2 Core CRUD routing (agent-facing — not for end users)" section):

```markdown
## v2 Index, Steward, and DBA routing

Plan 2 adds the mandatory write-path gateway (Index + Librarian), the
read-path retrieval layer (Reference Librarian), and storage-substrate
ops (DBA + Data Steward). These 9 procedures live at
`internal/<category>/<name>/SKILL.md` and are reachable only via this
routing table. They are agent-facing — not directly invoked by the
human user.

| Agent intent | Internal procedure |
|---|---|
| Submit a document for indexing by the Librarian, then persist to a target store (MANDATORY write path for any row carrying an `index_id`) | `internal/index/write/SKILL.md` |
| Ask the Reference Librarian a natural-language question; returns ranked results across every registered store | `internal/index/search/SKILL.md` |
| Explicitly archive a raw payload via the Archivist without indexing it | `internal/index/archive/SKILL.md` |
| Run a full integrity audit across the Index and every registered store | `internal/steward/audit/SKILL.md` |
| Run an integrity audit scoped to a single registered store | `internal/steward/audit-store/SKILL.md` |
| Authorized fix-up of a flagged orphan (delete-index / reindex / note) | `internal/steward/reconcile-orphan/SKILL.md` |
| Run a WAL checkpoint on a registered store | `internal/dba/checkpoint/SKILL.md` |
| Run `PRAGMA integrity_check` on a registered store | `internal/dba/integrity-check/SKILL.md` |
| Run `VACUUM` on a registered store to reclaim space and defragment | `internal/dba/vacuum/SKILL.md` |

The Python implementations live under `scripts/agents/`
(`librarian.py`, `reference_librarian.py`, `archivist.py`, `dba.py`,
`data_steward.py`). Each SKILL.md is a short documentation wrapper; the
agent reads it for the API contract, then calls the implementation.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_skills_present.py -v`
Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add skills/run/SKILL.md tests/test_skills_present.py
git commit -m "feat(index): extend memex:run routing for Index/Steward/DBA procedures"
```

---

## Task 13: End-to-end smoke test (Plan 2)

**Files:**
- Create: `tests/test_smoke_plan2.py`

- [ ] **Step 1: Write the failing test**

`tests/test_smoke_plan2.py`:

```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from scripts import install, stores
from scripts.agents import librarian, reference_librarian, data_steward
from scripts.db import memex_home, get_connection


def test_e2e_index_write_and_search(tmp_memex_home, tmp_path):
    """Full write → index → search → orphan-audit cycle."""
    install.run()

    # Create a target store
    md = tmp_path / "m"; md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "index_id TEXT NOT NULL UNIQUE, "
        "title TEXT NOT NULL, "
        "body TEXT NOT NULL"
        ");"
    )
    stores.create_store("test-articles", str(tmp_path / "ta.db"), str(md))

    # Mock Librarian LLM
    mock_lib_response = json.dumps({
        "index_id": "idx-1",
        "key": "hello-world",
        "domain": "article",
        "searchable": "hello world greeting body",
        "metadata": {},
        "relations": []
    })

    # Mock Reference Librarian LLM
    mock_rl_plan = json.dumps({
        "fts_query": "hello",
        "vector_query": None,
        "filters": {},
        "limit": 10,
    })

    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib_response), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"), \
         patch("scripts.agents.reference_librarian._invoke_llm", return_value=mock_rl_plan):

        # Write
        result = librarian.index_write(
            payload={"title": "Hello", "body": "hello world greeting body"},
            target_store="test-articles",
            target_table="articles",
            caller_agent_id="librarian-1",
        )
        assert result["index_id"] == "idx-1"

        # Search
        results = reference_librarian.ask("hello")
        ids = [r["index_id"] for r in results]
        assert "idx-1" in ids

    # Audit should find no orphans (everything consistent)
    index_db = str(memex_home() / "index.db")
    orphans = data_steward.find_orphans(index_db)
    assert orphans == []


def test_e2e_orphan_creation_and_audit(tmp_memex_home, tmp_path):
    """Simulate the inconsistency window: index row exists, store row doesn't.
    Data Steward must detect."""
    install.run()

    md = tmp_path / "m"; md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "index_id TEXT NOT NULL UNIQUE, "
        "body TEXT"
        ");"
    )
    stores.create_store("test-articles", str(tmp_path / "ta.db"), str(md))

    # Manually create an index row pointing to a nonexistent store row.
    index_db_path = str(memex_home() / "index.db")
    conn = get_connection(index_db_path)
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("idx-orphan", "x", "article", "test-articles", "articles", "99999", "txt", "librarian-1"),
    )
    conn.commit()
    conn.close()

    # Audit should detect
    report_path = data_steward.audit(index_db_path)
    content = Path(report_path).read_text()
    assert "idx-orphan" in content
    assert "Severity" in content


def test_e2e_install_is_complete():
    """Confirms install.run produces a fully bootstrapped Memex install."""
    home = memex_home()
    assert (home / "agents.db").exists()
    assert (home / "index.db").exists()
    assert (home / "registry.json").exists()
    assert (home / "raw").is_dir()
    assert (home / "audits").is_dir()
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_smoke_plan2.py -v`
Expected: PASS if all prior tasks are correctly implemented.

- [ ] **Step 3: (No implementation change — this is integration)**

- [ ] **Step 4: Run full suite**

Run: `pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_smoke_plan2.py
git commit -m "test(index): end-to-end smoke test exercising write+search+audit with mocked LLM"
```

---

## Task 14: Plan 2 doc

**Files:**
- Create: `docs/INDEX.md`

- [ ] **Step 1: Write the failing test**

Create `tests/test_index_docs.py`:

```python
from pathlib import Path


def test_index_doc_exists():
    assert Path("docs/INDEX.md").exists()


def test_index_doc_lists_internal_agents():
    content = Path("docs/INDEX.md").read_text()
    for agent in ["Librarian", "Reference Librarian", "Archivist", "Database Administrator", "Data Steward"]:
        assert agent in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_index_docs.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Create `docs/INDEX.md`:

```markdown
# Memex Index + Internal Agents (Plan 2)

Plan 2 builds the Memex Index — the mandatory write-path gateway and
read-path retrieval layer — plus the five internal agents.

## What Plan 2 ships

### Internal agents (seeded into agents.db on install)

| Agent | Role | Implementation |
|---|---|---|
| Librarian (Dr. Lakshmi Iyer-Ranganathan) | Librarian | LLM subagent (prompts/librarian.md) + scripts/agents/librarian.py harness |
| Reference Librarian (Dr. Eleanor Whitfield) | Reference Librarian | LLM subagent (prompts/reference_librarian.md) + scripts/agents/reference_librarian.py |
| Archivist (Dr. Heinrich Mühlbauer) | Archivist | Deterministic Python (scripts/agents/archivist.py) |
| Database Administrator (Dr. Rajesh Subramanian) | Database Administrator | Deterministic Python (scripts/agents/dba.py) |
| Data Steward (Dr. Ingrid Bergström) | Data Steward | Deterministic Python (scripts/agents/data_steward.py) |

### Skills

Per spec §8.0, the plugin registers only `memex:run`. The 9 procedures
below live at `internal/<category>/<name>/SKILL.md` and are reached on
demand through the routing table inside `skills/run/SKILL.md`.

| Procedure | Path | Purpose |
|---|---|---|
| memex:index:write | internal/index/write/SKILL.md | Mandatory write path: archive → Librarian → Core |
| memex:index:search | internal/index/search/SKILL.md | Read path: Reference Librarian → ranked results |
| memex:index:archive | internal/index/archive/SKILL.md | Explicit raw archive (rare) |
| memex:steward:audit | internal/steward/audit/SKILL.md | Full integrity audit |
| memex:steward:audit-store | internal/steward/audit-store/SKILL.md | Per-store audit |
| memex:steward:reconcile-orphan | internal/steward/reconcile-orphan/SKILL.md | Authorized orphan fix (Plan 3 fully implements) |
| memex:dba:checkpoint | internal/dba/checkpoint/SKILL.md | WAL checkpoint |
| memex:dba:integrity-check | internal/dba/integrity-check/SKILL.md | PRAGMA integrity_check |
| memex:dba:vacuum | internal/dba/vacuum/SKILL.md | VACUUM |

### Data

| File | Contents |
|---|---|
| ~/.memex/index.db | documents + relations + FTS5 + embeddings |
| ~/.memex/raw/ | Content-addressable raw archive |
| ~/.memex/audits/ | Data Steward reports |

## Atomicity contract

Index write commits BEFORE target store write. The brief inconsistency
window means a crash between the two writes leaves an orphan in index.db.
Data Steward audits detect orphans; resolution is authorized via
memex:steward:reconcile-orphan.

## What Plan 2 does NOT ship

- Brain skills (ingest/ask/capture/lint/synthesize) — Plan 3.
- Embedding backfill / re-embed tooling — Plan 4.
- Reconcile-orphan implementation — Plan 3.
- Onboarding flow for the human user — Plan 3.

## Acceptance criteria

1. `pytest tests/` passes 100% across all test files (Plan 1 + Plan 2).
2. `install.run()` is idempotent and creates index.db + seeds 5 internal agents.
3. The 9 new SKILL.md files exist at `internal/<category>/<name>/SKILL.md` with correct frontmatter.
4. `skills/run/SKILL.md` contains routing entries for all 9 new procedures.
5. `plugin.json` still registers only `memex:run` (no new top-level skills).
6. The end-to-end smoke test in tests/test_smoke_plan2.py passes with mocked LLM.
7. Manual sanity check: invoke Librarian against real Claude API, confirm
   reasonable index_id/domain/relations output on a sample article.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_index_docs.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add docs/INDEX.md tests/test_index_docs.py
git commit -m "docs(index): Plan 2 acceptance criteria and architecture overview"
```

---

## Plan 2 acceptance checklist (final)

- [ ] `pytest tests/` reports 100% green
- [ ] `install.run()` idempotent; seeds 5 internal agents; creates index.db
- [ ] `~/.memex/index.db` schema matches spec §5.2
- [ ] 9 new SKILL.md files present at `internal/<category>/<name>/SKILL.md` with correct frontmatter
- [ ] `skills/run/SKILL.md` contains routing entries for all 9 Plan 2 procedures
- [ ] `plugin.json` still registers only `memex:run` (per spec §8.0)
- [ ] Plan 2 smoke test passes (mocked LLM)
- [ ] Manual eval: real LLM invocation on a sample article produces reasonable Librarian output
- [ ] Final commit clean

Plan 3 (Brain) builds on this:
- `memex:brain:ingest` invokes `memex:index:write` with `target_store="article"`.
- `memex:brain:ask` invokes `memex:index:search`.
- `memex:brain:capture`, `lint`, `synthesize` round out Brain's surface.
- Onboarding flow registers the human user on first invocation.

Plan 4 (Packaging) provides install scripts, v1-plugin migration, and docs.
