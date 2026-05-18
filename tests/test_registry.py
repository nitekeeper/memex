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


# v2.5.1: __dunder__ keys in registry.json are reserved for config blobs
# (e.g. embeddings writes __embedding_model__). The registry API must treat
# them as not-stores so downstream consumers (e.g. Atelier's backend_memex)
# don't have to filter them client-side.


def test_list_stores_excludes_dunder_config_keys(tmp_memex_home):
    """list_stores() must filter out __key__ entries written by other subsystems
    (embeddings.__embedding_model__, etc.)."""
    registry.register_store("alpha", "/abs/alpha.db", "v1")
    # Simulate the embeddings layer writing config to registry.json directly.
    data = registry._load()
    data["__embedding_model__"] = {"provider": "openai", "model": "text-embedding-3-small"}
    registry._save(data)

    listed = registry.list_stores()
    names = [s.get("name") for s in listed]
    assert names == ["alpha"], f"expected only [alpha], got {names}"


def test_get_store_rejects_dunder_key(tmp_memex_home):
    """get_store('__embedding_model__') must return None, not the config dict."""
    data = registry._load()
    data["__embedding_model__"] = {"provider": "openai"}
    registry._save(data)

    assert registry.get_store("__embedding_model__") is None


def test_register_store_rejects_dunder_name(tmp_memex_home):
    """Reserve the __dunder__ namespace so callers can't collide with config blobs."""
    with pytest.raises(ValueError, match="reserved"):
        registry.register_store("__embedding_model__", "/abs/x.db", "v1")


def test_unregister_store_refuses_dunder_key(tmp_memex_home):
    """unregister_store on a config blob must no-op (return False), not delete it."""
    data = registry._load()
    data["__embedding_model__"] = {"provider": "openai"}
    registry._save(data)

    assert registry.unregister_store("__embedding_model__") is False
    # Config blob is still there.
    assert registry._load().get("__embedding_model__") == {"provider": "openai"}
