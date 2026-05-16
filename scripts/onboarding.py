"""Human-user onboarding for Memex Brain.

First Brain invocation triggers needs_onboarding() check. If true,
the caller (Brain skill wrapper) prompts the user for id/name/role and
calls register_human(). After successful registration, future Brain calls
skip onboarding.
"""
from __future__ import annotations
from scripts import roles, agents
from scripts.db import memex_home

# Memex's 5 internal agents that should be filtered out when looking
# for "the human."
_INTERNAL_AGENT_IDS = {
    "librarian-1", "reference-librarian-1", "archivist-1",
    "dba-1", "data-steward-1",
}


def _agents_db() -> str:
    return str(memex_home() / "agents.db")


def needs_onboarding() -> bool:
    """True if no human (non-internal) agent is registered."""
    return get_human() is None


def get_human() -> dict | None:
    """Return the first registered non-internal agent, or None."""
    listed = agents.list_agents(_agents_db())
    for a in listed:
        if a["id"] not in _INTERNAL_AGENT_IDS:
            return a
    return None


def register_human(agent_id: str, name: str, role_name: str, profile: str = "") -> dict:
    """Register a human agent. Idempotent: existing agent_id is updated."""
    db = _agents_db()
    # Ensure role exists
    existing_roles = {r["name"]: r["id"] for r in roles.list_roles(db)}
    if role_name in existing_roles:
        role_id = existing_roles[role_name]
    else:
        new_role = roles.create_role(db, role_name, f"Human role: {role_name}")
        role_id = new_role["id"]

    if not profile:
        profile = "Human user. Registered via Memex Brain onboarding."

    if agents.get_agent(db, agent_id) is None:
        return agents.create_agent(db, agent_id, name, role_id, profile)
    else:
        return agents.update_agent(db, agent_id, name=name, role_id=role_id, profile=profile)


if __name__ == "__main__":
    import sys
    if sys.argv[1] == "needs":
        print("yes" if needs_onboarding() else "no")
    elif sys.argv[1] == "register":
        # python -m scripts.onboarding register <id> <name> <role>
        print(register_human(sys.argv[2], sys.argv[3], sys.argv[4]))
    elif sys.argv[1] == "get":
        h = get_human()
        print(h if h else "Not registered")
