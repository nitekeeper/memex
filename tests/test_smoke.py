"""End-to-end Memex Core smoke test.

Walks the full Plan 1 surface: install -> register role -> register agent ->
create-store -> insert -> query -> migrate -> update -> delete -> list-stores.
"""

from scripts import agents, install, registry, roles, stores
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
        "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);"
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
