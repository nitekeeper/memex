import pytest
from unittest.mock import patch
from scripts import install, onboarding, agents, roles
from scripts.db import memex_home


def test_needs_onboarding_when_no_human_agent(tmp_memex_home):
    install.run()
    assert onboarding.needs_onboarding() is True


def test_needs_onboarding_false_after_registration(tmp_memex_home):
    install.run()
    agents_db = str(memex_home() / "agents.db")
    role = roles.create_role(agents_db, "User", "Human user")
    agents.create_agent(agents_db, "human-test", "Test User", role["id"], "test profile")
    assert onboarding.needs_onboarding() is False


def test_register_human_creates_role_if_missing(tmp_memex_home):
    install.run()
    onboarding.register_human(agent_id="human-user", name="user", role_name="User")
    agents_db = str(memex_home() / "agents.db")
    r = agents.get_agent(agents_db, "human-user")
    assert r is not None
    assert r["name"] == "user"


def test_register_human_reuses_existing_role(tmp_memex_home):
    install.run()
    agents_db = str(memex_home() / "agents.db")
    existing = roles.create_role(agents_db, "Researcher", "researcher role")
    onboarding.register_human(agent_id="human-user", name="user", role_name="Researcher")
    r = agents.get_agent(agents_db, "human-user")
    assert r["role_id"] == existing["id"]


def test_register_human_idempotent(tmp_memex_home):
    install.run()
    onboarding.register_human(agent_id="human-x", name="X", role_name="User")
    # Second call should not raise
    onboarding.register_human(agent_id="human-x", name="X (updated)", role_name="User")
    agents_db = str(memex_home() / "agents.db")
    r = agents.get_agent(agents_db, "human-x")
    assert r["name"] == "X (updated)"


def test_get_human_returns_registered_agent(tmp_memex_home):
    install.run()
    onboarding.register_human(agent_id="human-user", name="user", role_name="User")
    h = onboarding.get_human()
    assert h["id"] == "human-user"


def test_get_human_returns_none_when_not_registered(tmp_memex_home):
    install.run()
    assert onboarding.get_human() is None
