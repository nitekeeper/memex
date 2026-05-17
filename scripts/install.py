"""One-shot ~/.memex/ bootstrap. Extended in Plan 2 to seed internal agents
and create index.db."""

from __future__ import annotations

from pathlib import Path

from db.internal_agents_seed import INTERNAL_AGENTS
from scripts import agents, registry, roles
from scripts.db import get_connection, memex_home


def run() -> None:
    # Plan 4: archive v1 if present (no-op otherwise)
    from scripts import upgrade_from_v1

    upgrade_from_v1.archive_v1()

    home = memex_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "raw").mkdir(exist_ok=True)
    (home / "backups").mkdir(exist_ok=True)
    (home / "audits").mkdir(exist_ok=True)
    (home / "templates").mkdir(exist_ok=True)

    # agents.db (Plan 1 functionality, preserved)
    agents_db_path = home / "agents.db"
    if not agents_db_path.exists():
        agents_sql = Path("db/agents.sql").read_text(encoding="utf-8")
        conn = get_connection(str(agents_db_path))
        conn.executescript(agents_sql)
        conn.commit()
        conn.close()
    if registry.get_store("agents") is None:
        registry.register_store("agents", str(agents_db_path), schema_version="v1")

    # Seed roles + agents (Plan 2 addition). Idempotent — checks existence.
    _seed_internal(str(agents_db_path))

    # index.db (Plan 2 addition). Bootstrapped directly here to avoid the
    # circular dependency of registering ourselves via create-store.
    index_db_path = home / "index.db"
    if not index_db_path.exists():
        conn = get_connection(str(index_db_path))
        conn.executescript(Path("db/migrations_table.sql").read_text(encoding="utf-8"))
        conn.executescript(Path("db/index.sql").read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO migrations (filename) VALUES (?)",
            ("index.sql",),
        )
        conn.commit()
        conn.close()
    else:
        _migrate_index_db_to_unique_key(str(index_db_path))
    if registry.get_store("index") is None:
        registry.register_store("index", str(index_db_path), schema_version="v1")

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


def _migrate_index_db_to_unique_key(index_db_path: str) -> None:
    """In-place migration: replace non-unique documents_key_idx with the
    UNIQUE invariant introduced in spec §6.4.

    Idempotent. On pre-existing duplicate keys, raises ValueError listing
    the offending keys — the install does not silently merge or delete.
    Operators resolve by hand (e.g. via memex:steward:reconcile), then re-run.
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
