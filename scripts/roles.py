"""roles table CRUD. Pattern mirrors Atelier's scripts/roles.py."""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_role(db_path: str, name: str, description: str) -> dict:
    conn = get_connection(db_path)
    now = _now()
    cur = conn.execute(
        "INSERT INTO roles (name, description, created_at, updated_at) VALUES (?, ?, ?, ?)",
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
        f"UPDATE roles SET {set_clause} WHERE id = ?",  # nosec B608 - columns whitelisted via `allowed` above
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
    import json
    import sys

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
