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
    if not agents_db_path.exists():
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
