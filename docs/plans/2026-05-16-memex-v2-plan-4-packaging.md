# Memex v2 — Plan 4: Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Memex v2 as a Claude Code custom plugin update. Includes install/upgrade flow from v1, packaging the `dist/` artifact, README + user-guide, CHANGELOG entry, and a clean version bump. End state: a user with v1 installed can upgrade to v2 and have `~/.memex/` set up correctly, with the single `memex:run` skill registered and all 24 internal procedures routable through it (per spec §8.0).

**Architecture:** Plan 4 is mostly plumbing and documentation. The novel piece is the v1 → v2 upgrade path: detect prior install, archive v1 artifacts (do not migrate content per design decision §5), seed v2 from scratch.

**Tech Stack:** Same as Plans 1-3. Additional: `pyinstaller`-free zip-based plugin packaging (Memex stays stdlib-only at runtime; install-time bundling is the responsibility of the release script).

**Reference:** spec at `docs/specs/2026-05-16-memex-v2-redesign-design.md` (sections §9, §12).

**Depends on:** Plans 1, 2, 3.

---

## File Structure

```
memex/
├── scripts/
│   ├── upgrade_from_v1.py                         # NEW: detect + archive v1
│   └── release.py                                 # NEW: build dist/ artifact
├── dist/                                          # NEW: build output (gitignored body, manifest checked in)
│   └── v2.0.0/                                    # populated by release.py
│       ├── manifest.json
│       ├── plugin.json                            # registers only memex:run (spec §8.0)
│       ├── scripts/
│       ├── skills/                                # top-level: only run/SKILL.md
│       ├── internal/                              # 24 procedures, NOT auto-loaded
│       ├── db/
│       ├── prompts/
│       └── INSTALL.md
├── README.md                                      # MODIFY: rewrite for v2.0
├── USER_GUIDE.md                                  # NEW: how to use Memex v2.0
├── CHANGELOG.md                                   # MODIFY: add v2.0.0 entry
├── pyproject.toml                                 # MODIFY: version 2.0.0
├── .gitignore                                     # MODIFY: ignore dist body
└── tests/
    ├── test_upgrade_from_v1.py                    # NEW
    ├── test_release_bundle.py                     # NEW
    └── test_smoke_plan4.py                        # NEW: install + upgrade round-trip
```

---

## Task 1: `upgrade_from_v1.py` — detect and archive v1

**Files:**
- Create: `scripts/upgrade_from_v1.py`
- Create: `tests/test_upgrade_from_v1.py`

- [ ] **Step 1: Write the failing test**

`tests/test_upgrade_from_v1.py`:

```python
import pytest
from pathlib import Path
from scripts import upgrade_from_v1
from scripts.db import memex_home


def test_detect_v1_returns_false_when_no_prior_install(tmp_memex_home, monkeypatch):
    monkeypatch.delenv("MEMEX_V1_PATH", raising=False)
    assert upgrade_from_v1.detect_v1_install() is None


def test_detect_v1_returns_path_when_v1_dir_present(tmp_memex_home, tmp_path, monkeypatch):
    v1_dir = tmp_path / "memex-v1"
    v1_dir.mkdir()
    (v1_dir / ".ai").mkdir()
    (v1_dir / ".ai" / "memex.db").write_text("v1 db placeholder")
    (v1_dir / ".ai" / "wiki").mkdir()
    monkeypatch.setenv("MEMEX_V1_PATH", str(v1_dir))

    result = upgrade_from_v1.detect_v1_install()
    assert result == v1_dir


def test_archive_v1_moves_content_to_legacy(tmp_memex_home, tmp_path, monkeypatch):
    v1_dir = tmp_path / "memex-v1"
    v1_dir.mkdir()
    (v1_dir / ".ai").mkdir()
    (v1_dir / ".ai" / "memex.db").write_text("v1 db")
    (v1_dir / ".ai" / "wiki").mkdir()
    (v1_dir / ".ai" / "wiki" / "test.md").write_text("wiki content")
    monkeypatch.setenv("MEMEX_V1_PATH", str(v1_dir))

    upgrade_from_v1.archive_v1()

    legacy = memex_home() / "legacy" / "v1-wiki"
    assert legacy.exists()
    assert (legacy / "memex.db").exists()
    assert (legacy / "wiki" / "test.md").exists()


def test_archive_v1_no_op_when_no_v1(tmp_memex_home, monkeypatch):
    monkeypatch.delenv("MEMEX_V1_PATH", raising=False)
    # Should not raise
    result = upgrade_from_v1.archive_v1()
    assert result is None


def test_upgrade_logs_to_changelog(tmp_memex_home, tmp_path, monkeypatch):
    v1_dir = tmp_path / "memex-v1"
    v1_dir.mkdir()
    (v1_dir / ".ai").mkdir()
    (v1_dir / ".ai" / "memex.db").write_text("v1")
    monkeypatch.setenv("MEMEX_V1_PATH", str(v1_dir))

    upgrade_from_v1.archive_v1()

    log_path = memex_home() / "legacy" / "upgrade-log.md"
    assert log_path.exists()
    assert "v1" in log_path.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_upgrade_from_v1.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`scripts/upgrade_from_v1.py`:

```python
"""v1 → v2 upgrade: detect prior v1 install, archive content, log.

Per design decision §5 of the spec: v1 wiki content is NOT migrated
to brain.db. The .ai/wiki/ directory is preserved as a legacy archive
the user can manually re-ingest if desired.
"""
from __future__ import annotations
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from scripts.db import memex_home


def detect_v1_install() -> Path | None:
    """Return the v1 install path if MEMEX_V1_PATH is set and contains .ai/."""
    v1_env = os.environ.get("MEMEX_V1_PATH")
    if not v1_env:
        return None
    p = Path(v1_env)
    if not p.exists():
        return None
    if not (p / ".ai").exists():
        return None
    return p


def archive_v1() -> Path | None:
    """If a v1 install is detected, archive its .ai/ content to
    ~/.memex/legacy/v1-wiki/ and write an upgrade log entry.

    Returns the archive path, or None if no v1 was found.
    """
    v1_dir = detect_v1_install()
    if v1_dir is None:
        return None

    legacy_root = memex_home() / "legacy" / "v1-wiki"
    legacy_root.parent.mkdir(parents=True, exist_ok=True)

    if legacy_root.exists():
        # Already archived; idempotent no-op
        _append_log("v1 archive already present; skipping re-archive.")
        return legacy_root

    shutil.copytree(v1_dir / ".ai", legacy_root)
    _append_log(f"Archived v1 .ai/ from {v1_dir} to {legacy_root}.")
    return legacy_root


def _append_log(message: str) -> None:
    log_path = memex_home() / "legacy" / "upgrade-log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    if not log_path.exists():
        log_path.write_text("# Memex Upgrade Log\n\n")
    with log_path.open("a") as f:
        f.write(f"- {ts} | {message}\n")


if __name__ == "__main__":
    result = archive_v1()
    if result is None:
        print("No v1 install detected; nothing to archive.")
    else:
        print(f"v1 archive: {result}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_upgrade_from_v1.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/upgrade_from_v1.py tests/test_upgrade_from_v1.py
git commit -m "feat(packaging): detect and archive v1 install (no content migration per spec)"
```

---

## Task 2: Integrate upgrade into `install.py`

**Files:**
- Modify: `scripts/install.py`
- Modify: `tests/test_install.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_install.py`:

```python
def test_install_archives_v1_if_present(tmp_memex_home, tmp_path, monkeypatch):
    v1_dir = tmp_path / "memex-v1"
    v1_dir.mkdir()
    (v1_dir / ".ai").mkdir()
    (v1_dir / ".ai" / "memex.db").write_text("v1")
    monkeypatch.setenv("MEMEX_V1_PATH", str(v1_dir))

    install.run()

    legacy = memex_home() / "legacy" / "v1-wiki"
    assert legacy.exists()
    assert (legacy / "memex.db").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_install.py::test_install_archives_v1_if_present -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Modify `scripts/install.py` — at the top of `run()`, before other initialization:

```python
def run() -> None:
    # Plan 4: archive v1 if present (no-op otherwise)
    from scripts import upgrade_from_v1
    upgrade_from_v1.archive_v1()

    # ... rest of run() body unchanged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_install.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/install.py tests/test_install.py
git commit -m "feat(packaging): install.run archives v1 install if MEMEX_V1_PATH is set"
```

---

## Task 3: Version bump

**Files:**
- Modify: `pyproject.toml`
- Modify: `plugin.json`

- [ ] **Step 1: Write the failing test**

Create `tests/test_version.py`:

```python
import json
from pathlib import Path
import re


def test_pyproject_version_is_0_2_0():
    content = Path("pyproject.toml").read_text()
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    assert match
    assert match.group(1) == "2.0.0"


def test_plugin_json_version_is_0_2_0():
    data = json.loads(Path("plugin.json").read_text())
    assert data["version"] == "2.0.0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_version.py -v`
Expected: FAIL (currently 2.0.0-dev).

- [ ] **Step 3: Write minimal implementation**

Update `pyproject.toml`:

```toml
version = "2.0.0"
```

Update `plugin.json`:

```json
"version": "2.0.0"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_version.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml plugin.json tests/test_version.py
git commit -m "chore: bump version to 2.0.0"
```

---

## Task 4: `release.py` — bundle dist/

**Files:**
- Create: `scripts/release.py`
- Create: `.gitignore` (modify)
- Create: `tests/test_release_bundle.py`

- [ ] **Step 1: Write the failing test**

`tests/test_release_bundle.py`:

```python
import json
import pytest
from pathlib import Path
from scripts import release


def test_build_dist_creates_versioned_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(Path.cwd())  # ensure we run from the repo
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    assert (target / "v2.0.0").exists()


def test_dist_has_manifest_json(tmp_path):
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    manifest = json.loads((target / "v2.0.0" / "manifest.json").read_text())
    assert manifest["version"] == "2.0.0"
    assert "files" in manifest


def test_dist_includes_all_skills(tmp_path):
    """Per spec §8.0, only memex:run is registered at top level; the 24
    internal procedures live under internal/<category>/<name>/SKILL.md
    and must all be included in the bundle."""
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    bundle = target / "v2.0.0"
    # Top-level skills/ holds only the memex:run registration entry.
    assert (bundle / "skills" / "run" / "SKILL.md").exists()
    # The 24 procedures live under internal/<category>/.
    internal_dir = bundle / "internal"
    assert (internal_dir / "core").is_dir()
    assert (internal_dir / "index").is_dir()
    assert (internal_dir / "brain").is_dir()
    assert (internal_dir / "steward").is_dir()
    assert (internal_dir / "dba").is_dir()


def test_dist_includes_plugin_json(tmp_path):
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    assert (target / "v2.0.0" / "plugin.json").exists()


def test_dist_includes_install_md(tmp_path):
    target = tmp_path / "dist"
    release.build(version="2.0.0", target_root=target)
    install_doc = target / "v2.0.0" / "INSTALL.md"
    assert install_doc.exists()
    assert "2.0.0" in install_doc.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`scripts/release.py`:

```python
"""Build a dist/v<version>/ bundle for Claude Code plugin distribution.

The bundle includes: plugin.json, scripts/, skills/, db/, prompts/,
a manifest.json with file inventory, and INSTALL.md instructions.

dist/ body is gitignored; only manifest tracking is committed.
"""
from __future__ import annotations
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
import hashlib


_INCLUDE_DIRS = ["scripts", "skills", "internal", "db", "prompts"]
_INCLUDE_FILES = ["plugin.json", "pyproject.toml", "README.md", "USER_GUIDE.md", "CHANGELOG.md"]


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(version: str, target_root: Path | str = "dist") -> Path:
    """Build a dist bundle. Returns the path to the version directory."""
    target_root = Path(target_root)
    version_dir = target_root / f"v{version}"
    if version_dir.exists():
        shutil.rmtree(version_dir)
    version_dir.mkdir(parents=True)

    repo_root = Path.cwd()
    files_manifest: list[dict] = []

    # Copy directories
    for dirname in _INCLUDE_DIRS:
        src = repo_root / dirname
        if not src.exists():
            continue
        dst = version_dir / dirname
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for f in dst.rglob("*"):
            if f.is_file():
                files_manifest.append({
                    "path": str(f.relative_to(version_dir)),
                    "sha256": _hash_file(f),
                    "bytes": f.stat().st_size,
                })

    # Copy individual files
    for fname in _INCLUDE_FILES:
        src = repo_root / fname
        if not src.exists():
            continue
        dst = version_dir / fname
        shutil.copy2(src, dst)
        files_manifest.append({
            "path": fname,
            "sha256": _hash_file(dst),
            "bytes": dst.stat().st_size,
        })

    # INSTALL.md (generated, not copied)
    install_md = f"""# Memex v{version} Install Instructions

## Fresh install

1. Place this bundle in `~/.claude-code/plugins/memex/` (or your plugin directory).
2. Restart Claude Code or invoke `/plugin reload memex`.
3. Invoke `memex:run` and express your first intent (e.g. "ingest this article"). On first invocation of any Brain operation you will be prompted to register a human agent.

## Upgrading from v0.1

1. Set `MEMEX_V1_PATH` to your prior install root (the directory containing `.ai/`).
2. Place this bundle in `~/.claude-code/plugins/memex/` (replace prior bundle).
3. On first `memex:*` skill invocation, the plugin will archive v1's `.ai/` to
   `~/.memex/legacy/v1-wiki/` and bootstrap v2. v1 wiki content is preserved but
   NOT auto-migrated to v2 brain.db (per design decision).

## Verifying

Run `python -m scripts.install` to bootstrap `~/.memex/`. Then check:
- `~/.memex/agents.db` exists
- `~/.memex/index.db` exists
- `~/.memex/article.db` exists
- `~/.memex/registry.json` lists `agents`, `index`, `article`

## Embedding setup

v2.0 uses OpenAI text-embedding-3-small by default. Set `OPENAI_API_KEY`
or switch providers via `MEMEX_EMBEDDING_PROVIDER` (`voyage`, `local`).

## Skills shipped

**Memex v2.0 registers a single skill (`memex:run`)** with Claude Code,
then routes 24 internal procedures on demand via its body. This stays
well under Claude Code's 1% skill-description budget — the per-skill
descriptions for 24 entries would otherwise consume significant
context-window budget and risk truncation.

All 24 procedures live at `internal/<category>/<name>/SKILL.md` and are
reached via the routing tables inside `skills/run/SKILL.md`. The user
expresses intent (e.g. "ingest this article"); agents call CRUD
primitives by name. `memex:run` reads the matching procedure file on
demand and follows it.
"""
    (version_dir / "INSTALL.md").write_text(install_md)
    files_manifest.append({
        "path": "INSTALL.md",
        "sha256": _hash_file(version_dir / "INSTALL.md"),
        "bytes": (version_dir / "INSTALL.md").stat().st_size,
    })

    # Manifest
    manifest = {
        "version": version,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files_manifest),
        "files": sorted(files_manifest, key=lambda f: f["path"]),
    }
    (version_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return version_dir


if __name__ == "__main__":
    import sys
    version = sys.argv[1] if len(sys.argv) > 1 else "2.0.0"
    out = build(version)
    print(f"Built: {out}")
```

Modify `.gitignore` to add:

```
# Memex dist bundles — manifest tracked separately
dist/v*/
!dist/v*/manifest.json
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_release_bundle.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/release.py .gitignore tests/test_release_bundle.py
git commit -m "feat(packaging): release.build creates versioned dist bundle with manifest"
```

---

## Task 5: README rewrite for v2.0

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the failing test**

`tests/test_readme.py`:

```python
from pathlib import Path


def test_readme_mentions_v0_2():
    content = Path("README.md").read_text()
    assert "0.2" in content


def test_readme_mentions_three_layers():
    content = Path("README.md").read_text().lower()
    assert "brain" in content
    assert "index" in content
    assert "core" in content


def test_readme_mentions_internal_agents():
    content = Path("README.md").read_text()
    for agent in ["Librarian", "Reference Librarian", "Archivist"]:
        assert agent in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_readme.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Rewrite `README.md`:

```markdown
# Memex

**A personal knowledge runtime and shared memory plane for the agent fleet.**

Memex is the second-brain product of Skill Atelier (Product 1). It hosts your
personal knowledge — articles you read, notes you capture, syntheses you
produce — and serves as the shared memory layer for AI agents working on
your behalf.

## What's in v2.0

Three layers:

1. **Memex Brain** — opinionated second-brain skill layer. `ingest`, `ask`,
   `capture`, `lint`, `synthesize`. Stores articles, notes, and syntheses
   in `~/.memex/article.db`.
2. **Memex Index + 5 internal agents** — Librarian, Reference Librarian,
   Archivist, Database Administrator, Data Steward. Mandatory write-path
   gateway. Federated metadata, FTS5, embeddings, cross-store relationships.
3. **Memex Core** — CRUD substrate. Provisions and hosts arbitrary SQLite
   stores from consumer-supplied SQL migration files. Schema-agnostic.

24 internal procedures routed via the single `memex:run` skill, distributed via the Claude Code plugin. Per spec §8.0 only `memex:run` is registered with Claude Code — it routes natural-language user intents and agent-facing CRUD operations to the matching procedure on demand, keeping the plugin's skill-description footprint well under Claude Code's 1% budget.

## Installation

See `dist/v2.0.0/INSTALL.md` (after running `python -m scripts.release`).

For development:

```bash
python -m scripts.install
```

This bootstraps `~/.memex/`, seeds the 5 internal agents, creates the
default `article.db`, and registers everything in the global registry.

## Key design decisions (locked)

- Personal KM is the primary use case; project memory is a secondary
  capability via consumer stores (Atelier-style).
- SQLite-first; markdown is an export view, not the source of truth.
- Every document goes through the Librarian — no bypass.
- Eventually consistent across (Index, target store); Data Steward
  reconciles orphans.
- Open-ended `rel_type` vocabulary; Librarian's prompt is the consistency
  mechanism.
- Hybrid retrieval: FTS5 + vector embeddings from day one.

See `docs/specs/2026-05-16-memex-v2-redesign-design.md` for the full design.

## Layout

```
~/.memex/
├── agents.db       # roles + agents (5 Memex internal, plus your registered self)
├── index.db        # documents + relations + FTS5 + embeddings
├── article.db      # Brain's default store (articles + captures + syntheses)
├── registry.json   # registered stores
├── raw/            # Archivist's content-addressable raw archive
├── audits/         # Data Steward reports
└── legacy/         # v1 install (archived, not migrated)
```

## Status

v2.0.0 — released 2026-05-16 (or build date).

## Layer awareness

This repo is Layer 2 (a Skill Atelier product). Framework changes live at
the Skill Atelier repo; product changes live here.
```

- [ ] **Step 4: Run tests to verify they pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_readme.py
git commit -m "docs: rewrite README for v2.0 three-layer architecture"
```

---

## Task 6: USER_GUIDE.md

**Files:**
- Create: `USER_GUIDE.md`

- [ ] **Step 1: Write the failing test**

`tests/test_user_guide.py`:

```python
from pathlib import Path


def test_user_guide_exists():
    assert Path("USER_GUIDE.md").exists()


def test_user_guide_covers_all_brain_skills():
    content = Path("USER_GUIDE.md").read_text()
    for s in ["ingest", "ask", "capture", "lint", "synthesize"]:
        assert s in content


def test_user_guide_describes_onboarding():
    content = Path("USER_GUIDE.md").read_text().lower()
    assert "onboarding" in content or "first invocation" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`USER_GUIDE.md`:

```markdown
# Memex v2.0 — User Guide

## First-time setup

1. Install the plugin (see `dist/v2.0.0/INSTALL.md`).
2. Restart Claude Code.
3. Run `python -m scripts.install` (one-time bootstrap).
4. Set `OPENAI_API_KEY` if using the default embedding provider, or
   `MEMEX_EMBEDDING_PROVIDER=voyage|local` to switch.

## How to invoke Memex

Per spec §8.0, Memex registers a single Claude Code skill: `memex:run`.
You don't invoke `memex:brain:ingest` or `memex:brain:ask` as
top-level skills — those names are not in `plugin.json`. Instead you
invoke `memex:run` and express your intent in natural language. The
plugin routes the intent to the matching internal procedure under
`internal/brain/<name>/SKILL.md`, reads it, and follows it. Examples:

- "ingest this article: <url or body>" → `internal/brain/ingest/SKILL.md`
- "ask my brain: what did I read about transformers?" → `internal/brain/ask/SKILL.md`
- "capture this thought: ..." → `internal/brain/capture/SKILL.md`
- "lint my brain" or "audit my brain" → `internal/brain/lint/SKILL.md`
- "synthesize across these sources: ..." → `internal/brain/synthesize/SKILL.md`

The procedure descriptions below name each operation by its logical
identifier (`memex:brain:ingest`, etc.) for clarity — the underlying
implementation lives at `internal/brain/<name>/SKILL.md`.

## Onboarding

The first time you invoke a Brain operation (ingest, capture, etc.) via
`memex:run`, Memex will prompt you to register a human agent:

> "What's your agent id? (lowercase, dashes; example: `human-user`)"
> "Display name?"
> "Role? (default: User; can be Researcher, Owner, Editor, or custom)"

Your agent is registered in `~/.memex/agents.db` and used for attribution
on every write.

## Daily skills

### `memex:brain:ingest` — add an article

Hands an article (with optional source URL) to the Librarian, who
classifies it, links it to related entries in your Index, and stores it
in `~/.memex/article.db`.

Re-ingesting the same content is a silent no-op (source-hash check).

### `memex:brain:ask` — query

Natural-language questions go through the Reference Librarian, who runs
hybrid FTS5 + vector retrieval across the entire Index (all stores) and
returns ranked, citation-ready results.

### `memex:brain:capture` — quick note

Lighter than `ingest` — no source URL, no hash check. For thoughts,
observations, snippets.

### `memex:brain:lint` — health check

Runs the Data Steward audit. Reports orphans, broken relations, drift.
Read-only; never auto-fixes. Resolve findings via
`memex:steward:reconcile-orphan`.

### `memex:brain:synthesize` — cross-document synthesis

Pass a list of source `index_id`s and a topic. The Synthesizer LLM
produces a unified prose synthesis with inline citations. Result is
indexed as a `synthesis` document.

## Working with multiple stores

Memex hosts more than just your Brain. If you have Atelier installed,
or any other consumer that uses Memex Core, each has its own store.
The Index spans them all.

You can ask cross-store questions: "what decisions did the team make
about authentication?" — the Reference Librarian queries the Index,
finds matches in your articles AND Atelier's decisions table, and
returns ranked results from both.

## Maintenance

### Periodic audit

Invoke `memex:run` and say "lint my brain" (Brain-scoped) or "audit
the full Memex Index" (full sweep). The plugin routes to
`internal/brain/lint/SKILL.md` or `internal/steward/audit/SKILL.md`.

Recommended monthly or after bulk ingest activity.

### Vacuum

Invoke `memex:run` and say "vacuum the `article` store" (or any
registered store name). Routes to `internal/dba/vacuum/SKILL.md`.

Reclaims space. Run during quiet periods.

### Backup

Copy `~/.memex/` and any `<repo>/.memex/` directories. SQLite files
are self-contained.

## Troubleshooting

### "Agent not registered"

You skipped onboarding. Run:
```
python -m scripts.onboarding register <id> <name> <role>
```

### "Unknown store"

The store name you used isn't in `~/.memex/registry.json`. Check with:
```
python -m scripts.registry list
```

### Audit reports orphans

Open the latest report in `~/.memex/audits/`. For each finding, invoke
`memex:run` and say e.g. "reconcile orphan idx-XYZ with action
delete-index"; it routes to
`internal/steward/reconcile-orphan/SKILL.md`.
```

- [ ] **Step 4: Run tests to verify they pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add USER_GUIDE.md tests/test_user_guide.py
git commit -m "docs: USER_GUIDE.md covering daily Brain skills + maintenance"
```

---

## Task 7: CHANGELOG entry

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write the failing test**

`tests/test_changelog.py`:

```python
from pathlib import Path


def test_changelog_has_v0_2_0_section():
    content = Path("CHANGELOG.md").read_text()
    assert "2.0.0" in content or "v2.0.0" in content


def test_changelog_mentions_breaking_changes():
    content = Path("CHANGELOG.md").read_text().lower()
    # v2 is a substantial rewrite; the changelog must call it out
    assert "breaking" in content or "rewrite" in content or "redesign" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL (no v2.0.0 section yet).

- [ ] **Step 3: Write minimal implementation**

Prepend to `CHANGELOG.md`:

```markdown
## v2.0.0 — 2026-05-16

**Major redesign.** Memex is no longer a project-scoped wiki. It is now a
personal knowledge runtime and shared memory plane for the agent fleet.

### Breaking changes

- `.ai/memex.db` is no longer used. v2 lives at `~/.memex/` (machine-global).
- v1 wiki content is NOT auto-migrated. v1 `.ai/` is archived to
  `~/.memex/legacy/v1-wiki/` on first v2 install (if `MEMEX_V1_PATH` is set).
  Re-ingest manually via `memex:brain:ingest`.
- Self-improvement loop skills (`capture-lesson`, `review-lessons`,
  `propose-wiki-entry`, `review-wiki`) are dropped from Brain. Lessons-as-a-
  consumer is a future project.
- `synced-at-commit` git-anchored staleness is no longer load-bearing. It can
  return as a consumer-specific column if needed.

### Added

- **Three-layer architecture:** Memex Brain (5 skills) / Memex Index +
  5 internal agents / Memex Core (10 CRUD skills).
- **Five Memex-internal agents:** Librarian (Dr. Lakshmi Iyer-Ranganathan),
  Reference Librarian (Dr. Eleanor Whitfield), Archivist (Dr. Heinrich
  Mühlbauer), Database Administrator (Dr. Rajesh Subramanian), Data
  Steward (Dr. Ingrid Bergström).
- **Federated Index** (`~/.memex/index.db`): documents + relations + FTS5 +
  embeddings. Mandatory write-path gateway via the Librarian.
- **Hybrid retrieval** (FTS5 + vector cosine) via Reference Librarian.
  OpenAI `text-embedding-3-small` default; pluggable provider.
- **Content-addressable raw archive** (`~/.memex/raw/`) via Archivist.
- **Multi-store substrate.** Core hosts arbitrary SQLite stores from
  consumer-supplied SQL migrations. Atelier and any future consumer share
  the substrate.
- **24 internal procedures** spanning `memex:core:*`, `memex:index:*`,
  `memex:brain:*`, `memex:steward:*`, `memex:dba:*` — all reached via
  `memex:run`'s routing table (see "Single-skill registration model"
  below).
- **Single-skill registration model.** Only `memex:run` is registered
  in `plugin.json`. All 24 operations live as internal procedures
  (`internal/<category>/<name>/SKILL.md`) discovered through
  `memex:run`'s routing table. This avoids Claude Code's 1%
  skill-description budget truncation.
- **Eventually consistent** atomicity contract between Index and target
  stores; Data Steward reconciles orphans via audit.

### Changed

- Storage model is SQLite-first. Markdown is a derived export view.
- Cold-start cost reduced significantly: no ops-file routing, no `hot.md`,
  no response-footer compliance tax.
- Plugin remains a Claude Code custom plugin, globally accessible from any
  session regardless of working directory.

### Removed

- Obsidian integration. Memex v2 is Claude Code-native.
- Web-Clipper-driven ingestion. `memex:brain:ingest` accepts payloads
  directly (URL, body, or both).
- The `!! command` syntax. Skills are invoked through Claude Code's
  standard skill mechanism.

---

## v0.1.0 — 2026-05-10

Initial release. Project-scoped wiki with git-anchored staleness. See git
history for details.
```

- [ ] **Step 4: Run tests to verify they pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md tests/test_changelog.py
git commit -m "docs: CHANGELOG entry for v2.0.0"
```

---

## Task 8: End-to-end smoke test (Plan 4)

**Files:**
- Create: `tests/test_smoke_plan4.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from pathlib import Path
from scripts import install, release
from scripts.db import memex_home


def test_fresh_install_creates_all_components(tmp_memex_home):
    """Fresh install (no v1 to archive) should bootstrap cleanly."""
    install.run()
    # Plan 1
    assert (memex_home() / "agents.db").exists()
    # Plan 2
    assert (memex_home() / "index.db").exists()
    # Plan 3
    assert (memex_home() / "article.db").exists()
    # Plan 4 — legacy dir created lazily on first archive, not at install


def test_upgrade_from_v1_archives_then_installs_v2(tmp_memex_home, tmp_path, monkeypatch):
    """Upgrade flow: v1 → archived → v2 installed alongside."""
    v1 = tmp_path / "v1"
    v1.mkdir()
    (v1 / ".ai").mkdir()
    (v1 / ".ai" / "memex.db").write_text("v1 placeholder")
    (v1 / ".ai" / "wiki").mkdir()
    (v1 / ".ai" / "wiki" / "test-entry.md").write_text("# Test\n\nContent")
    monkeypatch.setenv("MEMEX_V1_PATH", str(v1))

    install.run()

    # v1 archived
    legacy = memex_home() / "legacy" / "v1-wiki"
    assert legacy.exists()
    assert (legacy / "wiki" / "test-entry.md").exists()

    # v2 fully installed
    assert (memex_home() / "agents.db").exists()
    assert (memex_home() / "index.db").exists()
    assert (memex_home() / "article.db").exists()


def test_release_bundle_builds(tmp_path):
    """Build a dist bundle in a temp dir and verify structure."""
    out = release.build(version="2.0.0", target_root=tmp_path / "dist")
    assert (out / "manifest.json").exists()
    assert (out / "plugin.json").exists()
    assert (out / "INSTALL.md").exists()
    # Top-level skills/ holds the memex:run registration entry.
    assert (out / "skills" / "run" / "SKILL.md").exists()
    # The 24 procedures live under internal/<category>/ (spec §8.0).
    assert (out / "internal" / "core").is_dir()
    assert (out / "internal" / "index").is_dir()
    assert (out / "internal" / "brain").is_dir()
```

- [ ] **Step 2-4: Run the test**

Run: `pytest tests/test_smoke_plan4.py -v`
Expected: PASS.

Full suite: `pytest tests/ -v` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_smoke_plan4.py
git commit -m "test(packaging): end-to-end install + upgrade + release smoke"
```

---

## Task 9: Build the v2.0.0 release artifact

**Files:**
- Generates: `dist/v2.0.0/` (manifest tracked; body gitignored)

- [ ] **Step 1: Run the release build**

```bash
python -m scripts.release 2.0.0
```

Expected output: `Built: dist/v2.0.0`

- [ ] **Step 2: Verify**

```bash
ls dist/v2.0.0/
cat dist/v2.0.0/manifest.json | head -20
```

Expected: directory contains plugin.json, scripts/, skills/, db/, prompts/, INSTALL.md, manifest.json.

- [ ] **Step 3: Sanity check the manifest**

```bash
python -c "import json; m = json.load(open('dist/v2.0.0/manifest.json')); print(f'Files: {m[\"file_count\"]}'); print(f'Version: {m[\"version\"]}')"
```

Expected: file count > 30, version "2.0.0".

- [ ] **Step 4: Commit the manifest**

`.gitignore` already excludes `dist/v*/` body but keeps `manifest.json`:

```bash
git add dist/v2.0.0/manifest.json
git commit -m "release: Memex v2.0.0 bundle manifest"
```

- [ ] **Step 5: Tag the release**

```bash
git tag -a v2.0.0 -m "Memex v2.0.0 — three-layer redesign"
```

Push the tag in a separate step after user review:

```bash
# Deferred until user approves
# git push origin v2.0.0
```

---

## Task 10: Plan 4 doc

**Files:**
- Create: `docs/PACKAGING.md`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


def test_packaging_doc_exists():
    assert Path("docs/PACKAGING.md").exists()
```

- [ ] **Step 2-3: Implementation**

`docs/PACKAGING.md`:

```markdown
# Memex v2.0 Packaging

Plan 4 is the final wave of v2.0: packaging, install/upgrade, docs.

## What ships in the bundle

`dist/v2.0.0/` contains:
- `plugin.json` — Claude Code plugin manifest. **Per spec §8.0 this registers exactly one skill: `memex:run`.** The 1% skill-description budget makes per-procedure top-level registration infeasible.
- `scripts/` — Python CRUD + agent harness modules
- `skills/run/SKILL.md` — the single registered skill; its body holds the routing tables for the 24 internal procedures
- `internal/` — the 24 internal procedures, organized as `internal/<category>/<name>/SKILL.md` (core, index, brain, steward, dba). NOT auto-loaded by Claude Code; reached on demand via `memex:run`'s routing tables.
- `db/` — SQL migration files (agents.sql, index.sql, brain.sql, migrations_table.sql)
- `prompts/` — Librarian, Reference Librarian, Synthesizer prompt templates
- `manifest.json` — file inventory with SHA-256 hashes
- `INSTALL.md` — install + upgrade instructions
- `README.md`, `USER_GUIDE.md`, `CHANGELOG.md`

## Build

```bash
python -m scripts.release 2.0.0
```

Produces `dist/v2.0.0/`. The `dist/v*/` body is gitignored; only
`manifest.json` is tracked.

## Install flow

1. Bundle placed in `~/.claude-code/plugins/memex/`
2. Claude Code reloads plugin
3. First Brain intent expressed via `memex:run` (e.g. "ingest this article") triggers `install.run()` which:
   - Archives v1 if `MEMEX_V1_PATH` is set
   - Creates `~/.memex/agents.db` + seeds 5 internal agents
   - Creates `~/.memex/index.db`
   - Creates `~/.memex/article.db`
   - Registers all in `~/.memex/registry.json`
4. Onboarding prompt registers the human user

## Upgrade from v0.1

v0.1 stored data under `<project>/.ai/memex.db`. v2.0 is machine-global at
`~/.memex/`. The upgrade process:

1. Set `MEMEX_V1_PATH=<path-to-old-install>` (the directory containing `.ai/`)
2. Run `install.run()` (or any Brain skill)
3. Old `.ai/` is copied to `~/.memex/legacy/v1-wiki/` as an archive
4. v2 installs fresh

v1 wiki content is NOT migrated. The user re-ingests via
`memex:brain:ingest` for entries that still matter.

## Acceptance criteria

1. `pytest tests/` 100% green across all 4 plans' tests
2. `python -m scripts.release 2.0.0` produces a valid bundle
3. `dist/v2.0.0/manifest.json` lists all files with SHA-256
4. `dist/v2.0.0/INSTALL.md` has correct instructions
5. README + CHANGELOG reflect v2.0.0
6. Bundle structure matches the §8.0 single-skill registration model:
   - `dist/v2.0.0/plugin.json` registers exactly one skill (`memex:run`)
   - `dist/v2.0.0/skills/run/SKILL.md` is present and contains routing tables for all 24 procedures
   - `dist/v2.0.0/internal/{core,index,brain,steward,dba}/` are all present
7. Git tag `v2.0.0` created (push deferred to user)
```

- [ ] **Step 4: Run tests to verify they pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/PACKAGING.md tests/test_packaging_doc.py
git commit -m "docs: PACKAGING.md for v2.0 release artifact"
```

---

## Plan 4 acceptance checklist (final)

- [ ] `pytest tests/` 100% green
- [ ] `python -m scripts.install` is idempotent and includes v1 archive step
- [ ] `python -m scripts.release 2.0.0` produces `dist/v2.0.0/`
- [ ] `dist/v2.0.0/manifest.json` checked into git
- [ ] README, USER_GUIDE, CHANGELOG, PACKAGING docs all present and accurate
- [ ] `pyproject.toml` and `plugin.json` show version 2.0.0
- [ ] `v2.0.0` git tag created locally (push is user decision)

## Release sequence (after all 4 plans complete)

1. Run `pytest tests/` — must be 100% green across all 4 plans
2. Run `python -m scripts.release 2.0.0`
3. Verify the bundle manually: install it locally, run the smoke flow
4. Commit the manifest
5. Tag `v2.0.0`
6. (User decision) Push tag + bundle to distribution channel

---

## Cross-plan summary — total v2.0 surface

Per spec §8.0, `plugin.json` registers exactly one Claude Code skill:
`memex:run`. All counts below refer to internal procedures at
`internal/<category>/<name>/SKILL.md`, reached on demand via
`memex:run`'s routing tables.

| Layer | Plan | Internal procedures | Tests |
|---|---|---|---|
| Memex Core | 1 | 10 (`memex:core:*` at `internal/core/`) | ~50 |
| Memex Index | 2 | 3 (`memex:index:*`) + 3 (`memex:steward:*`) + 3 (`memex:dba:*`) under `internal/{index,steward,dba}/` | ~60 |
| Memex Brain | 3 | 5 (`memex:brain:*` at `internal/brain/`) | ~40 |
| Packaging | 4 | (no new procedures; ships the bundle) | ~25 |
| **Total** | | **24 procedures, 1 registered skill (`memex:run`)** | **~175 tests** |

This concludes the v2.0 implementation plan series.
