"""Regression tests for the public `ensure_internal_agents(db_path)` API.

This API is memex's half of atelier issue #9 — the architectural follow-up
to PR #19. Any external consumer that touches `agents.db` (atelier's
bootstrap, future plugins, manual restore scripts) is expected to call
`ensure_internal_agents(db_path)` afterwards to re-establish the invariant
that the 5 internal Memex agents (`librarian-1`, `reference-librarian-1`,
`archivist-1`, `dba-1`, `data-steward-1`) are present.

The function must be:
  - public (top-level import from `scripts.install`),
  - idempotent (safe to call N times),
  - schema-aware (creates `agents.db` schema if absent),
  - return-rich (status / missing_before / present_after dict),
  - hard-failing (raise InternalAgentsMissingError if seeding fails to
    land all 5).
"""

from __future__ import annotations

import sqlite3
from unittest import mock

import pytest

from scripts import agents
from scripts._internal_agents_seed import INTERNAL_AGENTS
from scripts.db import get_connection
from scripts.paths import DB_DIR

_EXPECTED_AGENT_IDS = sorted(a["agent_id"] for a in INTERNAL_AGENTS)


def _make_empty_agents_db(path) -> str:
    """Create an `agents.db` with the schema applied but no internal-agent rows."""
    conn = get_connection(str(path))
    conn.executescript((DB_DIR / "agents.sql").read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return str(path)


def test_ensure_internal_agents_seeds_missing(tmp_path):
    """Empty schema-only DB → seeds all 5, reports them as missing_before."""
    from scripts.install import ensure_internal_agents

    db_path = _make_empty_agents_db(tmp_path / "agents.db")

    result = ensure_internal_agents(db_path)

    assert result["status"] == "repaired"
    assert sorted(result["missing_before"]) == _EXPECTED_AGENT_IDS
    assert sorted(result["present_after"]) == _EXPECTED_AGENT_IDS

    # Verify via direct read.
    listed_ids = {a["id"] for a in agents.list_agents(db_path)}
    assert listed_ids == set(_EXPECTED_AGENT_IDS)


def test_ensure_internal_agents_idempotent(tmp_path):
    """Second call must be a no-op reporting already_present."""
    from scripts.install import ensure_internal_agents

    db_path = _make_empty_agents_db(tmp_path / "agents.db")

    first = ensure_internal_agents(db_path)
    second = ensure_internal_agents(db_path)

    assert first["status"] == "repaired"
    assert second["status"] == "already_present"
    assert second["missing_before"] == []
    assert sorted(second["present_after"]) == _EXPECTED_AGENT_IDS


def test_ensure_internal_agents_returns_status(tmp_path):
    """Contract check: return dict has the expected keys and types."""
    from scripts.install import ensure_internal_agents

    db_path = _make_empty_agents_db(tmp_path / "agents.db")

    result = ensure_internal_agents(db_path)

    assert isinstance(result, dict)
    assert set(result.keys()) >= {"status", "missing_before", "present_after"}
    assert result["status"] in {"already_present", "repaired"}
    assert isinstance(result["missing_before"], list)
    assert isinstance(result["present_after"], list)
    assert all(isinstance(x, str) for x in result["missing_before"])
    assert all(isinstance(x, str) for x in result["present_after"])


def test_ensure_internal_agents_creates_schema_when_db_absent(tmp_path):
    """If the DB file doesn't exist at all, ensure_internal_agents must
    initialise the schema and then seed. This is the atelier-bootstrap
    early-call shape (call before any other consumer has touched the DB)."""
    from scripts.install import ensure_internal_agents

    db_path = str(tmp_path / "fresh_agents.db")
    # Note: file deliberately does NOT exist yet.

    result = ensure_internal_agents(db_path)

    assert result["status"] == "repaired"
    assert sorted(result["present_after"]) == _EXPECTED_AGENT_IDS


def test_ensure_internal_agents_raises_if_seeding_fails(tmp_path):
    """If seeding silently no-ops (mocked), the post-condition must raise
    InternalAgentsMissingError with the missing IDs in the message."""
    from scripts.install import InternalAgentsMissingError, ensure_internal_agents

    db_path = _make_empty_agents_db(tmp_path / "agents.db")

    # Stub out the underlying seed step so no rows get written.
    with (
        mock.patch("scripts.install._seed_internal", lambda _p: None),
        pytest.raises(InternalAgentsMissingError) as excinfo,
    ):
        ensure_internal_agents(db_path)

    # Every expected ID should be referenced in the error message.
    msg = str(excinfo.value)
    for aid in _EXPECTED_AGENT_IDS:
        assert aid in msg


def test_ensure_internal_agents_repairs_partial_seed(tmp_path):
    """A DB with SOME internal agents present and others missing must be
    healed — the missing ones get seeded, the present ones are left alone."""
    from scripts import roles
    from scripts.install import ensure_internal_agents

    db_path = _make_empty_agents_db(tmp_path / "agents.db")

    # Pre-seed only librarian-1 by hand to simulate partial state.
    librarian_entry = next(a for a in INTERNAL_AGENTS if a["agent_id"] == "librarian-1")
    role = roles.create_role(db_path, librarian_entry["role_name"], librarian_entry["role_desc"])
    agents.create_agent(
        db_path,
        librarian_entry["agent_id"],
        librarian_entry["agent_name"],
        role["id"],
        librarian_entry["agent_profile"],
    )

    result = ensure_internal_agents(db_path)

    assert result["status"] == "repaired"
    assert "librarian-1" not in result["missing_before"]
    assert sorted(result["present_after"]) == _EXPECTED_AGENT_IDS
    assert len(result["missing_before"]) == 4


def test_ensure_internal_agents_raises_on_corrupted_schema(tmp_path):
    """Pre-existing DB file with garbage bytes (not a valid SQLite file) must
    raise a clean low-level error rather than silently succeed or return a
    misleading dict. Pins current behavior so future contributors don't
    accidentally swallow the error."""
    from scripts.install import ensure_internal_agents

    db_path = tmp_path / "agents.db"
    db_path.write_bytes(b"this is not a sqlite database, just garbage bytes\x00\xff")

    with pytest.raises(sqlite3.DatabaseError):
        ensure_internal_agents(str(db_path))


def test_ensure_internal_agents_raises_on_directory_path(tmp_path):
    """Passing a path that points at a directory (not a file) must raise a
    clean error rather than silently mis-treat the path. Pins current
    behavior."""
    from scripts.install import ensure_internal_agents

    dir_path = tmp_path / "not_a_file"
    dir_path.mkdir()

    # The exact exception class is whichever Python/sqlite3 surfaces for
    # "this path is a directory" — typically IsADirectoryError or
    # sqlite3.OperationalError. Pin: it must raise *something* loud.
    with pytest.raises((IsADirectoryError, OSError, sqlite3.OperationalError)):
        ensure_internal_agents(str(dir_path))
