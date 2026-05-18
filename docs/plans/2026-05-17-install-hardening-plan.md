# Install Hardening Implementation Plan (v2.5.0) — Cycle 3

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Steps use `- [ ]` checkbox syntax.

**Goal:** Ship v2.5.0 per `docs/specs/2026-05-17-install-hardening-design.md` (cycle-3 revised). All 9 user decisions and reviewer mechanical fixes incorporated.

**Architecture:** SKILL `skills/run/SKILL.md` Step 0 preflight (python3 check + Memex initialization check + Python-deterministic y/n consent gate via stdin). `scripts/paths.py` is the plugin-anchored path source. `~/.memex/config.json` is the persistent plugin-root cache (single source of truth after first invocation). `scripts/db.py` provides `MemexNotInitializedError`, `MemexHomeInvalidError`, `require_bootstrap()`. Four pre-existing security fixes ship together.

**Tech Stack:** Python 3.10+ stdlib (`pathlib`, `subprocess`, `sqlite3`, `fcntl`/`msvcrt`, `shutil`, `hashlib`, `json`, `os` with `O_NOFOLLOW`), pytest, ruff, bandit.

**Spec:** `docs/specs/2026-05-17-install-hardening-design.md`.

---

## Wave Overview

| Wave | Description | Tasks |
|---|---|---|
| **Wave 1** | Foundation (parallel) | T1, T2, T3, T4 |
| **Wave 2** | `scripts/db.py` exceptions + validation + test migration script | T5, T6 |
| **Wave 3** | Per-module Python updates (parallel) | T7–T14 |
| **Wave 4** | New test files (parallel) | T15–T22 |
| **Wave 5** | SKILL Step 0 | T23 |
| **Wave 6** | Documentation normalization (parallel) | T24–T30 |
| **Wave 7** | CHANGELOG + bump | T31, T32 |
| **Wave 8** | CI gate + PR | T33 |

Dependencies: 2→1, 3→1+2, 4→1+2+3, 5→1–4, 6→5, 7→6, 8→7.

---

# Wave 1 — Foundation (parallel)

## Task 1: `scripts/paths.py` + `tests/test_paths.py`

- [ ] **Step 1: Create `scripts/paths.py`**

```python
"""Plugin-anchored filesystem constants.

Resource files (SQL migrations, prompt templates) live inside the
installed plugin bundle and must be resolved relative to this file,
not CWD. Stable API: PLUGIN_ROOT, DB_DIR, PROMPTS_DIR.
"""

from __future__ import annotations

from pathlib import Path

# scripts/paths.py → scripts/ → <plugin_root>
PLUGIN_ROOT: Path = Path(__file__).resolve().parent.parent

DB_DIR: Path = PLUGIN_ROOT / "db"
PROMPTS_DIR: Path = PLUGIN_ROOT / "prompts"

if not (DB_DIR / "migrations_table.sql").is_file():
    raise ImportError(
        f"Memex bundle layout broken: {DB_DIR}/migrations_table.sql not found. "
        f"PLUGIN_ROOT resolved to {PLUGIN_ROOT}. See docs/PACKAGING.md."
    )
```

- [ ] **Step 2: Create `tests/test_paths.py`**

```python
"""Plugin-anchored path constants resolve regardless of CWD."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest


def test_imports_succeed():
    from scripts.paths import DB_DIR, PLUGIN_ROOT, PROMPTS_DIR
    assert PLUGIN_ROOT.is_absolute()
    assert DB_DIR.is_dir()
    assert PROMPTS_DIR.is_dir()


def test_plugin_root_contains_expected_dirs():
    from scripts.paths import PLUGIN_ROOT
    assert (PLUGIN_ROOT / "scripts").is_dir()
    assert (PLUGIN_ROOT / "db").is_dir()
    assert (PLUGIN_ROOT / "prompts").is_dir()


def test_db_dir_contains_sql_files():
    from scripts.paths import DB_DIR
    for fname in ("agents.sql", "index.sql", "brain.sql", "migrations_table.sql"):
        assert (DB_DIR / fname).is_file(), f"missing {fname}"


def test_prompts_dir_contains_md_files():
    from scripts.paths import PROMPTS_DIR
    for fname in ("librarian.md", "reference_librarian.md", "synthesizer.md"):
        assert (PROMPTS_DIR / fname).is_file(), f"missing {fname}"


def test_paths_cwd_independent(tmp_path):
    """Subprocess from foreign CWD resolves to the same PLUGIN_ROOT."""
    from scripts.paths import PLUGIN_ROOT as EXPECTED
    import os
    result = subprocess.check_output(
        [sys.executable, "-c", "from scripts.paths import PLUGIN_ROOT; print(PLUGIN_ROOT)"],
        cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": str(EXPECTED)},
    ).decode().strip()
    assert Path(result) == EXPECTED


def _ast_has_relative_path_literal(src: str, prefix: str) -> bool:
    """True if source has any Call(...string-starts-with(prefix)) — robust to comments/quotes/f-strings."""
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value.startswith(prefix):
                    return True
    return False
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/test_paths.py -v
git add scripts/paths.py tests/test_paths.py
git commit -m "scripts: add plugin-anchored path constants (paths.py)"
```

---

## Task 2: Relocate `db/internal_agents_seed.py` → `scripts/_internal_agents_seed.py`

- [ ] **Step 1: Read current content**

```bash
cat db/internal_agents_seed.py
```

- [ ] **Step 2: Create `scripts/_internal_agents_seed.py`**

Copy verbatim from `db/internal_agents_seed.py`. Append at bottom:

```python
import hashlib as _hashlib
import json as _json

# Sort entries by agent_id BEFORE hashing — order-insensitive across refactors.
_SORTED = sorted(INTERNAL_AGENTS, key=lambda a: a["agent_id"])
INTERNAL_AGENTS_HASH: str = _hashlib.sha256(
    _json.dumps(_SORTED, sort_keys=True, ensure_ascii=False).encode("utf-8")
).hexdigest()
del _SORTED  # don't expose internal sort artifact
```

- [ ] **Step 3: Delete old file**

```bash
git rm db/internal_agents_seed.py
```

- [ ] **Step 4: Verify no stale references**

```bash
grep -rn "from db.internal_agents_seed\|from db import internal_agents_seed" scripts tests
```

Should show `scripts/install.py:8` (will be updated in T7) and `tests/test_internal_agents_seed.py` (will be updated in T6 audit).

- [ ] **Step 5: Commit**

```bash
git add scripts/_internal_agents_seed.py db/internal_agents_seed.py
git commit -m "scripts: relocate internal_agents_seed from db/ + add INTERNAL_AGENTS_HASH"
```

---

## Task 3: `.gitattributes`

- [ ] **Step 1: Create file at repo root**

```
* text=auto eol=lf
*.md   text eol=lf
*.py   text eol=lf
*.sql  text eol=lf
*.json text eol=lf
*.toml text eol=lf
*.yml  text eol=lf
*.yaml text eol=lf
*.sh   text eol=lf
*.db   binary
*.sqlite binary
*.png  binary
*.ico  binary
*.zip  binary
```

- [ ] **Step 2: Stash any unrelated changes, then renormalize**

```bash
git stash push -m "pre-renormalize stash" || true
git add .gitattributes
git add --renormalize .
git status
```

- [ ] **Step 3: Commit + pop stash**

```bash
git commit -m "git: enforce LF line endings + binary declarations via .gitattributes"
git stash pop || true
```

---

## Task 4: Update `tests/conftest.py` with new fixtures

- [ ] **Step 1: Read current state**

```bash
cat tests/conftest.py
```

- [ ] **Step 2: Replace `tmp_memex_home` fixture and append new fixtures**

```python
import pytest

from scripts.db import get_connection


@pytest.fixture
def tmp_memex_home(monkeypatch, tmp_path):
    """Isolated ~/.memex/ root for tests.

    Sets MEMEX_HOME_ALLOW_UNUSUAL=1 because tmp_path is under /tmp,
    which fails the v2.5.0 $MEMEX_HOME validation.
    """
    home = tmp_path / "memex_home"
    home.mkdir()
    monkeypatch.setenv("MEMEX_HOME", str(home))
    monkeypatch.setenv("MEMEX_HOME_ALLOW_UNUSUAL", "1")
    return home


@pytest.fixture
def bootstrapped_marker(tmp_memex_home):
    """Lightweight: write registry.json so require_bootstrap() passes."""
    (tmp_memex_home / "registry.json").write_text("{}")
    return tmp_memex_home


@pytest.fixture
def bootstrapped_home(tmp_memex_home):
    """Full install. Use for tests that need real seeded data."""
    from scripts import install
    install.run()
    return tmp_memex_home


@pytest.fixture
def tmp_store_path(tmp_path):
    """Disposable SQLite store path."""
    return tmp_path / "store.db"


@pytest.fixture
def conn(tmp_store_path):
    """Opened SQLite connection with Memex pragmas."""
    c = get_connection(tmp_store_path)
    try:
        yield c
    finally:
        c.close()
```

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "tests: tmp_memex_home sets ALLOW_UNUSUAL=1; add bootstrapped fixtures"
```

---

# Wave 2 — Exceptions/validation + test migration

## Task 5: `scripts/db.py` — exceptions, validated `memex_home()`, `require_bootstrap()`, `config.json` helpers

- [ ] **Step 1: Write `tests/test_bootstrap_guard.py`**

```python
"""require_bootstrap() + memex_home() validation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.db import (
    MemexHomeInvalidError,
    MemexNotInitializedError,
    memex_home,
    require_bootstrap,
)


def test_require_bootstrap_raises_when_missing(tmp_memex_home):
    with pytest.raises(MemexNotInitializedError) as exc_info:
        require_bootstrap()
    msg = str(exc_info.value)
    assert "not bootstrapped" in msg.lower()
    assert str(tmp_memex_home) in msg


def test_require_bootstrap_passes_when_present(bootstrapped_marker):
    require_bootstrap()


def test_error_subclasses():
    assert issubclass(MemexNotInitializedError, RuntimeError)
    assert issubclass(MemexHomeInvalidError, ValueError)


def test_error_message_resolves_plugin_root(tmp_memex_home):
    from scripts.paths import PLUGIN_ROOT
    with pytest.raises(MemexNotInitializedError) as exc_info:
        require_bootstrap()
    msg = str(exc_info.value)
    assert "<plugin_root>" not in msg
    assert str(PLUGIN_ROOT) in msg


def test_memex_home_default(monkeypatch):
    monkeypatch.delenv("MEMEX_HOME", raising=False)
    monkeypatch.delenv("MEMEX_HOME_ALLOW_UNUSUAL", raising=False)
    assert memex_home() == Path.home() / ".memex"


def test_memex_home_rejects_outside_home(monkeypatch):
    monkeypatch.setenv("MEMEX_HOME", "/etc/memex")
    monkeypatch.delenv("MEMEX_HOME_ALLOW_UNUSUAL", raising=False)
    with pytest.raises(MemexHomeInvalidError):
        memex_home()


def test_memex_home_rejects_root(monkeypatch):
    monkeypatch.setenv("MEMEX_HOME", "/")
    monkeypatch.delenv("MEMEX_HOME_ALLOW_UNUSUAL", raising=False)
    with pytest.raises(MemexHomeInvalidError):
        memex_home()


def test_memex_home_rejects_symlinked_explicit(monkeypatch, tmp_path):
    """$MEMEX_HOME set to a symlink → reject."""
    real = tmp_path / "real_home"
    real.mkdir()
    link = tmp_path / "link_home"
    link.symlink_to(real)
    monkeypatch.setenv("MEMEX_HOME", str(link))
    monkeypatch.delenv("MEMEX_HOME_ALLOW_UNUSUAL", raising=False)
    # link is also outside $HOME, but check error mentions symlink first
    with pytest.raises(MemexHomeInvalidError, match="(symlink|not under)"):
        memex_home()


def test_memex_home_rejects_symlinked_default(monkeypatch, tmp_path):
    """~/.memex/ existing as a symlink → reject in default branch."""
    monkeypatch.delenv("MEMEX_HOME", raising=False)
    monkeypatch.delenv("MEMEX_HOME_ALLOW_UNUSUAL", raising=False)
    # Patch Path.home() to tmp_path, then pre-stage .memex as a symlink.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path) if False else (lambda: tmp_path))
    real = tmp_path / "elsewhere"
    real.mkdir()
    link = tmp_path / ".memex"
    link.symlink_to(real)
    with pytest.raises(MemexHomeInvalidError, match="symlink"):
        memex_home()


def test_memex_home_allow_unusual(monkeypatch):
    monkeypatch.setenv("MEMEX_HOME", "/tmp/memex-allow-unusual-test")
    monkeypatch.setenv("MEMEX_HOME_ALLOW_UNUSUAL", "1")
    assert memex_home() == Path("/tmp/memex-allow-unusual-test").resolve()


def test_install_does_not_require_bootstrap(tmp_memex_home):
    """install.run() is the bootstrap; does NOT call require_bootstrap()."""
    from scripts import install
    install.run()
    assert (tmp_memex_home / "registry.json").exists()


def test_registry_does_not_require_bootstrap(tmp_memex_home):
    from scripts import registry
    assert registry.get_store("any") is None
    assert registry.list_stores() == []


def test_registry_does_not_call_require_bootstrap_via_mock_bomb(
    tmp_memex_home, monkeypatch
):
    bomb = Mock(side_effect=AssertionError("require_bootstrap leaked into registry"))
    monkeypatch.setattr("scripts.db.require_bootstrap", bomb)
    from scripts import registry
    registry.get_store("x")
    registry.list_stores()
    bomb.assert_not_called()


def test_roles_does_not_require_bootstrap(tmp_memex_home, tmp_path):
    """roles.* takes explicit db_path; bootstrap-state-independent."""
    from scripts import roles
    db = str(tmp_path / "isolated.db")
    # Create the DB schema first (roles needs the roles table)
    from scripts.db import get_connection
    from scripts.paths import DB_DIR
    conn = get_connection(db)
    conn.executescript((DB_DIR / "agents.sql").read_text())
    conn.commit()
    conn.close()
    # Now roles operations should work without MEMEX_HOME being bootstrapped
    roles.create_role(db, "test", "desc")  # must not raise


def test_dba_does_not_require_bootstrap(tmp_memex_home, tmp_path, monkeypatch):
    """dba.* takes explicit db_path; bootstrap-state-independent."""
    from scripts.agents import dba
    db = str(tmp_path / "any.db")
    from scripts.db import get_connection
    conn = get_connection(db)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()
    bomb = Mock(side_effect=AssertionError("require_bootstrap leaked into dba"))
    monkeypatch.setattr("scripts.db.require_bootstrap", bomb)
    dba.integrity_check(db)  # must not raise
    bomb.assert_not_called()
```

- [ ] **Step 2: Verify failure (no exceptions exist yet)**

```bash
pytest tests/test_bootstrap_guard.py -v 2>&1 | head -20
```

- [ ] **Step 3: Update `scripts/db.py`**

Add imports near top:

```python
import json
```

Replace the existing `memex_home()` function:

```python
def memex_home() -> Path:
    """Resolve Memex home directory, with validation in both branches.

    Order:
      - $MEMEX_HOME if set → validated (no symlink, under $HOME unless ALLOW_UNUSUAL=1)
      - else Path.home() / .memex → validated (no symlink unless ALLOW_UNUSUAL=1)

    Raises MemexHomeInvalidError on invalid input.
    """
    allow_unusual = os.environ.get("MEMEX_HOME_ALLOW_UNUSUAL") == "1"
    explicit = os.environ.get("MEMEX_HOME")

    if explicit:
        candidate = Path(explicit).expanduser()
        # Check is_symlink BEFORE resolve (resolve collapses symlinks).
        if not allow_unusual and candidate.exists() and candidate.is_symlink():
            raise MemexHomeInvalidError(
                f"$MEMEX_HOME ({candidate}) is a symlink; refusing to write through it. "
                f"Set MEMEX_HOME_ALLOW_UNUSUAL=1 to override."
            )
        resolved = candidate.resolve()
        if not allow_unusual:
            try:
                resolved.relative_to(Path.home().resolve())
            except ValueError:
                raise MemexHomeInvalidError(
                    f"$MEMEX_HOME ({resolved}) is not under your home directory "
                    f"({Path.home().resolve()}). Set MEMEX_HOME_ALLOW_UNUSUAL=1 to override."
                )
        return resolved

    # Default branch.
    home = Path.home() / MEMEX_DIR_NAME
    if not allow_unusual and home.exists() and home.is_symlink():
        raise MemexHomeInvalidError(
            f"{home} is a symlink; refusing to write through it. "
            f"Set MEMEX_HOME_ALLOW_UNUSUAL=1 to override."
        )
    return home
```

Append at end:

```python


class MemexHomeInvalidError(ValueError):
    """$MEMEX_HOME or default ~/.memex/ failed validation."""


class MemexNotInitializedError(RuntimeError):
    """Memex Python invoked before ~/.memex/ is bootstrapped."""


def require_bootstrap() -> None:
    """Precondition for functions that write under memex_home()."""
    home = memex_home()
    if not (home / "registry.json").exists():
        from scripts.paths import PLUGIN_ROOT
        raise MemexNotInitializedError(
            f"Memex is not bootstrapped at {home}.\n"
            f"To bootstrap:\n"
            f"  PYTHONPATH={PLUGIN_ROOT} python3 -m scripts.install\n"
            f"Or, in Claude Code, invoke memex:run and accept the prompt."
        )


def read_plugin_root_config() -> Path | None:
    """Read plugin_root from ~/.memex/config.json. None if absent or invalid."""
    config_path = memex_home() / "config.json"
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text())
        candidate = Path(data["plugin_root"])
        if (candidate / "scripts" / "install.py").is_file():
            plugin_json = candidate / "plugin.json"
            if plugin_json.exists():
                manifest = json.loads(plugin_json.read_text())
                if manifest.get("name") == "memex":
                    return candidate
    except (json.JSONDecodeError, KeyError, OSError, ValueError):
        pass
    return None


def write_plugin_root_config(plugin_root: Path) -> None:
    """Write {plugin_root: <abs>} to ~/.memex/config.json."""
    home = memex_home()
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.json"
    config_path.write_text(json.dumps({"plugin_root": str(plugin_root)}, indent=2))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_bootstrap_guard.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/db.py tests/test_bootstrap_guard.py
git commit -m "db: MemexNotInitializedError + require_bootstrap + $MEMEX_HOME validation + config.json helpers"
```

---

## Task 6: Write + run `scripts/_migrate_v25_tests.py`

- [ ] **Step 1: Write the migration script**

Create `scripts/_migrate_v25_tests.py`:

```python
"""One-shot migration of existing test_*.py files to v2.5.0 fixtures + paths.

Scans each tests/test_*.py and rewrites:
  - tmp_memex_home arg → bootstrapped_marker (if test calls guarded fn but does NOT
    seed via install.run()) or bootstrapped_home (if seeds via install).
  - Path("db/...") / Path("prompts/...") → DB_DIR / PROMPTS_DIR
  - from db.internal_agents_seed → from scripts._internal_agents_seed

Usage:
  python3 -m scripts._migrate_v25_tests --dry-run    (print diff)
  python3 -m scripts._migrate_v25_tests --apply       (write changes)
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

GUARDED_MODULES = {
    "scripts.brain", "scripts.stores", "scripts.embeddings",
    "scripts.agents.archivist",
}

# Tests in these files use raw db_path patterns (Class C); no migration needed.
CLASS_C_FILES = {"test_roles.py", "test_agents.py", "test_agents_schema.py", "test_dba.py"}


def classify(src: str) -> str:
    """Return 'marker', 'home', or 'none'."""
    if "install.run()" in src or "scripts.install" in src:
        return "home"
    for mod in GUARDED_MODULES:
        if f"from {mod}" in src or f"import {mod}" in src:
            return "marker"
        # also catches `from scripts import brain` style:
        last_seg = mod.split(".")[-1]
        if f"from scripts import {last_seg}" in src or f"scripts.{last_seg}" in src:
            return "marker"
    return "none"


def migrate_file(path: Path) -> str:
    src = path.read_text()
    new = src

    # 1. Path("db/...") / Path("prompts/...") → DB_DIR / PROMPTS_DIR
    if 'Path("db/' in new or "Path('db/" in new:
        new = re.sub(r'Path\(["\']db/([^"\']+)["\']\)', r'(DB_DIR / "\1")', new)
        if "from scripts.paths" not in new:
            new = "from scripts.paths import DB_DIR\n" + new
    if 'Path("prompts/' in new or "Path('prompts/" in new:
        new = re.sub(r'Path\(["\']prompts/([^"\']+)["\']\)', r'(PROMPTS_DIR / "\1")', new)
        if "PROMPTS_DIR" not in new.split("\n", 1)[0]:
            new = "from scripts.paths import PROMPTS_DIR\n" + new

    # 2. from db.internal_agents_seed → from scripts._internal_agents_seed
    new = new.replace(
        "from db.internal_agents_seed import",
        "from scripts._internal_agents_seed import",
    )

    # 3. Fixture migration: tmp_memex_home → bootstrapped_marker / bootstrapped_home
    if path.name not in CLASS_C_FILES:
        cls = classify(new)
        if cls == "marker":
            new = re.sub(r"\btmp_memex_home\b", "bootstrapped_marker", new)
        elif cls == "home":
            new = re.sub(r"\btmp_memex_home\b", "bootstrapped_home", new)
        # else: leave alone

    return new


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    tests_dir = Path(__file__).resolve().parent.parent / "tests"
    diffs = []
    for f in sorted(tests_dir.glob("test_*.py")):
        old = f.read_text()
        new = migrate_file(f)
        if old != new:
            diffs.append((f, old, new))
            if args.apply:
                f.write_text(new)
                print(f"updated: {f.relative_to(tests_dir.parent)}")
            else:
                print(f"would update: {f.relative_to(tests_dir.parent)}")

    print(f"\n{len(diffs)} files migrated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Dry-run**

```bash
python3 -m scripts._migrate_v25_tests
```

Inspect output. Manually verify a few sample files.

- [ ] **Step 3: Apply migration**

```bash
python3 -m scripts._migrate_v25_tests --apply
```

- [ ] **Step 4: Run full suite (some tests may still fail because Wave 3 guards haven't landed yet)**

```bash
pytest tests/ -v 2>&1 | tail -30
```

Expect failures only in tests that exercise guarded code without the guards being installed yet. These are fine — they'll pass once Wave 3 lands.

- [ ] **Step 5: Commit**

```bash
git add tests/ scripts/_migrate_v25_tests.py
git commit -m "tests: mechanical migration to v2.5.0 fixtures + DB_DIR/PROMPTS_DIR"
```

---

# Wave 3 — Per-module Python updates (parallel)

## Task 7: `scripts/install.py` — paths + flock + hash-pin + stdin consent + relocate import

- [ ] **Step 1: Write `tests/test_security_install_lock.py`**

```python
"""Concurrent install lock via flock/msvcrt + O_NOFOLLOW."""

from __future__ import annotations

import multiprocessing
import os
import time
from pathlib import Path

import pytest


def _barrier_worker(memex_home: str, barrier, result_queue):
    os.environ["MEMEX_HOME"] = memex_home
    os.environ["MEMEX_HOME_ALLOW_UNUSUAL"] = "1"
    barrier.wait(timeout=5)
    try:
        from scripts import install
        install.run()
        result_queue.put("ok")
    except Exception as e:
        result_queue.put(type(e).__name__)


def test_install_lock_typed_error_on_concurrent(tmp_memex_home):
    """Deterministic race exercise via Barrier — exactly one process wins."""
    from scripts.install import InstallLockBusyError  # noqa: F401

    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    q = ctx.Queue()
    procs = [
        ctx.Process(target=_barrier_worker, args=(str(tmp_memex_home), barrier, q))
        for _ in range(2)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=15)

    results = sorted([q.get() for _ in range(2)])
    # Exactly one ok, one InstallLockBusyError (race is forced via Barrier).
    assert results == ["InstallLockBusyError", "ok"]
    # registry.json must be valid JSON.
    import json
    assert json.loads((tmp_memex_home / "registry.json").read_text())


def test_lock_file_rejects_symlink(tmp_memex_home):
    """If .install.lock is a symlink, O_NOFOLLOW raises before truncating target."""
    target = tmp_memex_home / "innocent.txt"
    target.write_text("important data")
    lock = tmp_memex_home / ".install.lock"
    lock.symlink_to(target)

    from scripts.install import InstallLockBusyError, _acquire_lock
    with pytest.raises(InstallLockBusyError):
        _acquire_lock(lock)

    # Target must NOT have been truncated.
    assert target.read_text() == "important data"
```

- [ ] **Step 2: Write `tests/test_security_profile_hash.py`**

```python
"""Internal agent profile hash-pinning."""

from __future__ import annotations


def test_seed_writes_hash(bootstrapped_home):
    import sqlite3
    from scripts._internal_agents_seed import INTERNAL_AGENTS_HASH
    conn = sqlite3.connect(str(bootstrapped_home / "agents.db"))
    cur = conn.execute("SELECT value FROM meta WHERE key = 'seed_hash'")
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == INTERNAL_AGENTS_HASH


def test_seed_noop_on_match(bootstrapped_home, capsys):
    from scripts import install
    capsys.readouterr()
    install.run()
    captured = capsys.readouterr()
    assert "Updating internal agent profiles" not in captured.err


def test_seed_warns_on_mismatch(bootstrapped_home, capfd):
    import sqlite3
    conn = sqlite3.connect(str(bootstrapped_home / "agents.db"))
    conn.execute("UPDATE meta SET value = 'deadbeefdeadbeefdeadbeef' WHERE key = 'seed_hash'")
    conn.commit()
    conn.close()
    capfd.readouterr()
    from scripts import install
    install.run()
    captured = capfd.readouterr()
    assert "Updating internal agent profiles" in captured.err
    assert "deadbeef" in captured.err


def test_stdin_consent_y(tmp_memex_home, monkeypatch):
    """install.run() proceeds when 'y' is on stdin."""
    import io
    import sys
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    from scripts import install
    install.run()
    assert (tmp_memex_home / "registry.json").exists()


def test_stdin_consent_n(tmp_memex_home, monkeypatch):
    """install.run() exits cleanly without bootstrapping when 'n' is on stdin."""
    import io
    import sys
    monkeypatch.setattr(sys, "stdin", io.StringIO("n\n"))
    from scripts import install
    import pytest
    with pytest.raises(SystemExit) as exc_info:
        install.run()
    assert exc_info.value.code == 1
    assert not (tmp_memex_home / "registry.json").exists()


def test_stdin_consent_empty(tmp_memex_home, monkeypatch):
    """install.run() proceeds when stdin is empty (manual invocation via terminal)."""
    import io
    import sys
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    from scripts import install
    # Empty stdin → assume consent (manual command-line invocation).
    install.run()
    assert (tmp_memex_home / "registry.json").exists()
```

- [ ] **Step 3: Rewrite `scripts/install.py`**

```python
"""One-shot ~/.memex/ bootstrap. v2.5.0: flock-protected, hash-pinned, consent-gated."""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

from scripts import agents, registry, roles
from scripts._internal_agents_seed import INTERNAL_AGENTS, INTERNAL_AGENTS_HASH
from scripts.db import get_connection, memex_home
from scripts.paths import DB_DIR


class InstallLockBusyError(RuntimeError):
    """Another scripts.install.run() is already in progress."""


def _acquire_lock(lock_path: Path):
    """Cross-platform exclusive lock with O_NOFOLLOW. Returns open file handle."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(lock_path), flags, 0o600)
    except OSError as e:
        if e.errno == getattr(errno, "ELOOP", 40):
            raise InstallLockBusyError(
                f"Lock path is a symlink: {lock_path}. Refusing to follow."
            )
        raise

    fh = os.fdopen(fd, "r+")
    if sys.platform.startswith("win") or os.name == "nt":
        import msvcrt
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as e:
            fh.close()
            if e.errno in (errno.EACCES, getattr(errno, "EDEADLK", 35)):
                raise InstallLockBusyError(
                    f"Another Memex install is already running (lock at {lock_path})."
                )
            raise
    else:
        import fcntl
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            raise InstallLockBusyError(
                f"Another Memex install is already running (lock at {lock_path})."
            )
        except OSError as e:
            fh.close()
            raise InstallLockBusyError(
                f"Lock acquisition failed at {lock_path}: {e}."
            )
    return fh


def _read_consent_from_stdin() -> bool:
    """Read y/n from stdin. Empty stdin (no SKILL invocation, manual CLI) → True."""
    try:
        line = sys.stdin.readline().strip().lower()
    except Exception:
        return True
    if not line:
        return True
    if line == "y":
        return True
    if line == "n":
        sys.exit(1)
    sys.stderr.write(
        f"Invalid consent token: {line!r}. Expected 'y' or 'n'. Aborting.\n"
    )
    sys.exit(2)


def run() -> None:
    if not _read_consent_from_stdin():
        sys.exit(1)

    home = memex_home()
    home.mkdir(parents=True, exist_ok=True)

    lock_fh = _acquire_lock(home / ".install.lock")
    try:
        from scripts import upgrade_from_v1
        upgrade_from_v1.archive_v1()

        for sub in ("raw", "backups", "audits", "templates"):
            (home / sub).mkdir(exist_ok=True)

        agents_db_path = home / "agents.db"
        if not agents_db_path.exists():
            conn = get_connection(str(agents_db_path))
            conn.executescript((DB_DIR / "agents.sql").read_text(encoding="utf-8"))
            conn.commit()
            conn.close()
        if registry.get_store("agents") is None:
            registry.register_store("agents", str(agents_db_path), schema_version="v1")

        _seed_internal(str(agents_db_path))

        index_db_path = home / "index.db"
        if not index_db_path.exists():
            conn = get_connection(str(index_db_path))
            conn.executescript((DB_DIR / "migrations_table.sql").read_text(encoding="utf-8"))
            conn.executescript((DB_DIR / "index.sql").read_text(encoding="utf-8"))
            conn.execute("INSERT INTO migrations (filename) VALUES (?)", ("index.sql",))
            conn.commit()
            conn.close()
        else:
            _migrate_index_db_to_unique_key(str(index_db_path))
        if registry.get_store("index") is None:
            registry.register_store("index", str(index_db_path), schema_version="v1")

        article_db_path = home / "article.db"
        if not article_db_path.exists():
            conn = get_connection(str(article_db_path))
            conn.executescript((DB_DIR / "migrations_table.sql").read_text())
            conn.executescript((DB_DIR / "brain.sql").read_text())
            conn.execute("INSERT INTO migrations (filename) VALUES (?)", ("brain.sql",))
            conn.commit()
            conn.close()
        if registry.get_store("article") is None:
            registry.register_store("article", str(article_db_path), schema_version="v1")
    finally:
        lock_fh.close()


def _seed_internal(agents_db_path: str) -> None:
    """Idempotent seed of internal roles + agents. Hash-pinned for drift detection."""
    conn = get_connection(agents_db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        cur = conn.execute("SELECT value FROM meta WHERE key = 'seed_hash'")
        row = cur.fetchone()
        stored_hash = row["value"] if row else None
    finally:
        conn.close()

    if stored_hash == INTERNAL_AGENTS_HASH:
        return

    if stored_hash is not None and stored_hash != INTERNAL_AGENTS_HASH:
        print(
            f"Updating internal agent profiles "
            f"(bundle hash {INTERNAL_AGENTS_HASH[:8]} != stored hash {stored_hash[:8]}). "
            f"If you have manually edited any profiles, back them up before re-running install.",
            file=sys.stderr,
        )

    existing_roles = {r["name"]: r["id"] for r in roles.list_roles(agents_db_path)}
    for entry in INTERNAL_AGENTS:
        if entry["role_name"] in existing_roles:
            role_id = existing_roles[entry["role_name"]]
        else:
            r = roles.create_role(agents_db_path, entry["role_name"], entry["role_desc"])
            role_id = r["id"]

        if agents.get_agent(agents_db_path, entry["agent_id"]) is None:
            agents.create_agent(
                agents_db_path,
                entry["agent_id"],
                entry["agent_name"],
                role_id,
                entry["agent_profile"],
            )
        else:
            agents.update_agent(
                agents_db_path,
                entry["agent_id"],
                profile=entry["agent_profile"],
                name=entry["agent_name"],
                role_id=role_id,
            )

    conn = get_connection(agents_db_path)
    try:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('seed_hash', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (INTERNAL_AGENTS_HASH,),
        )
        conn.commit()
    finally:
        conn.close()


def _migrate_index_db_to_unique_key(index_db_path: str) -> None:
    """In-place migration to UNIQUE(documents.key) per spec §6.4."""
    conn = get_connection(index_db_path)
    try:
        has_unique = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='documents_key_unique_idx'"
        ).fetchone()
        if has_unique:
            return
        dupes = [
            (r["key"], r["n"])
            for r in conn.execute(
                "SELECT key, COUNT(*) AS n FROM documents "
                "WHERE key IS NOT NULL GROUP BY key HAVING n > 1"
            )
        ]
        if dupes:
            preview = ", ".join(f"{k!r} x{n}" for k, n in dupes[:5])
            more = f" (+{len(dupes) - 5} more)" if len(dupes) > 5 else ""
            raise ValueError(
                f"Cannot apply UNIQUE(documents.key): {len(dupes)} duplicate key(s) "
                f"already present: {preview}{more}."
            )
        conn.execute("DROP INDEX IF EXISTS documents_key_idx")
        conn.execute("CREATE UNIQUE INDEX documents_key_unique_idx ON documents(key)")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    run()
    print(f"Memex installed at {memex_home()}")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_install.py tests/test_security_install_lock.py tests/test_security_profile_hash.py tests/test_bootstrap_guard.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/install.py tests/test_security_install_lock.py tests/test_security_profile_hash.py
git commit -m "install: paths via DB_DIR + O_NOFOLLOW flock + hash-pinned seed + stdin consent + relocate import"
```

---

## Task 8: `scripts/stores.py`

Add imports:
```python
from scripts.db import get_connection, require_bootstrap, safe_identifier
from scripts.paths import DB_DIR
```

Replace `_migrations_table_sql()`:
```python
def _migrations_table_sql() -> str:
    return (DB_DIR / "migrations_table.sql").read_text()
```

Add `require_bootstrap()` as first line of: `create_store`, `migrate`, `query`, `insert`, `update`, `delete`.

Remove unused `from pathlib import Path` if applicable. Run `ruff check --fix`.

Commit: `stores: anchor migrations SQL + bootstrap guards`

---

## Task 9: `scripts/brain.py`

Update imports:
```python
from scripts.db import memex_home, require_bootstrap
from scripts.paths import PROMPTS_DIR
```

Replace line 289:
```python
    template = (PROMPTS_DIR / "synthesizer.md").read_text(encoding="utf-8")
```

Add `require_bootstrap()` as first line of: `ingest_prepare`, `ingest_complete`, `capture_prepare`, `capture_complete`, `ask_prepare`, `ask_execute`, `lint`, `synthesize_prepare`, `synthesize_complete`.

Commit: `brain: anchor prompts + bootstrap guards`

---

## Task 10: `scripts/embeddings.py`

Add import:
```python
from scripts.db import require_bootstrap
```

Identify public entries (`grep -nE "^def [a-z]" scripts/embeddings.py`) and add `require_bootstrap()` to each.

Commit: `embeddings: bootstrap guards on public encode entries`

---

## Task 11: `scripts/agents/librarian.py`

Add import:
```python
from scripts.paths import PROMPTS_DIR
```

Replace line 73:
```python
    return (PROMPTS_DIR / "librarian.md").read_text(encoding="utf-8")
```

Commit: `librarian: anchor prompt to PROMPTS_DIR`

---

## Task 12: `scripts/agents/reference_librarian.py`

Add import + replace line 71 analogously to T11.

Commit: `reference_librarian: anchor prompt to PROMPTS_DIR`

---

## Task 13: `scripts/agents/archivist.py` — guard `archive()` only

Verify the actual function signature first:
```bash
grep -nE "^def [a-z]" scripts/agents/archivist.py
```

Real signature is `def archive(payload, filename)` — guard it. Other public entries (if any) that write under `memex_home() / "raw"` also get the guard.

Test:
```python
def test_archivist_archive_requires_bootstrap(tmp_memex_home):
    from scripts.agents import archivist
    with pytest.raises(MemexNotInitializedError):
        archivist.archive(b"x", "x.txt")
```

Commit: `archivist: bootstrap guard on archive()`

---

## Task 14: `scripts/upgrade_from_v1.py` — symlink protection

- [ ] **Step 1: Write `tests/test_security_v1_symlink.py`** (similar to prior version, with `is_symlink` checked BEFORE `.resolve()`)

- [ ] **Step 2: Update `detect_v1_install()`**

```python
def detect_v1_install() -> Path | None:
    explicit = os.environ.get("MEMEX_V1_PATH")
    if not explicit:
        return None
    candidate = Path(explicit).expanduser()
    # is_symlink check BEFORE resolve
    if candidate.is_symlink():
        raise ValueError(f"$MEMEX_V1_PATH is a symlink ({candidate}); refusing to archive.")
    v1_root = candidate.resolve()
    try:
        v1_root.relative_to(Path.home().resolve())
    except ValueError:
        return None
    ai = v1_root / ".ai"
    if not ai.exists():
        return None
    if ai.is_symlink():
        raise ValueError(f"{ai} is a symlink; refusing to archive.")
    return v1_root
```

- [ ] **Step 3: Update `archive_v1()`**

```python
def archive_v1() -> None:
    v1_dir = detect_v1_install()
    if v1_dir is None:
        return

    from scripts.db import memex_home
    home = memex_home()
    legacy_root = home / "legacy" / "v1-wiki"
    if legacy_root.exists():
        return
    legacy_parent = legacy_root.parent
    if legacy_parent.exists() and legacy_parent.is_symlink():
        raise ValueError(f"{legacy_parent} is a symlink; refusing to archive.")
    legacy_parent.mkdir(parents=True, exist_ok=True)

    import shutil
    shutil.copytree(
        v1_dir / ".ai",
        legacy_root,
        symlinks=True,
        ignore_dangling_symlinks=True,
    )
```

Commit: `upgrade_from_v1: symlink-safe archive (is_symlink before resolve)`

---

# Wave 4 — New test files (parallel)

## Task 15: `tests/test_install_alt_cwd.py`

```python
"""install.run() succeeds regardless of CWD; ignores shadowing db/."""

from __future__ import annotations


def test_install_runs_from_alt_cwd(tmp_memex_home, tmp_path, monkeypatch):
    alt = tmp_path / "elsewhere"
    alt.mkdir()
    monkeypatch.chdir(alt)
    import io, sys
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    from scripts import install
    install.run()
    for f in ("registry.json", "agents.db", "index.db", "article.db"):
        assert (tmp_memex_home / f).exists()


def test_install_idempotent(tmp_memex_home, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import io, sys
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\ny\n"))
    from scripts import install
    install.run()
    install.run()
    assert (tmp_memex_home / "registry.json").exists()


def test_install_ignores_shadowing_db_dir(tmp_memex_home, tmp_path, monkeypatch):
    fake_db = tmp_path / "db"
    fake_db.mkdir()
    (fake_db / "agents.sql").write_text("CREATE TABLE bogus (x INTEGER);")
    monkeypatch.chdir(tmp_path)
    import io, sys
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    from scripts import install
    install.run()

    import sqlite3
    conn = sqlite3.connect(str(tmp_memex_home / "agents.db"))
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
    ).fetchone() is not None
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bogus'"
    ).fetchone() is None
    conn.close()
```

Commit: `tests: install runs from arbitrary CWD; ignores shadowing db/`

---

## Task 16: `tests/test_modules_import_clean.py`

```python
"""require_bootstrap() must be call-time, not import-time."""

from __future__ import annotations

import importlib


def test_modules_import_clean(monkeypatch, tmp_path):
    monkeypatch.delenv("MEMEX_HOME", raising=False)
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no-home")
    for mod in [
        "scripts.brain", "scripts.stores", "scripts.roles",
        "scripts.embeddings", "scripts.agents",
        "scripts.agents.archivist", "scripts.agents.dba",
        "scripts.agents.data_steward", "scripts.agents.librarian",
        "scripts.agents.reference_librarian",
        "scripts.install", "scripts.upgrade_from_v1",
        "scripts.registry", "scripts.db",
    ]:
        try:
            m = importlib.import_module(mod)
            importlib.reload(m)
        except Exception as e:
            raise AssertionError(f"{mod} fails clean import: {e}")
```

Commit: `tests: all scripts.* modules import without MEMEX_HOME`

---

## Task 17: `tests/test_config_json.py`

```python
"""~/.memex/config.json read/write/validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.db import read_plugin_root_config, write_plugin_root_config


def test_write_then_read(tmp_memex_home):
    from scripts.paths import PLUGIN_ROOT
    write_plugin_root_config(PLUGIN_ROOT)
    config = tmp_memex_home / "config.json"
    assert config.exists()
    assert json.loads(config.read_text())["plugin_root"] == str(PLUGIN_ROOT)
    assert read_plugin_root_config() == PLUGIN_ROOT


def test_read_missing_returns_none(tmp_memex_home):
    assert read_plugin_root_config() is None


def test_read_invalid_returns_none(tmp_memex_home):
    (tmp_memex_home / "config.json").write_text("not json")
    assert read_plugin_root_config() is None


def test_read_stale_path_returns_none(tmp_memex_home, tmp_path):
    (tmp_memex_home / "config.json").write_text(
        json.dumps({"plugin_root": str(tmp_path / "nonexistent")})
    )
    assert read_plugin_root_config() is None


def test_read_path_missing_install_py_returns_none(tmp_memex_home, tmp_path):
    fake_plugin = tmp_path / "fake_plugin"
    fake_plugin.mkdir()
    (fake_plugin / "plugin.json").write_text(json.dumps({"name": "memex"}))
    (tmp_memex_home / "config.json").write_text(
        json.dumps({"plugin_root": str(fake_plugin)})
    )
    # Missing scripts/install.py → reject
    assert read_plugin_root_config() is None


def test_read_path_with_wrong_name_returns_none(tmp_memex_home, tmp_path):
    fake_plugin = tmp_path / "fake_plugin"
    (fake_plugin / "scripts").mkdir(parents=True)
    (fake_plugin / "scripts" / "install.py").write_text("# fake")
    (fake_plugin / "plugin.json").write_text(json.dumps({"name": "not-memex"}))
    (tmp_memex_home / "config.json").write_text(
        json.dumps({"plugin_root": str(fake_plugin)})
    )
    assert read_plugin_root_config() is None
```

Commit: `tests: config.json read/write/validation`

---

## Task 18: `tests/test_skill_run_preflight.py` — xfail until T23

```python
"""SKILL.md Step 0 preflight markers (presence-only, scoped)."""

from __future__ import annotations

from pathlib import Path

import pytest

SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "run" / "SKILL.md"

pytestmark = pytest.mark.xfail(strict=True, reason="Step 0 inserted in T23")


def _step_0_region() -> str:
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert text.count("## Step 0") == 1, "Expected exactly one Step 0 heading"
    after = text.split("## Step 0", 1)[1]
    parts = after.split("\n## ", 1)
    return "## Step 0" + parts[0]


def test_step_0_heading_present():
    assert "## Step 0" in _step_0_region()


def test_python_check_one_liner():
    region = _step_0_region()
    assert "python3 -c" in region
    assert "sys.version_info" in region
    assert "(3, 10)" in region


def test_initialization_check_paths():
    region = _step_0_region()
    for p in ("registry.json", "agents.db", "index.db", "article.db", "config.json"):
        assert p in region


def test_strict_y_n_via_stdin():
    region = _step_0_region()
    assert "(y/n)" in region
    # Consent piped to install.py via stdin
    assert 'echo "y"' in region or "echo \"y\"" in region


def test_install_invocation_uses_pythonpath_not_cd():
    region = _step_0_region()
    assert "PYTHONPATH=" in region
    # No reliance on cd persistence
    assert "cd \"<" not in region or "&&" not in region.split("cd ")[1].split("\n")[0]


def test_platform_install_blocks():
    region = _step_0_region().lower()
    assert "apt" in region
    assert "brew" in region
    assert "winget" in region


def test_two_blocks_for_v1():
    region = _step_0_region()
    # Block A (with v1) and Block B (without v1) both present.
    assert "Block A" in region or "v1 install" in region
    assert "HAS_V1" in region or "test -d" in region
```

Commit: `tests: SKILL.md Step 0 markers (xfail until T23)`

---

## Task 19: `tests/test_skill_preflight_smoke.py`

```python
"""Extract bash snippets from SKILL.md; execute them; check parseable output."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "run" / "SKILL.md"


def test_python_detection_snippet_executes():
    text = SKILL_PATH.read_text(encoding="utf-8")
    m = re.search(r"```bash\n(for cmd in python3[^\n]+\n(?:[^\n]+\n)+?done\nexit 1)\n```", text)
    if not m:
        import pytest
        pytest.skip("Step 0.1 python3 detection snippet not yet present")
    snippet = m.group(1)
    result = subprocess.run(snippet, shell=True, capture_output=True, text=True, timeout=10)
    assert result.returncode in (0, 1)
    if result.returncode == 0:
        assert "PYTHON=" in result.stdout
```

Commit: `tests: smoke-test python3 detection snippet from SKILL.md`

---

## Task 20: `tests/test_security_home_validation.py`

Tests for `$MEMEX_HOME` validation:
- Reject `/etc/memex`, `/`, `/tmp/memex` (without ALLOW_UNUSUAL)
- Reject symlinked `$MEMEX_HOME` (both explicit and default branches)
- Accept paths under `$HOME`
- `MEMEX_HOME_ALLOW_UNUSUAL=1` bypasses validation

(Most already in `tests/test_bootstrap_guard.py`; this file expands the coverage.)

---

## Task 21: `tests/test_security_v1_symlink.py`

Already created in T14. Skip here unless additional cases needed.

---

## Task 22: `tests/test_release_bundle.py` — assert INSTALL.md uses python3

Append to existing file:

```python
def test_install_md_uses_python3(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from scripts import release
    release.build("2.5.0")
    install_md = (tmp_path / "dist" / "v2.5.0" / "INSTALL.md").read_text()
    assert "python3 -m scripts.install" in install_md
    assert "python -m scripts.install" not in install_md
```

Commit: `tests: assert generated INSTALL.md uses python3`

---

# Wave 5 — SKILL Step 0

## Task 23: Insert Step 0 in `skills/run/SKILL.md`

- [ ] **Step 1: Verify anchor**

```bash
grep -n "v2.0 architecture" skills/run/SKILL.md
```

Should match exactly once.

- [ ] **Step 2: Remove xfail marker in test_skill_run_preflight.py**

Delete the `pytestmark = pytest.mark.xfail(...)` line.

- [ ] **Step 3: Insert Step 0 in SKILL.md**

Insert after the "v2.0 architecture" line, before `## v2 Brain user-facing intent routing`:

(The full Step 0 block from spec §"Step 0 — Preflight", verbatim. The implementing agent should refer to the spec for the exact prose.)

- [ ] **Step 4: Run full suite**

```bash
pytest tests/ -v
```

All pass.

- [ ] **Step 5: Commit**

```bash
git add skills/run/SKILL.md tests/test_skill_run_preflight.py
git commit -m "skills/run: Step 0 preflight (python3 check + config.json plugin-root + y/n stdin consent)"
```

---

# Wave 6 — Documentation normalization (parallel)

## Task 24: `README.md`

Apply edits per spec §"Documentation":
- Line 30: plugin path → `~/.claude/plugins/cache/<marketplace>/memex/<version>/`
- Line 32: Step 4 rewrite (auto-bootstrap)
- Line 44: `pip install pytest...` → `python3 -m pip install pytest...`
- Lines 53, 61: `python -m` → `python3 -m`

Verify:
```bash
grep -nE "python -m|claude-code/plugins|^pip install" README.md
```
Should show no matches.

Commit: `docs(README): normalize python3, plugin path, auto-bootstrap step`

---

## Task 25: `USER_GUIDE.md`

Line 9 rewrite + lines 188/196/206 `python` → `python3`. Commit: `docs(USER_GUIDE): normalize python3 + auto-bootstrap`

---

## Task 26: `docs/CORE.md`

Line 37 rewrite. Commit: `docs(CORE): python3 + Step 0.2 cross-reference`

---

## Task 27: `docs/PACKAGING.md`

Lines 48, 110 `python -m` → `python3 -m`. Commit.

---

## Task 28: `scripts/release.py` INSTALL.md template

Edit template body to use `python3` and corrected plugin path. Commit.

---

## Task 29: `internal/brain/ingest/SKILL.md`

Delete line 114, reword 115 (per spec §"Documentation"). Commit.

---

## Task 30: `docs/specs/2026-05-16-memex-v2-redesign-design.md`

Append §8.5 cross-reference. Commit.

---

# Wave 7 — Release prep

## Task 31: `CHANGELOG.md` v2.5.0 entry

Insert below top heading, above v2.4.1. Use the entry from spec §"v2.5.0 — 2026-05-17" verbatim. Commit.

---

## Task 32: `python3 -m scripts.bump 2.5.0`

```bash
python3 -m scripts.bump 2.5.0
```

Verify version updates in `plugin.json`, `pyproject.toml`. Commit.

---

# Wave 8 — Verification + PR

## Task 33: Local CI gate + PR

```bash
ruff check . && ruff format --check .
bandit -c pyproject.toml -r scripts internal skills db
pytest tests/ -v
```

All pass. Then:

```bash
gh pr create --title "Install hardening: preflight + CWD decoupling + security pass (v2.5.0)" --body "$(cat <<'EOF'
## Summary
Closes 8 problems in `docs/specs/2026-05-17-install-hardening-design.md`:
- A: Auto-bootstrap on memex:run via SKILL Step 0
- B: CWD-independent bundle reads via scripts/paths.py
- C: Module discovery + sibling-import fix (relocate _internal_agents_seed)
- D: python3 / python3 -m pip normalization
- E: $MEMEX_HOME + ~/.memex/ validation
- F: v1 archive symlink protection
- G: Internal agent profile hash-pinning
- H: flock-based concurrent install lock

Plus: ~/.memex/config.json persistent plugin-root cache, Python-deterministic y/n consent gate, .gitattributes for cross-platform line endings.

Spec: docs/specs/2026-05-17-install-hardening-design.md
Plan: docs/plans/2026-05-17-install-hardening-plan.md

## Test plan
- [ ] pytest tests/ passes
- [ ] ruff check . && ruff format --check . passes
- [ ] bandit -c pyproject.toml -r scripts internal skills db passes
- [ ] tests/test_install_alt_cwd.py: install runs from /tmp and ignores shadowing db/
- [ ] tests/test_bootstrap_guard.py: MemexNotInitializedError raises on empty home
- [ ] tests/test_security_*.py: all 4 security fixes exercised
- [ ] tests/test_skill_run_preflight.py: Step 0 markers present
- [ ] tests/test_modules_import_clean.py: all scripts.* import without MEMEX_HOME

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review Checklist

**Spec coverage:**

| Spec section | Task(s) |
|---|---|
| §A Bootstrap UX | T23 |
| §B Path-relative reads | T1, T7-T9, T11, T12 |
| §C Module discovery + sibling import | T2, T7 |
| §D python3 normalization | T24–T30 |
| §E $MEMEX_HOME + ~/.memex/ validation | T5 |
| §F v1 archive symlink protection | T14 |
| §G Profile hash-pin | T2, T7 |
| §H Concurrent install lock | T7 |
| `~/.memex/config.json` | T5, T17 |
| `scripts/paths.py` | T1 |
| Test migration script | T6 |
| `MemexNotInitializedError` wiring | T5, T7–T13 |
| Documentation | T24–T30 |
| CHANGELOG + bump | T31, T32 |

**Wave dependencies:** clean. Wave 2 adds validation + migration script + fixtures BEFORE Wave 3's guards land. xfail tests in Wave 4 turn green in Wave 5.
