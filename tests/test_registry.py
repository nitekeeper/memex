import json

import pytest

from scripts import registry


def test_register_store(tmp_memex_home):
    registry.register_store("alpha", "/abs/path/alpha.db", schema_version="v1")
    listed = registry.list_stores()
    assert any(s["name"] == "alpha" for s in listed)


def test_get_store_returns_dict(tmp_memex_home):
    registry.register_store("alpha", "/abs/path/alpha.db", schema_version="v1")
    s = registry.get_store("alpha")
    assert s["name"] == "alpha"
    assert s["path"] == "/abs/path/alpha.db"
    assert s["schema_version"] == "v1"


def test_get_store_returns_none_when_missing(tmp_memex_home):
    assert registry.get_store("nope") is None


def test_register_duplicate_raises(tmp_memex_home):
    registry.register_store("alpha", "/p1", "v1")
    with pytest.raises(ValueError):
        registry.register_store("alpha", "/p2", "v1")


def test_unregister_store(tmp_memex_home):
    registry.register_store("alpha", "/p1", "v1")
    assert registry.unregister_store("alpha") is True
    assert registry.get_store("alpha") is None


def test_registry_persists_as_json(tmp_memex_home):
    registry.register_store("alpha", "/p", "v1")
    raw = (tmp_memex_home / "registry.json").read_text()
    data = json.loads(raw)
    assert "alpha" in data
