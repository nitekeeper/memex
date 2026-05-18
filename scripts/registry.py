"""Store registry: maps store names → absolute paths + schema version.

Backed by ~/.memex/registry.json. Single-process write semantics
(short JSON read-modify-write; no inter-process locking in v2.0).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.db import memex_home

# Keys in registry.json that match this shape are reserved for config blobs
# written by other subsystems (e.g. embeddings.__embedding_model__) and must
# not be confused with store rows by the registry API.
_RESERVED_PREFIX = "__"


def _is_reserved(name: str) -> bool:
    return name.startswith(_RESERVED_PREFIX)


def _registry_path() -> Path:
    return memex_home() / "registry.json"


def _load() -> dict:
    p = _registry_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _save(data: dict) -> None:
    p = _registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def register_store(name: str, path: str, schema_version: str) -> dict:
    """Add a store to the registry. Raises ValueError if name exists or is reserved."""
    if _is_reserved(name):
        raise ValueError(
            f"Store name {name!r} is reserved (the __dunder__ namespace is for "
            f"internal config blobs, e.g. __embedding_model__)"
        )
    data = _load()
    if name in data:
        raise ValueError(f"Store already registered: {name}")
    record = {
        "name": name,
        "path": path,
        "schema_version": schema_version,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    data[name] = record
    _save(data)
    return record


def get_store(name: str) -> dict | None:
    if _is_reserved(name):
        return None
    return _load().get(name)


def list_stores() -> list[dict]:
    return [v for k, v in _load().items() if not _is_reserved(k)]


def unregister_store(name: str) -> bool:
    if _is_reserved(name):
        return False
    data = _load()
    if name not in data:
        return False
    del data[name]
    _save(data)
    return True


def update_schema_version(name: str, new_version: str) -> dict | None:
    if _is_reserved(name):
        return None
    data = _load()
    if name not in data:
        return None
    data[name]["schema_version"] = new_version
    _save(data)
    return data[name]


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1]

    if cmd == "register":
        print(json.dumps(register_store(sys.argv[2], sys.argv[3], sys.argv[4]), indent=2))
    elif cmd == "get":
        result = get_store(sys.argv[2])
        print(json.dumps(result, indent=2) if result else "Not found")
    elif cmd == "list":
        print(json.dumps(list_stores(), indent=2))
    elif cmd == "unregister":
        print("Removed" if unregister_store(sys.argv[2]) else "Not found")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
