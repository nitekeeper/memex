---
name: memex:core:register-agent
description: Register a new agent in the global agents.db agents table. Every Memex write requires an agent_id; this is how agents (human or LLM, internal or consumer-provided) come into existence.
---

# memex:core:register-agent

## Inputs
- `agent_id` — TEXT PK (e.g., `librarian-1`, `human-user`)
- `name` — display name
- `role_id` — FK into roles.id
- `profile` — markdown persona/system-prompt-fragment

## Invocation
`scripts/agents/__init__.py:create_agent(db_path, agent_id, name, role_id, profile)`
