"""Every scripts.* module must import cleanly without MEMEX_HOME.

v2.5.0 §A guarantee: require_bootstrap() is call-time, not import-time.
This lets the preflight Step 0 (skills/run/SKILL.md) import scripts.install
to inspect it and dispatch install.run() without first needing ~/.memex/
to exist. Any module that calls memex_home()/require_bootstrap() at
import time will fail this test and must be fixed.
"""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULES = [
    "scripts.brain",
    "scripts.stores",
    "scripts.roles",
    "scripts.embeddings",
    "scripts.agents",
    "scripts.agents.archivist",
    "scripts.agents.dba",
    "scripts.agents.data_steward",
    "scripts.agents.librarian",
    "scripts.agents.reference_librarian",
    "scripts.install",
    "scripts.upgrade_from_v1",
    "scripts.registry",
    "scripts.db",
    "scripts.paths",
    "scripts._internal_agents_seed",
]


def test_modules_import_clean(monkeypatch, tmp_path):
    """All scripts.* modules import successfully with no MEMEX_HOME present.

    We also point Path.home() at a non-existent directory so that the
    default $MEMEX_HOME branch (~/.memex/) cannot resolve — proving the
    modules never touch the filesystem at import time.
    """
    monkeypatch.delenv("MEMEX_HOME", raising=False)
    monkeypatch.delenv("MEMEX_HOME_ALLOW_UNUSUAL", raising=False)
    fake_home = tmp_path / "no-home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    failures = []
    for mod in _MODULES:
        try:
            m = importlib.import_module(mod)
            importlib.reload(m)
        except Exception as e:
            failures.append(f"{mod}: {type(e).__name__}: {e}")

    assert not failures, "Modules failing clean import:\n  " + "\n  ".join(failures)
