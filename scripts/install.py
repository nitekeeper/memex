"""One-shot ~/.memex/ bootstrap. v2.5.0: flock-protected, hash-pinned, consent-gated."""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

from scripts import agents, registry, roles
from scripts._internal_agents_seed import INTERNAL_AGENTS, INTERNAL_AGENTS_HASH
from scripts.db import get_connection, memex_home
from scripts.paths import DB_DIR


class InstallLockBusyError(RuntimeError):
    """Another scripts.install.run() is already in progress."""


class InternalAgentsMissingError(RuntimeError):
    """install.run() finished but one or more of the 5 internal Memex
    agents are not present in `~/.memex/agents.db`. Indicates either a
    failed seed step or post-install corruption (DB wiped/rebuilt by
    another process after seeding)."""


def ensure_internal_agents(db_path: str) -> dict:
    """Idempotently ensure the 5 internal Memex agents are present in `db_path`.

    Public hook for any consumer that touches `agents.db` directly
    (atelier's bootstrap, future plugins, manual restore scripts). Call
    this after the touch to re-establish the invariant.

    Initialises the schema if `db_path` does not yet exist. Seeds any
    missing internal agents (and their roles). Safe to call multiple times.

    Returns a dict with keys:
      - status:         "already_present" | "repaired"
      - missing_before: list[str]   agent IDs absent before this call
      - present_after:  list[str]   agent IDs present after this call (== all 5)

    Raises `InternalAgentsMissingError` if seeding fails to land all 5 agents.

    Concurrency: this function does not acquire a file lock. If you call
    it against ~/.memex/agents.db concurrently with a running
    `memex.install.run()`, both may attempt to seed the same rows. The
    seed is row-idempotent (uses get_agent checks; no duplicate INSERTs),
    so the worst case is wasted work. Serialize via your own mechanism
    if that worst case matters.
    """
    path = Path(db_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = get_connection(str(path))
        try:
            conn.executescript((DB_DIR / "agents.sql").read_text(encoding="utf-8"))
            conn.commit()
        finally:
            conn.close()

    missing_before = _missing_internal_agent_ids(str(path))

    if not missing_before:
        return {
            "status": "already_present",
            "missing_before": [],
            "present_after": list(_INTERNAL_AGENT_IDS),
        }

    _seed_internal(str(path))

    missing_after = _missing_internal_agent_ids(str(path))
    if missing_after:
        raise InternalAgentsMissingError(
            f"ensure_internal_agents({db_path}) finished but "
            f"{len(missing_after)} internal Memex agent(s) are still missing: "
            f"{missing_after} (was missing before: {missing_before})."
        )

    return {
        "status": "repaired",
        "missing_before": missing_before,
        "present_after": list(_INTERNAL_AGENT_IDS),
    }


def _acquire_lock(lock_path: Path):
    """Cross-platform exclusive lock with O_NOFOLLOW.

    Returns the open file handle. Caller MUST close it to release the lock.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(lock_path), flags, 0o600)
    except OSError as e:
        if e.errno == getattr(errno, "ELOOP", 40):
            raise InstallLockBusyError(
                f"Lock path is a symlink: {lock_path}. Refusing to follow."
            ) from e
        raise

    fh = os.fdopen(fd, "r+")
    if sys.platform.startswith("win") or os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as e:
            fh.close()
            if e.errno in (errno.EACCES, getattr(errno, "EDEADLK", 35)):
                raise InstallLockBusyError(
                    f"Another Memex install is already running (lock at {lock_path})."
                ) from e
            raise
    else:
        import fcntl

        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            fh.close()
            raise InstallLockBusyError(
                f"Another Memex install is already running (lock at {lock_path})."
            ) from e
        except OSError as e:
            fh.close()
            raise InstallLockBusyError(f"Lock acquisition failed at {lock_path}: {e}.") from e
    return fh


def _read_consent_from_stdin() -> bool:
    """Read y/n from stdin.

    Returns True for proceed, False for decline. Exits the process on invalid input.
    Empty stdin (no SKILL invocation; manual CLI from terminal) → proceed.
    """
    try:
        line = sys.stdin.readline().strip().lower()
    except Exception:
        return True
    if not line:
        return True
    if line == "y":
        return True
    if line == "n":
        return False
    sys.stderr.write(
        f"install.py: invalid consent token {line!r}; expected 'y' or 'n'. Aborting.\n"
    )
    sys.exit(2)


def run() -> None:
    if not _read_consent_from_stdin():
        sys.exit(1)

    home = memex_home()
    home.mkdir(parents=True, exist_ok=True)

    lock_fh = _acquire_lock(home / ".install.lock")
    try:
        # Plan 4: archive v1 if present (no-op otherwise) — symlink-safe per §F.
        from scripts import upgrade_from_v1

        upgrade_from_v1.archive_v1()

        for sub in ("raw", "backups", "audits", "templates"):
            (home / sub).mkdir(exist_ok=True)

        agents_db_path = home / "agents.db"
        if not agents_db_path.exists():
            conn = get_connection(str(agents_db_path))
            conn.executescript((DB_DIR / "agents.sql").read_text(encoding="utf-8"))
            conn.commit()
            conn.close()
        if registry.get_store("agents") is None:
            registry.register_store("agents", str(agents_db_path), schema_version="v1")

        _seed_internal(str(agents_db_path))
        _verify_internal_agents_present(str(agents_db_path))

        index_db_path = home / "index.db"
        if not index_db_path.exists():
            conn = get_connection(str(index_db_path))
            conn.executescript((DB_DIR / "migrations_table.sql").read_text(encoding="utf-8"))
            conn.executescript((DB_DIR / "index.sql").read_text(encoding="utf-8"))
            conn.execute("INSERT INTO migrations (filename) VALUES (?)", ("index.sql",))
            conn.commit()
            conn.close()
        else:
            _migrate_index_db_to_unique_key(str(index_db_path))
            # Re-apply index.sql so additive `CREATE TABLE/INDEX IF NOT EXISTS`
            # statements (e.g. the v2.7.0 GraphRAG community layer) land on
            # pre-existing index.db installs. index.sql is re-entrant by
            # construction; existing tables/triggers are untouched.
            _apply_index_schema_additive(str(index_db_path))
        if registry.get_store("index") is None:
            registry.register_store("index", str(index_db_path), schema_version="v1")

        article_db_path = home / "article.db"
        if not article_db_path.exists():
            conn = get_connection(str(article_db_path))
            conn.executescript((DB_DIR / "migrations_table.sql").read_text())
            conn.executescript((DB_DIR / "brain.sql").read_text())
            conn.execute("INSERT INTO migrations (filename) VALUES (?)", ("brain.sql",))
            conn.commit()
            conn.close()
        if registry.get_store("article") is None:
            registry.register_store("article", str(article_db_path), schema_version="v1")
    finally:
        lock_fh.close()


def _migrate_index_db_to_unique_key(index_db_path: str) -> None:
    """In-place migration: replace non-unique documents_key_idx with the
    UNIQUE invariant introduced in spec §6.4.

    Idempotent. On pre-existing duplicate keys, raises ValueError listing
    the offending keys — the install does not silently merge or delete.
    """
    conn = get_connection(index_db_path)
    try:
        has_unique = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='documents_key_unique_idx'"
        ).fetchone()
        if has_unique:
            return  # already migrated
        dupes = [
            (r["key"], r["n"])
            for r in conn.execute(
                "SELECT key, COUNT(*) AS n FROM documents "
                "WHERE key IS NOT NULL GROUP BY key HAVING n > 1"
            )
        ]
        if dupes:
            preview = ", ".join(f"{k!r} x{n}" for k, n in dupes[:5])
            more = f" (+{len(dupes) - 5} more)" if len(dupes) > 5 else ""
            raise ValueError(
                f"Cannot apply UNIQUE(documents.key): {len(dupes)} duplicate key(s) "
                f"already present: {preview}{more}. Resolve via memex:steward, then re-run install."
            )
        conn.execute("DROP INDEX IF EXISTS documents_key_idx")
        conn.execute("CREATE UNIQUE INDEX documents_key_unique_idx ON documents(key)")
        conn.commit()
    finally:
        conn.close()


def _apply_index_schema_additive(index_db_path: str) -> None:
    """Re-run db/index.sql against an existing index.db.

    index.sql is composed exclusively of re-entrant statements
    (`CREATE TABLE/INDEX/TRIGGER/VIRTUAL TABLE IF NOT EXISTS`), so re-applying
    it on an already-provisioned store is a no-op for pre-existing objects and
    materializes any objects added since that store was created (e.g. the
    v2.7.0 GraphRAG community layer). Idempotent."""
    conn = get_connection(index_db_path)
    try:
        conn.executescript((DB_DIR / "index.sql").read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


_INTERNAL_AGENT_IDS: tuple[str, ...] = tuple(sorted(a["agent_id"] for a in INTERNAL_AGENTS))


def _missing_internal_agent_ids(agents_db_path: str) -> list[str]:
    """Return the subset of the 5 internal agent IDs that are absent from
    `agents_db_path`. Empty list = all present."""
    return [aid for aid in _INTERNAL_AGENT_IDS if agents.get_agent(agents_db_path, aid) is None]


def _verify_internal_agents_present(agents_db_path: str) -> None:
    """Hard post-condition for install.run(): all 5 internal Memex agents
    MUST be registered in agents.db. Surfaced as `InternalAgentsMissingError`
    with the specific missing IDs so the operator can diagnose without
    spelunking the DB."""
    missing = _missing_internal_agent_ids(agents_db_path)
    if missing:
        raise InternalAgentsMissingError(
            f"install.run() finished but {len(missing)} internal Memex agent(s) "
            f"are missing from {agents_db_path}: {missing}. "
            f"This indicates the seed step did not run to completion or the DB "
            f"was rebuilt by another process after seeding. Re-run "
            f"`python -m scripts.install` to restore."
        )


def _seed_internal(agents_db_path: str) -> None:
    """Idempotent seed of internal roles + agents. Hash-pinned for drift detection (§G).

    The seed_hash short-circuit only fires when every one of the 5 internal
    agents is actually present in the DB. A stale seed_hash on a DB whose
    agent rows have been wiped (e.g. by another consumer rebuilding the
    file) MUST NOT prevent re-seeding — that was the live-machine bug.
    """
    conn = get_connection(agents_db_path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        cur = conn.execute("SELECT value FROM meta WHERE key = 'seed_hash'")
        row = cur.fetchone()
        stored_hash = row["value"] if row else None
    finally:
        conn.close()

    # Drift-safe short-circuit: only honour seed_hash when the rows it
    # claims to have written are still there. Verifying rows is the
    # authoritative invariant; seed_hash is just an optimisation.
    if stored_hash == INTERNAL_AGENTS_HASH and not _missing_internal_agent_ids(agents_db_path):
        return  # already seeded with this exact content AND rows are present.

    if stored_hash is not None and stored_hash != INTERNAL_AGENTS_HASH:
        print(
            f"Updating internal agent profiles "
            f"(bundle hash {INTERNAL_AGENTS_HASH[:8]} != stored hash {stored_hash[:8]}). "
            f"If you have manually edited any profiles, back them up before re-running install.",
            file=sys.stderr,
        )

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
            agents.update_agent(
                agents_db_path,
                entry["agent_id"],
                profile=entry["agent_profile"],
                name=entry["agent_name"],
                role_id=role_id,
            )

    conn = get_connection(agents_db_path)
    try:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('seed_hash', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (INTERNAL_AGENTS_HASH,),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    run()
    print(f"Memex installed at {memex_home()}")
