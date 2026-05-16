from db.internal_agents_seed import INTERNAL_AGENTS


def test_seed_has_five_entries():
    assert len(INTERNAL_AGENTS) == 5


def test_seed_role_names_match_spec():
    names = {e["role_name"] for e in INTERNAL_AGENTS}
    assert names == {
        "Librarian",
        "Reference Librarian",
        "Archivist",
        "Database Administrator",
        "Data Steward",
    }


def test_seed_agent_ids_match_spec():
    ids = {e["agent_id"] for e in INTERNAL_AGENTS}
    assert ids == {
        "librarian-1",
        "reference-librarian-1",
        "archivist-1",
        "dba-1",
        "data-steward-1",
    }


def test_each_entry_has_complete_fields():
    required = {"role_name", "role_desc", "agent_id", "agent_name", "agent_profile"}
    for e in INTERNAL_AGENTS:
        assert set(e.keys()) >= required, f"Missing fields in {e.get('agent_id')}"
        for k in required:
            assert isinstance(e[k], str) and e[k].strip(), f"Empty {k} in {e.get('agent_id')}"


def test_profiles_are_substantial():
    """Each profile is a multi-paragraph operational spec (not a one-liner)."""
    for e in INTERNAL_AGENTS:
        assert len(e["agent_profile"]) > 800, f"{e['agent_id']} profile too short"
