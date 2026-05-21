"""Regression: install.run() must always end with all 5 internal Memex
agents present in `~/.memex/agents.db`, even when the DB is pre-existing,
partially populated by another consumer (e.g. Atelier seeded its roster
first), or has a stale `meta.seed_hash` claiming "already seeded" while
the actual rows are missing.

Surfaced bug: on a real install the user's `~/.memex/agents.db` ended up
with 61 atelier roles but zero internal Memex agents (librarian-1,
reference-librarian-1, archivist-1, dba-1, data-steward-1), and no
`meta` table. Any operation needing librarian classification raised
`ValueError: Agent not registered: librarian-1`. Root cause: the
`_seed_internal` short-circuit trusts `meta.seed_hash` blindly and
returns even if the agent rows are missing, and `install.run()` does not
verify its own post-condition.
"""

from __future__ import annotations

import io
import sys

import pytest

from scripts import agents, install, roles
from scripts._internal_agents_seed import INTERNAL_AGENTS_HASH
from scripts.db import get_connection, memex_home

EXPECTED_INTERNAL_AGENT_IDS = {
    "librarian-1",
    "reference-librarian-1",
    "archivist-1",
    "dba-1",
    "data-steward-1",
}


def _internal_agent_ids_in(db_path: str) -> set[str]:
    return {a["id"] for a in agents.list_agents(db_path)} & EXPECTED_INTERNAL_AGENT_IDS


def test_install_seeds_all_5_internal_agents_on_clean_install(tmp_memex_home, monkeypatch):
    """Baseline: a clean install lands all 5 internal agents with non-empty profiles."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    install.run()

    db = str(memex_home() / "agents.db")
    listed = {a["id"]: a for a in agents.list_agents(db)}
    for aid in EXPECTED_INTERNAL_AGENT_IDS:
        assert aid in listed, f"internal agent {aid} missing after clean install"
        assert listed[aid]["profile"].strip(), f"{aid} profile is empty after install"


def test_install_reseeds_when_internal_agents_missing_with_stale_seed_hash(
    tmp_memex_home, monkeypatch
):
    """Recovery path: a previous install seeded the 5 agents (seed_hash recorded),
    but the agents.db was subsequently rebuilt or the rows wiped. Re-running
    install.run() MUST detect the missing rows and re-seed — not silently
    short-circuit on the stale seed_hash.

    This is the scenario observed on the real user's machine: a
    partially-rebuilt agents.db with no internal-agent rows."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\ny\n"))

    # First install — produces a fully-seeded DB with seed_hash recorded.
    install.run()
    db = str(memex_home() / "agents.db")
    assert _internal_agent_ids_in(db) == EXPECTED_INTERNAL_AGENT_IDS

    # Simulate the post-install corruption: delete the 5 internal agents and
    # their roles, leaving seed_hash in place (and any other roles such as
    # Atelier's roster untouched).
    conn = get_connection(db)
    try:
        conn.execute(
            "DELETE FROM agents WHERE id IN "
            "('librarian-1','reference-librarian-1','archivist-1','dba-1','data-steward-1')"
        )
        conn.execute(
            "DELETE FROM roles WHERE name IN "
            "('Librarian','Reference Librarian','Archivist',"
            "'Database Administrator','Data Steward')"
        )
        # Confirm the stale seed_hash is still there — that is the bug's surface.
        row = conn.execute("SELECT value FROM meta WHERE key = 'seed_hash'").fetchone()
        assert row is not None and row["value"] == INTERNAL_AGENTS_HASH
        conn.commit()
    finally:
        conn.close()

    assert _internal_agent_ids_in(db) == set()  # confirm setup

    # Re-running install must restore the missing 5 agents.
    install.run()

    assert _internal_agent_ids_in(db) == EXPECTED_INTERNAL_AGENT_IDS, (
        "install.run() did not re-seed missing internal agents — stale seed_hash "
        "short-circuit fired even though agent rows were absent"
    )


def test_install_seeds_when_db_pre_exists_with_third_party_roles(tmp_memex_home, monkeypatch):
    """Another reproduction of the live-machine state: `agents.db` exists
    with foreign roles (Atelier's roster) and no `meta` table at all. The
    first `install.run()` against this DB must seed the 5 internal agents
    alongside the existing rows.
    """
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))

    # Pre-create agents.db with foreign roles only — mirrors the broken state
    # observed on the user's machine.
    home = tmp_memex_home
    home.mkdir(parents=True, exist_ok=True)
    db_path = home / "agents.db"
    from scripts.paths import DB_DIR

    conn = get_connection(str(db_path))
    conn.executescript((DB_DIR / "agents.sql").read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO roles (name, description) VALUES (?, ?)",
        ("Backend Engineer", "Atelier-roster placeholder"),
    )
    conn.commit()
    conn.close()
    assert _internal_agent_ids_in(str(db_path)) == set()
    # Sanity check: no meta table on this pre-existing DB.
    conn = get_connection(str(db_path))
    has_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
    ).fetchone()
    conn.close()
    assert has_meta is None

    install.run()

    assert _internal_agent_ids_in(str(db_path)) == EXPECTED_INTERNAL_AGENT_IDS
    # Foreign roles preserved.
    role_names = {r["name"] for r in roles.list_roles(str(db_path))}
    assert "Backend Engineer" in role_names


def test_install_is_idempotent_on_full_seed(tmp_memex_home, monkeypatch):
    """Re-running install.run() against a fully-seeded DB must be a clean
    no-op — no UNIQUE violation, no duplicate rows, no row count change."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\ny\n"))

    install.run()
    db = str(memex_home() / "agents.db")
    first_count = len(agents.list_agents(db))
    assert _internal_agent_ids_in(db) == EXPECTED_INTERNAL_AGENT_IDS

    install.run()  # second invocation; must not raise on UNIQUE
    second_count = len(agents.list_agents(db))

    assert first_count == second_count
    assert _internal_agent_ids_in(db) == EXPECTED_INTERNAL_AGENT_IDS


def test_install_post_condition_raises_if_seed_silently_skipped(tmp_memex_home, monkeypatch):
    """If `_seed_internal` is bypassed (e.g. by an external bug) and returns
    without writing the 5 agents, `install.run()` MUST surface a loud error
    rather than returning clean. This guards the user-visible post-condition."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))

    def _broken_seed(_agents_db_path: str) -> None:
        # Simulate a silently-failed seed: return without seeding anything.
        return None

    monkeypatch.setattr(install, "_seed_internal", _broken_seed)

    with pytest.raises(Exception) as excinfo:
        install.run()
    # The error must name at least one missing internal agent so the
    # operator can diagnose without spelunking the DB.
    msg = str(excinfo.value).lower()
    assert "librarian-1" in msg or "internal agent" in msg, (
        f"post-condition error must identify missing internal agents; got: {excinfo.value!r}"
    )
