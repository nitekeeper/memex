# Install hardening: preflight + CWD decoupling + security pass (v2.5.0)

**Status:** Revised 2026-05-17 (post expert-review cycle 2; 9 user decisions locked)
**Target release:** Memex v2.5.0 (minor — adds contract: routing skill performs preflight; tightens four pre-existing security holes; introduces persistent plugin-root cache)
**Supersedes:** the manual `python -m scripts.install` bootstrap contract at `README.md:32`, `USER_GUIDE.md:9`, `INSTALL.md`.
**Cross-references:** §8 of `docs/specs/2026-05-16-memex-v2-redesign-design.md` (skill visibility model).

## Motivation

Eight problems addressed:

### A — Bootstrap UX
The manual `python -m scripts.install` bootstrap has no in-product entry point. The "error pointer" fallback documented in `README.md:32` is wired in 1 of 24 procedures.

### B — Path-relative file reads
Nine call sites read bundle resources via CWD-relative `Path("db/...")` / `Path("prompts/...")`. Tests pass because pytest invokes from repo root; production invocations from a user's project CWD fail.

### C — Module discovery + sibling-package import
`python3 -m scripts.install` fails from non-plugin-root CWD with `ModuleNotFoundError`. `scripts/install.py:8` does `from db.internal_agents_seed import INTERNAL_AGENTS` — a sibling-package import that blocks any consumer plugin from importing `scripts.install.run()` directly.

### D — `python` vs `python3` + `pip` vs `python3 -m pip`
Ubuntu/Debian/WSL omit bare `python` and `pip`. Modern macOS omits `python`. Eight user-facing doc/SKILL locations use the wrong form.

### E — `$MEMEX_HOME` accepts arbitrary paths (pre-existing v2.4.x)
No validation; `MEMEX_HOME=/etc` is accepted. Auto-bootstrap amplifies blast radius: a single `y` to Step 0.2 writes Memex into the attacker-controlled location.

### F — v1 archive follows symlinks (pre-existing v2.4.x)
`shutil.copytree(v1_dir / ".ai", legacy_root)` uses default `symlinks=False`, dereferencing any symlink under `.ai/` — exfiltration of `~/.ssh/id_rsa` via `.ai/leak → ~/.ssh/id_rsa`.

### G — Internal agent profiles silently overwritten on every install (pre-existing v2.4.x)
`_seed_internal()` unconditionally rewrites `agents.db.agents.profile`. Librarian + Reference Librarian profiles drive LLM system prompts. A hostile bundle upgrade can install malicious prompts with no diff visible.

### H — Race condition under concurrent install (pre-existing v2.4.x)
No lock. Two `memex:run` against an uninitialized `~/.memex/` race. Auto-bootstrap makes parallel invocations realistic (two Claude Code windows).

## Out of scope

- Pip-installable package conversion.
- Signed bundles (the marketplace + GitHub release pipeline + filesystem isolation already verify provenance; in-Memex signature verification would duplicate work and break the "no pip install" guarantee).
- Re-embedding tooling, multi-machine sync, multi-tenant.
- Migrating v1 (`.ai/`) Wiki content into v2 Brain.
- LLM-level prompt-injection defense for the y/n consent gate. The act of invoking `memex:run` is itself a consent signal; the LLM is necessarily the channel for any in-product prompt (verified: Claude Code's Bash tool runs subprocesses with `stdin.isatty() == False` and `/dev/tty` inaccessible). Risk accepted; documented.

## Design

### Architectural choice: SKILL-led preflight + Python-deterministic consent gate + persistent plugin-root cache

Three coordination mechanisms:

1. **Persistent `~/.memex/config.json`.** Single source of truth for plugin-root location. Written on first invocation; read by every subsequent invocation. Eliminates per-invocation discovery cost and CWD-coupling issues entirely.
2. **`scripts/paths.py`.** Plugin-anchored bundle paths (`PLUGIN_ROOT`, `DB_DIR`, `PROMPTS_DIR`). Resolved via `Path(__file__).resolve().parent.parent` — independent of CWD.
3. **Python-deterministic consent gate.** LLM interprets the user's chat reply (flexibly — handles "yes"/"yeah"/"sure" as affirmative; "no"/"cancel" as negative; questions get answered, then re-prompt). LLM's interface to `install.py` is narrow: only ever pipes `y` or `n` to stdin. Python does the exact match; anything other than `y` or `n` is a defect (LLM bug). LLM remains the channel for the user's reply (Claude Code Bash subprocesses have no terminal access), but the matching is platform-agnostic Python.

### Step 0 — Preflight (skills/run/SKILL.md)

Runs BEFORE intent routing on every top-level `memex:run` invocation. ~7ms total cost (no caching layer; subagents do not re-enter `memex:run`).

#### Step 0.1 — Verify Python ≥ 3.10 is available

Run via Bash, trying interpreters in order:

```bash
for cmd in python3 python "py -3"; do
  $cmd -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)' 2>/dev/null && {
    echo "PYTHON=$cmd"; exit 0
  }
done
exit 1
```

Outcomes:
- **Exit 0** with `PYTHON=<token>` captured → continue to 0.2. Substitute the captured token unquoted wherever `python3` appears (e.g., `PYTHON=py -3` becomes `py -3 -m scripts.install` — `py` is the executable, `-3` is its arg).
- **Exit 1** → no interpreter ≥ 3.10 found. Detect platform via a single shell:

```bash
sh -c '
  s=$(uname -s 2>/dev/null) || { echo UNKNOWN; exit; }
  case "$s" in
    Linux*)
      if [ -r /proc/version ] && grep -qi microsoft /proc/version; then echo WSL
      else echo LINUX
      fi ;;
    Darwin*) echo DARWIN ;;
    MINGW*|MSYS*|CYGWIN*) echo WINDOWS ;;
    *) echo UNKNOWN ;;
  esac
'
```

Show the matching install block; `UNKNOWN` shows all three.

**Ubuntu / Debian / WSL:**
```bash
sudo apt update && sudo apt install python3 python3-pip
```

**macOS (Homebrew):**
```bash
brew install python
```
or download the installer from https://www.python.org/downloads/macos/.

**Windows:**
```powershell
winget install --scope user --id Python.Python.3
```
or download the installer from https://www.python.org/downloads/windows/.

Then output verbatim (fenced text block, do not paraphrase):

```text
Memex requires Python 3.10 or newer.

Install it using the matching block shown above, then re-run `memex:run`.
```

End the turn. No further tool calls, no summarization, no offered alternatives.

#### Step 0.2 — Verify Memex is initialized

Resolve `<RESOLVED_HOME>`: `$MEMEX_HOME` if set (validated per §Security E), else `~/.memex/` (default; validated per §Security E to reject symlinked `~/.memex/`).

Resolve `<RESOLVED_PLUGIN_ROOT>` via the persistent-config cascade:

1. **Read `~/.memex/config.json`** (if `~/.memex/` exists). If it contains a valid `plugin_root` field whose target exists AND whose `scripts/install.py` is a regular file AND whose `plugin.json` contains `"name": "memex"` → use it.
2. **`$PWD` probe.** If `$PWD/scripts/install.py` exists AND `$PWD/plugin.json` contains `"name": "memex"` → use `$PWD`.
3. **`$PATH` probe.** Claude Code prepends the active plugin's `bin/` directory to `$PATH`:
   ```bash
   # Use ; on Windows, : on POSIX. Determine from the platform token captured in Step 0.1.
   matches=$(echo "$PATH" | tr "${SEP}" '\n' | grep -E '/memex/[^/]+/bin$' | sed 's:/bin$::' | sort -u)
   count=$(echo "$matches" | grep -c .)
   ```
   For each candidate, verify `<path>/scripts/install.py` exists AND `<path>/plugin.json` contains `"name": "memex"`. If exactly 1 candidate passes validation → use it.
4. **Ask the user.** If 0 or >1 from step 3, output verbatim:
   ```text
   I couldn't auto-locate the Memex plugin directory.
   What is the absolute path to your install (the directory containing scripts/install.py)?
   ```
   End the turn; use the user's reply. Validate `<reply>/scripts/install.py` exists AND `<reply>/plugin.json` is a Memex manifest; if not, re-ask once with the failure reason, then STOP.

After successful resolution, **write the resolved path back to `~/.memex/config.json`** (creating `~/.memex/` first if needed):

```json
{
  "plugin_root": "/absolute/path/to/plugin"
}
```

Subsequent invocations read directly from the file (step 1) and skip discovery.

Then check that all five paths exist:
- `<RESOLVED_HOME>/`
- `<RESOLVED_HOME>/registry.json`
- `<RESOLVED_HOME>/agents.db`
- `<RESOLVED_HOME>/index.db`
- `<RESOLVED_HOME>/article.db`

If all exist → proceed to routing.

If ANY missing, build the missing list with EXACTLY these line shapes:
- If `<RESOLVED_HOME>/` does not exist: emit one line, exactly: `  - <RESOLVED_HOME>/ (directory does not exist)`. Do NOT add per-file lines in this case.
- Else: one line per missing file, exactly: `  - <absolute path>`.

Check whether `~/.ai/` exists:
```bash
[ -d "$HOME/.ai" ] && echo HAS_V1 || echo NO_V1
```

If `HAS_V1`, emit **block A** (with v1 bullet); else emit **block B** (without v1 bullet). Both blocks below are verbatim fenced text — substitute `<RESOLVED_HOME>` and `<missing list>` with real values, do not paraphrase any line.

**Block A (v1 present):**
```text
Memex isn't bootstrapped at <RESOLVED_HOME>. Missing:
<missing list>

I can bootstrap Memex now. This will:
  - create <RESOLVED_HOME>/ and subdirectories raw/, backups/, audits/, templates/
  - create any missing databases (agents.db, index.db, article.db) and registry.json; existing files are not modified
  - install the 5 internal Memex agents (Librarian, Reference Librarian, Archivist, DBA, Data Steward) from the verified plugin bundle
  - archive your existing ~/.ai/ (Memex v1 install) to <RESOLVED_HOME>/legacy/v1-wiki/. Symlinks under .ai/ are preserved as symlinks (not dereferenced). No data is deleted or auto-migrated.

Proceed? (y/n)
```

**Block B (no v1):**
```text
Memex isn't bootstrapped at <RESOLVED_HOME>. Missing:
<missing list>

I can bootstrap Memex now. This will:
  - create <RESOLVED_HOME>/ and subdirectories raw/, backups/, audits/, templates/
  - create any missing databases (agents.db, index.db, article.db) and registry.json; existing files are not modified
  - install the 5 internal Memex agents (Librarian, Reference Librarian, Archivist, DBA, Data Steward) from the verified plugin bundle

Proceed? (y/n)
```

End the turn. Wait for the user's reply.

**Reply interpretation** (LLM-side, flexible — but only `y` or `n` is forwarded to Python):
- **Affirmative** (`yes`, `y`, `yeah`, `yep`, `sure`, `ok`, `okay`, `go`, `go ahead`, `do it`, `proceed`, `please`): forward `y` to install.py.
- **Negative** (`no`, `n`, `nope`, `not now`, `later`, `wait`, `stop`, `cancel`, `skip`): forward `n` to install.py.
- **Ambiguous or question**: answer concisely using only information from this Step 0 block (do not invent capabilities). Then re-display the matching block (A or B). End the turn.
- After 3 ambiguous cycles, forward `n` and tell the user "Repeated ambiguous replies; treating as decline. Re-invoke `memex:run` to retry."

**On `n`** — install.py exits 1; LLM displays:
```text
Memex was not bootstrapped. Memex cannot run without ~/.memex/.

To proceed later, do one of:
  - re-invoke memex:run and answer y
  - bootstrap manually:
      PYTHONPATH="<RESOLVED_PLUGIN_ROOT>" python3 -m scripts.install
  - point Memex at a different location with MEMEX_HOME=/abs/path before re-invoking
```

End the turn. No routing. No summary.

**On `y`**:

1. Output: `Bootstrapping Memex…`
2. Run via Bash (single call, no `cd` needed because plugin-root is on PYTHONPATH):
   ```bash
   echo "y" | PYTHONPATH="<RESOLVED_PLUGIN_ROOT>" MEMEX_HOME="<RESOLVED_HOME>" python3 -m scripts.install 2>/tmp/memex-install-stderr.log
   echo "EXIT=$?"
   tail -40 /tmp/memex-install-stderr.log
   ```
   (Substitute captured Python interpreter token for `python3`. Quote both env-var values to survive spaces. The `echo "y"` provides the consent token to install.py's stdin.)
3. On `EXIT=0` AND all five paths now exist:
   - Output: `Bootstrapped Memex at <RESOLVED_HOME>.`
   - Proceed to routing.
4. On failure, output verbatim:
   ```text
   Memex bootstrap failed.

   Command:        python3 -m scripts.install
   Plugin root:    <RESOLVED_PLUGIN_ROOT>
   Memex home:     <RESOLVED_HOME>
   Exit code:      <code>
   Still missing:
     - <each absolute path>

   Stderr (last 40 lines):
   <stderr tail>

   Next steps:
     1. Verify <RESOLVED_PLUGIN_ROOT>/scripts/install.py exists.
     2. Confirm <RESOLVED_HOME> is writable.
     3. If both check out, file an issue at https://github.com/nitekeeper/memex/issues with this report.
   ```
   End the turn.

### `~/.memex/config.json` schema

```json
{
  "plugin_root": "/absolute/path/to/plugin"
}
```

Single field for v2.5.0. JSON format leaves room for future settings without a redesign. Validation on read: `plugin_root` must point to a directory containing `scripts/install.py` and `plugin.json` with `"name": "memex"`. If stale, the cascade re-runs and rewrites the file.

### Plugin-anchored file paths (`scripts/paths.py`)

```python
"""Plugin-anchored filesystem constants.

Resource files (SQL migrations, prompt templates) live inside the
installed plugin bundle and must be resolved relative to this file,
not CWD. Stable API: PLUGIN_ROOT, DB_DIR, PROMPTS_DIR.
"""

from __future__ import annotations

from pathlib import Path

# scripts/paths.py → scripts/ → <plugin_root>
# .resolve() follows symlinks intentionally (legitimate dev pattern:
# ~/.claude/plugins/memex symlinked to a working tree).
PLUGIN_ROOT: Path = Path(__file__).resolve().parent.parent

DB_DIR: Path = PLUGIN_ROOT / "db"
PROMPTS_DIR: Path = PLUGIN_ROOT / "prompts"

# Defensive: fail at import time on broken bundle layouts.
if not (DB_DIR / "migrations_table.sql").is_file():
    raise ImportError(
        f"Memex bundle layout broken: {DB_DIR}/migrations_table.sql not found. "
        f"PLUGIN_ROOT resolved to {PLUGIN_ROOT}. See docs/PACKAGING.md."
    )
```

Nine call sites migrated from `Path("db/X")` / `Path("prompts/X")` to `DB_DIR / "X"` / `PROMPTS_DIR / "X"`:

| File | Line(s) | Constant |
|---|---|---|
| `scripts/install.py` | 29 | `DB_DIR / "agents.sql"` |
| `scripts/install.py` | 45, 62 | `DB_DIR / "migrations_table.sql"` |
| `scripts/install.py` | 46 | `DB_DIR / "index.sql"` |
| `scripts/install.py` | 63 | `DB_DIR / "brain.sql"` |
| `scripts/stores.py` | 17 | `DB_DIR / "migrations_table.sql"` |
| `scripts/brain.py` | 289 | `PROMPTS_DIR / "synthesizer.md"` |
| `scripts/agents/librarian.py` | 73 | `PROMPTS_DIR / "librarian.md"` |
| `scripts/agents/reference_librarian.py` | 71 | `PROMPTS_DIR / "reference_librarian.md"` |

### Relocate `db/internal_agents_seed.py` → `scripts/_internal_agents_seed.py`

`scripts/install.py:8`'s `from db.internal_agents_seed import INTERNAL_AGENTS` is the only sibling-package import. Move the file under `scripts/` (leading underscore for internal-API), update the import, delete the old location.

Add `INTERNAL_AGENTS_HASH` constant for drift detection (§G).

### Python-layer defense (`scripts/db.py`)

```python
class MemexHomeInvalidError(ValueError):
    """$MEMEX_HOME (or default ~/.memex/) failed validation."""


class MemexNotInitializedError(RuntimeError):
    """Memex Python invoked before ~/.memex/ is bootstrapped."""


def require_bootstrap() -> None:
    """Precondition for functions that write under memex_home().

    Resolves home, validates, checks for registry.json. Raises
    MemexNotInitializedError with operator guidance if absent.
    """
    home = memex_home()
    if not (home / "registry.json").exists():
        from scripts.paths import PLUGIN_ROOT
        raise MemexNotInitializedError(
            f"Memex is not bootstrapped at {home}.\n"
            f"To bootstrap:\n"
            f"  PYTHONPATH={PLUGIN_ROOT} python3 -m scripts.install\n"
            f"Or, in Claude Code, invoke memex:run and accept the prompt."
        )
```

Called at the top of every public function that **writes under `memex_home()`** (no explicit `db_path` parameter):

- `scripts.brain.*` — all 9 public functions
- `scripts.stores.{create_store, migrate, query, insert, update, delete}`
- `scripts.embeddings.*` — all public encode entries
- `scripts.agents.archivist.archive` — writes to `memex_home() / "raw"`

Explicitly **NOT** called from (these take explicit `db_path` and are bootstrap-state-independent):

- `scripts.roles.*` (all)
- `scripts.agents.{create_agent, get_agent, list_agents, list_by_role, update_agent, delete_agent}`
- `scripts.agents.dba.*` — `db_path` param
- `scripts.agents.data_steward.*` — `index_db` / `db_path` params
- `scripts.registry.*` — JSON metadata, well-defined empty-state semantics

Also NOT called from:
- `scripts.install.run()` — IS the bootstrap
- `scripts.upgrade_from_v1.archive_v1()` — called pre-bootstrap by install (has its own validation)
- `scripts.agents.librarian.*` / `scripts.agents.reference_librarian.*` — invoked from inside guarded `scripts.brain.*`

### Security

#### E — `$MEMEX_HOME` + `~/.memex/` validation

```python
def memex_home() -> Path:
    """Resolve Memex home, with validation in both branches."""
    explicit = os.environ.get("MEMEX_HOME")
    if explicit:
        resolved = Path(explicit).expanduser()
        if resolved.exists() and resolved.is_symlink():
            # Check is_symlink() BEFORE resolve() — resolve() collapses symlinks.
            if os.environ.get("MEMEX_HOME_ALLOW_UNUSUAL") != "1":
                raise MemexHomeInvalidError(
                    f"$MEMEX_HOME ({resolved}) is a symlink; refusing to write through it."
                )
        resolved = resolved.resolve()
        if os.environ.get("MEMEX_HOME_ALLOW_UNUSUAL") != "1":
            try:
                resolved.relative_to(Path.home().resolve())
            except ValueError:
                raise MemexHomeInvalidError(
                    f"$MEMEX_HOME ({resolved}) is not under your home directory "
                    f"({Path.home().resolve()}). Set MEMEX_HOME_ALLOW_UNUSUAL=1 to override."
                )
        return resolved

    # Default branch: ~/.memex/ — also validate not a symlink.
    home = Path.home() / MEMEX_DIR_NAME
    if home.exists() and home.is_symlink():
        if os.environ.get("MEMEX_HOME_ALLOW_UNUSUAL") != "1":
            raise MemexHomeInvalidError(
                f"~/.memex/ ({home}) is a symlink; refusing to write through it. "
                f"Set MEMEX_HOME_ALLOW_UNUSUAL=1 to override."
            )
    return home
```

Tested with: paths outside `$HOME`, root `/`, symlinked `~/.memex/`, symlinked `$MEMEX_HOME`, valid paths under home.

#### F — v1 archive symlink protection

Rewrite `scripts/upgrade_from_v1.detect_v1_install()`:

```python
def detect_v1_install() -> Path | None:
    explicit = os.environ.get("MEMEX_V1_PATH")
    if not explicit:
        return None
    v1_root = Path(explicit).expanduser()
    # Check is_symlink BEFORE resolve.
    if v1_root.is_symlink():
        raise ValueError(f"$MEMEX_V1_PATH is a symlink ({v1_root}); refusing to archive.")
    v1_root = v1_root.resolve()
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

Rewrite `archive_v1()`:
- Validate `<home>/legacy/` and `<home>/legacy/v1-wiki/` are not symlinks.
- `shutil.copytree(symlinks=True, ignore_dangling_symlinks=True)` — symlinks preserved as links.

#### G — Internal agent profile hash-pinning

`scripts/_internal_agents_seed.py` exposes `INTERNAL_AGENTS_HASH = sha256(json.dumps(sorted_INTERNAL_AGENTS, ...))` computed at import time (sort `INTERNAL_AGENTS` by `agent_id` before serializing for order-insensitivity).

`_seed_internal()`:
- Creates `agents.db.meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)` if missing.
- Reads stored `seed_hash`. If matches bundle → no-op.
- If differs (drift) → print one line to stderr:
  ```
  Updating internal agent profiles (bundle hash <new[:8]> != stored hash <old[:8]>). If you have manually edited any profiles, back them up before re-running install.
  ```
  Then update + write new hash.
- If stored hash is missing (first install or pre-v2.5.0 upgrade) → silent seed + write hash.

The "verified" label in the Step 0.2 prompt accurately describes state on disk — bundle is verified by the marketplace + GitHub release pipeline before reaching the user. Memex hash-pinning is drift detection, not signature verification.

#### H — Concurrent install lock

```python
class InstallLockBusyError(RuntimeError): ...

def _acquire_lock(lock_path: Path):
    """Symlink-safe exclusive file lock. Caller closes the returned handle."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # O_NOFOLLOW prevents symlink-target-truncation attacks.
    import os, errno
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(lock_path), flags, 0o600)
    except OSError as e:
        if e.errno == errno.ELOOP:
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
            if e.errno in (errno.EACCES, errno.EDEADLK):
                fh.close()
                raise InstallLockBusyError(
                    f"Another Memex install is already running (lock at {lock_path})."
                )
            fh.close()
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
```

`scripts/install.run()` acquires the lock immediately after `home.mkdir(exist_ok=True)`. Released on exit (try/finally). Tested with deterministic synchronization: a barrier ensures both worker processes reach `install.run()` simultaneously; assert one succeeds, one raises `InstallLockBusyError`.

### Documentation: `python` → `python3` + `pip` → `python3 -m pip`

User-facing locations:

| File | Lines | Change |
|---|---|---|
| `README.md` | 30, 32, 44, 53, 61 | Plugin path correction (`~/.claude/plugins/cache/<marketplace>/memex/<version>/`); Step 4 rewrite (auto-bootstrap); `pip install` → `python3 -m pip install` (line 44); `python` → `python3` (53, 61) |
| `USER_GUIDE.md` | 9, 188, 196, 206 | Step 3 rewrite (auto-bootstrap); `python` → `python3` |
| `docs/CORE.md` | 37 | `python` → `python3` + Step 0.2 cross-reference |
| `docs/PACKAGING.md` | 48, 110 | `python` → `python3` |
| `scripts/release.py` | INSTALL.md template body | `python` → `python3` everywhere; plugin path correction |
| `internal/brain/ingest/SKILL.md` | 114, 115 | Delete 114; reword 115 to reference `memex:steward:audit-store` |

**Not touched:** `CHANGELOG.md` historical entries, frozen `docs/plans/*` / `docs/specs/2026-05-16-*` / `docs/specs/2026-05-17-embedding-unavailable-*` / `docs/superpowers/plans/*`, `.github/workflows/*.yml` (CI uses `actions/setup-python`).

### `.gitattributes`

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

Followed by `git add --renormalize .` (after `git stash` if working tree has unrelated unstaged changes).

### Updated `~/.memex/` layout reference

```
~/.memex/
├── agents.db
├── index.db
├── article.db
├── registry.json
├── config.json          (new in v2.5.0 — plugin-root cache)
├── .install.lock        (new in v2.5.0 — flock target)
├── raw/
├── backups/
├── audits/
├── templates/
└── legacy/              (only if v1 install was archived)
```

## Testing

### Updated `tests/conftest.py`

```python
@pytest.fixture
def tmp_memex_home(monkeypatch, tmp_path):
    """Isolated ~/.memex/ root for tests.

    Sets MEMEX_HOME_ALLOW_UNUSUAL=1 because tmp_path is under /tmp,
    which fails the new $MEMEX_HOME validation introduced in v2.5.0.
    """
    home = tmp_path / "memex_home"
    home.mkdir()
    monkeypatch.setenv("MEMEX_HOME", str(home))
    monkeypatch.setenv("MEMEX_HOME_ALLOW_UNUSUAL", "1")
    return home


@pytest.fixture
def bootstrapped_marker(tmp_memex_home):
    """Lightweight: write registry.json so require_bootstrap() passes.
    Use for tests that need to satisfy the guard but don't need a real install."""
    (tmp_memex_home / "registry.json").write_text("{}")
    return tmp_memex_home


@pytest.fixture
def bootstrapped_home(tmp_memex_home):
    """Full install. Use for tests that exercise post-bootstrap behavior."""
    from scripts import install
    install.run()
    return tmp_memex_home
```

### New test files

- `tests/test_paths.py` — `PLUGIN_ROOT`, `DB_DIR`, `PROMPTS_DIR` resolve; subprocess-from-tmp test for CWD independence.
- `tests/test_install_alt_cwd.py` — install runs from arbitrary CWD; shadowing `tmp_path/db/` is ignored.
- `tests/test_bootstrap_guard.py` — `MemexNotInitializedError` raises on empty home; mock-bomb tests for guard exclusions (registry, install, upgrade_from_v1, roles, agents CRUD, dba, data_steward).
- `tests/test_modules_import_clean.py` — every `scripts.*` module imports cleanly with `MEMEX_HOME` unset.
- `tests/test_skill_run_preflight.py` — Step 0 markers present in SKILL.md (scoped via `_step_0_region()` splitter); xfail(strict=True) until T-SKILL turns them green.
- `tests/test_skill_preflight_smoke.py` — extracts SKILL bash snippets and executes them.
- `tests/test_config_json.py` — read/write/validation of `~/.memex/config.json`.
- `tests/test_security_home_validation.py` — `$MEMEX_HOME` validation (paths outside home, root, symlinks both branches).
- `tests/test_security_v1_symlink.py` — v1 archive preserves symlinks; rejects symlinked `$MEMEX_V1_PATH` / `.ai`.
- `tests/test_security_profile_hash.py` — seed-hash matches/mismatches, no-op on match, warning on mismatch.
- `tests/test_security_install_lock.py` — deterministic race test: `multiprocessing.Barrier` ensures contention; assert exactly one process raises `InstallLockBusyError`.
- `tests/test_install_lock_no_follow.py` — pre-stage `<home>/.install.lock` as a symlink; assert install raises `InstallLockBusyError` (or similar) rather than truncating the symlink target.

### Migration assertions: AST not strings

Reusable helper:
```python
def _ast_has_relative_path_literal(src: str, prefix: str) -> bool:
    """True if source has any Call(..."{prefix}..." as first string-literal arg)."""
    import ast
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value.startswith(prefix):
                    return True
    return False
```

Used in `tests/test_paths.py` to verify each migrated module has no `Path("db/...")` or `Path("prompts/...")` literals. Robust to comments, quote-style, f-strings.

### Existing test migration via script

`scripts/_migrate_v25_tests.py` (one-shot migration tool, deleted after Wave 1):

```python
"""Mechanical migration of existing test_*.py files to v2.5.0 fixtures + path constants.

Scans each tests/test_*.py and rewrites:
  - `tmp_memex_home` fixture argument → `bootstrapped_marker` if the test calls guarded
    functions; → `bootstrapped_home` if the test reads seeded DB content.
  - `Path("db/...")` / `Path("prompts/...")` literals → DB_DIR / PROMPTS_DIR usage.

Emits a unified diff for review before applying with --apply.
"""
```

Reviewer-counted scope: ~138 test methods across ~23 files. Mechanical migration is deterministic; partial misses are caught by the post-migration `pytest tests/` run.

## v2.5.0 — 2026-05-17

### Added

- **Auto-bootstrap on `memex:run` (Step 0.2).** Detects missing/incomplete `~/.memex/`, prompts strictly `(y/n)`, runs `scripts.install` via Python stdin (deterministic match) on `y`.
- **Python 3.10+ preflight (Step 0.1).** `python3 -c 'sys.version_info[:2] >= (3, 10)'`; fallback to `python` then `py -3`; OS-specific install instructions on miss.
- **`scripts/paths.py`.** Plugin-anchored `PLUGIN_ROOT`, `DB_DIR`, `PROMPTS_DIR`. Import-time bundle integrity check.
- **`~/.memex/config.json`.** Persistent plugin-root cache; written on first invocation, read by all subsequent ones. Eliminates per-invocation discovery.
- **`scripts.db.MemexNotInitializedError` + `require_bootstrap()`.** Typed precondition for direct Python imports.
- **`MemexHomeInvalidError` + `$MEMEX_HOME` / `~/.memex/` validation.** Rejects out-of-home paths and symlinked home unless `MEMEX_HOME_ALLOW_UNUSUAL=1`.
- **v1-archive symlink protection.** `copytree(symlinks=True)`; `$MEMEX_V1_PATH` / `.ai` validation.
- **Internal agent profile hash-pinning.** Drift detection via `agents.db.meta.seed_hash`.
- **Concurrent install lock.** `os.O_NOFOLLOW` + `flock`/`msvcrt.locking`; new `InstallLockBusyError`.
- **`.gitattributes`** enforcing LF line endings.

### Changed

- **Bundle reads CWD-independent.** 9 sites migrated to `DB_DIR` / `PROMPTS_DIR`.
- **`db/internal_agents_seed.py` relocated to `scripts/_internal_agents_seed.py`.** Eliminates sibling-package import.
- **All user-facing docs say `python3` and `python3 -m pip`.**
- **Brain `ingest`'s manual-install error pointer removed; `Unknown store: article` reworded to reference `memex:steward:audit-store`.**
- **Plugin install path docs corrected** from `~/.claude-code/plugins/` to `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`.

### Migration

Existing v2.4.1 installs continue to work without action. The first `memex:run` after upgrade re-runs preflight; on a healthy install it passes silently and writes `~/.memex/config.json` for future invocations.

**Degraded install** (deleted DB files, partial install, stale `MEMEX_HOME`): first `memex:run` after upgrade prompts `(y/n)` to bootstrap. Idempotent.

**`$MEMEX_HOME` outside `$HOME`** (rare): v2.5.0 raises `MemexHomeInvalidError`. Set `MEMEX_HOME_ALLOW_UNUSUAL=1` to retain v2.4.x behavior.

**Manually-edited internal agent profiles** (very rare): on upgrade, `_seed_internal()` detects hash drift and prints a stderr warning before overwriting. Back up before running install if you've customized profiles.

## Versioning + release sequencing

**v2.5.0 (minor).** SKILL contract change + `$MEMEX_HOME` validation (rejects previously-accepted inputs).

**Release flow (one PR):**
1. PR opened against `main`.
2. Local CI mirror: `ruff check`, `ruff format --check`, `bandit`, `pytest tests/`.
3. After merge: `python3 -m scripts.release 2.5.0` builds `dist/v2.5.0/`.
4. Tag + push triggers `release.yml`; agora's `plugin-update.yml` opens marketplace auto-update PR.

## Decision log (locked, 9 user decisions + accepted reviewer guidance)

### User decisions

1. **Plugin-root resolution:** persistent `~/.memex/config.json` (JSON), written on first invocation via `$PWD` → `$PATH` → ask-user cascade. Subsequent invocations read directly. Install via `PYTHONPATH="$PLUGIN_ROOT" python3 -m scripts.install` (no `cd`, single call).
2. **MEMEX_PREFLIGHT_OK env var:** dropped. Step 0 reruns every top-level `memex:run` (~7ms); cheap enough that the optimization isn't worth the complexity. Subagents don't actually re-enter `memex:run`.
3. **`dba.py` / `data_steward.py` bootstrap guards:** dropped. Both take explicit `db_path` parameters and are bootstrap-state-independent (same principle as the already-excluded `roles.*` / `agents.{C,R,U,D}_agent`).
4. **Test audit:** mechanical Python migration script (`scripts/_migrate_v25_tests.py`).
5. **v1-archive bullet:** two complete fenced blocks (block A with v1, block B without). Probe via `[ -d "$HOME/.ai" ] && echo HAS_V1 || echo NO_V1`. Same pattern as Step 0.1 platform-install blocks.
6. **Profile-overwrite warning:** moved out of the Step 0.2 user prompt (wrong audience: first-time users have no edits to overwrite). Survives only as the §G stderr line that fires on actual hash mismatch (upgrade case).
7. **"Verified" wording:** kept. The bundle IS verified — by the marketplace + GitHub release pipeline + filesystem isolation — before reaching Memex. Hash-pinning is drift detection, not signature verification (correctly scoped).
8. **Consent gate:** LLM interprets the user's reply flexibly (accepts yes/y/sure/ok/go ahead as affirmative; no/cancel as negative; answers questions then re-prompts). LLM's interface to `install.py` is narrow: pipe only `y` or `n` to stdin. Python does exact match. LLM remains the channel; Claude Code Bash tool has no terminal access (verified). Prompt-injection risk accepted per earlier decision.
9. **`memex_home()` default branch validation:** rejects symlinked `~/.memex/` unless `MEMEX_HOME_ALLOW_UNUSUAL=1`. Symmetric with `$MEMEX_HOME` validation.

### Accepted reviewer guidance (mechanical fixes)

- `tmp_memex_home` fixture sets `MEMEX_HOME_ALLOW_UNUSUAL=1` (avoids breaking ~140 tests under §E validation).
- `archivist.archive(payload, filename)` is the actual signature — guards reference the correct function.
- `is_symlink()` checks happen BEFORE `.resolve()` (resolve collapses symlinks, making post-resolve checks no-ops).
- Lock file opens with `os.O_NOFOLLOW` to prevent symlink-target-truncation.
- `$PATH` plugin-root resolver validates `plugin.json` contains `"name": "memex"` (closes the RCE primitive from arbitrary `$PATH` prepends).
- Single-token platform detection (`sh -c` returning `LINUX`/`WSL`/`DARWIN`/`WINDOWS`/`UNKNOWN`).
- AST-based migration assertions (robust to formatting, f-strings, comments).
- `xfail(strict=True)` for pre-merged SKILL-presence tests (flips to passing in the SKILL.md insertion commit).
- Stderr capture in install: redirect to `/tmp/memex-install-stderr.log` so the LLM can tail it on failure.
- `multiprocessing.Barrier` in concurrent-install test (deterministic race exercise, not "ok,ok also acceptable").
- Plugin install path corrected to `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`.
- `_internal_agents_seed.py` sorts `INTERNAL_AGENTS` by `agent_id` before hashing (order-insensitive).
