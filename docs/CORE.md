# Memex Core (Plan 1)

Memex Core is the CRUD substrate. It provisions and hosts SQLite stores
defined by consumer-supplied SQL migration files. It owns the agents and
roles tables (shared across consumers) and the store registry.

## Skill layout

Memex registers only **`memex:run`** as a Claude-Code-visible skill (to stay
under the 1% skill-description budget). All Core operations are agent-only
and live at `internal/core/<name>/SKILL.md`, reachable via the routing
table in `skills/run/SKILL.md`.

| Internal procedure | Purpose |
|---|---|
| `internal/core/create-store/SKILL.md` | Provision a new SQLite store from a migrations directory |
| `internal/core/migrate/SKILL.md` | Apply additional migrations to an existing store |
| `internal/core/query/SKILL.md` | SELECT from any registered store |
| `internal/core/insert/SKILL.md` | INSERT into a non-document table |
| `internal/core/update/SKILL.md` | UPDATE a row by id |
| `internal/core/delete/SKILL.md` | DELETE a row by id |
| `internal/core/list-stores/SKILL.md` | List every registered store |
| `internal/core/register-role/SKILL.md` | Add a role to the global `agents.db.roles` table |
| `internal/core/register-agent/SKILL.md` | Add an agent to `agents.db.agents` |
| `internal/core/get-agent/SKILL.md` | Fetch an agent's profile by id |

## What Plan 1 does NOT ship

- The 5 Memex-internal agent seeds (Librarian, Reference Librarian, Archivist, DBA, Data Steward) — that's Plan 2.
- index.db, FTS5, embeddings — Plan 2.
- Brain skills (ingest/ask/capture/lint/synthesize) — Plan 3.
- Plugin install scripts beyond `scripts/install.py:run()` — Plan 4.

## Acceptance criteria for Plan 1

1. `pytest tests/` passes with all tests green.
2. `python3 -m scripts.install` is idempotent and creates `~/.memex/` with `agents.db` and `registry.json`. Auto-invoked by `memex:run` Step 0 on first use; see `docs/specs/2026-05-17-install-hardening-design.md` §"Step 0.2".
3. The 10 internal core SKILL.md files exist at `internal/core/<name>/SKILL.md` with correct `name: memex:core:<name>` frontmatter.
4. The plugin manifest registers ONLY `memex:run`.
5. `skills/run/SKILL.md` contains routing entries for all 10 core procedures.
6. The end-to-end smoke test (`tests/test_smoke.py`) exercises the full lifecycle: install → register role → register agent → create-store → insert → query → migrate → update → delete → list-stores.

## How agents use it

```python
from scripts import install, roles, agents, stores
from scripts.db import memex_home

install.run()

agents_db = str(memex_home() / "agents.db")
role = roles.create_role(agents_db, "Engineer", "writes code")
agents.create_agent(agents_db, "eng-1", "Dr. X", role["id"], "profile...")

stores.create_store("my-project", "/abs/path/my-project.db", "/abs/path/migrations/")
stores.insert("my-project", "tasks", {"title": "do thing", "status": "open"})
rows = stores.query("my-project", "SELECT * FROM tasks WHERE status = ?", ("open",))
```

## Skill-description budget rationale

Claude Code loads every registered skill's `description:` frontmatter into
the agent's available-skills system reminder. Per Anthropic's guidance the
combined size of all skill descriptions should stay under roughly 1% of the
context window. With ~24 skills planned across Plans 1–3, naive top-level
registration would consume significant budget AND get truncated.

Memex's solution: register ONE skill (`memex:run`) whose description is
about the routing service itself, and let the body — read on demand — hold
the full routing table to internal procedures. Agents read the procedure
they need, when they need it, without paying for descriptions of operations
they aren't currently running.
