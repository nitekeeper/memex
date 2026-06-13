"""agents package.

Provides:
- agents table CRUD (create/get/list/list_by_role/update/delete) — these live
  here at the package root so `from scripts import agents; agents.create_agent(...)`
  keeps working from Plan 1.
- Submodules for the 5 Memex internal agent implementations:
    scripts.agents.archivist    — content-addressable raw archive
    scripts.agents.dba          — pragma ops, integrity, vacuum, checkpoint
    scripts.agents.data_steward — orphan / drift audits + report writer
    scripts.agents.librarian    — LLM-driven indexing harness  (Plan 2 W-C)
    scripts.agents.reference_librarian — LLM-driven retrieval harness (Plan 2 W-C)
"""

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
    cur = conn.execute("SELECT * FROM agents WHERE role_id = ? ORDER BY id", (role_id,))
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
        f"UPDATE agents SET {set_clause} WHERE id = ?",  # nosec B608 - columns whitelisted via `allowed` above
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


def main() -> None:
    """CLI dispatch for `python -m scripts.agents <cmd> ...`.

    Mirrors the sibling CLIs in scripts/roles.py and scripts/registry.py.
    Invoked from scripts/agents/__main__.py (a package needs __main__.py for
    `python -m` to reach it); also runnable directly via the guard below.
    """
    import json
    import sys

    from scripts.db import memex_home

    db_path = str(memex_home() / "agents.db")
    cmd = sys.argv[1] if len(sys.argv) > 1 else None

    if cmd == "create":
        print(
            json.dumps(
                create_agent(db_path, sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]),
                indent=2,
            )
        )
    elif cmd == "get":
        result = get_agent(db_path, sys.argv[2])
        print(json.dumps(result, indent=2) if result else "Not found")
    elif cmd == "list":
        print(json.dumps(list_agents(db_path), indent=2))
    elif cmd == "delete":
        print("Deleted" if delete_agent(db_path, sys.argv[2]) else "Not found")
    elif cmd in (None, "-h", "--help", "help"):
        print(
            "usage: python -m scripts.agents <command> [args]\n"
            "commands:\n"
            "  create <id> <name> <role_id> <profile>   create an agent\n"
            "  get <id>                                  fetch an agent by id\n"
            "  list                                      list all agents\n"
            "  delete <id>                               delete an agent by id"
        )
        sys.exit(0 if cmd is not None else 1)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
