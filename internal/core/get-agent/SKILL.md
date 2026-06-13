---
name: memex:core:get-agent
description: Fetch an agent's full profile (including markdown profile body) by agent_id. Used by the Librarian, Reference Librarian, and other Memex internal agents to read created_by profiles for context-aware decision-making.
---

# memex:core:get-agent

## Inputs
- `agent_id` — TEXT PK

## Invocation
`scripts/agents/__init__.py:get_agent(db_path, agent_id)`
