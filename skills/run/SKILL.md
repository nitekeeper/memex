---
description: Use to invoke any Memex v2.0 operation. Routes user-facing intents (ingest, ask, capture, lint, synthesize) and agent-facing CRUD primitives to the right internal procedure. The only Claude-Code-visible Memex skill — internal procedures (24 total) are read on demand to stay under the 1% skill-description budget.
---

Memex v2 is a personal knowledge runtime and shared memory plane for the agent fleet. This skill is the public entry point — it maps natural-language intent (for users) or agent-named operations (for AI consumers) to the right internal procedure under `internal/<category>/<name>/SKILL.md`.

When this skill references `internal/<category>/<name>/SKILL.md` below, the agent should: (1) Read that file via the Read tool, (2) follow the procedure inline.

For the full v2.0 architecture: see the per-layer acceptance docs (`docs/CORE.md`, `docs/INDEX.md`, `docs/BRAIN.md`, `docs/PACKAGING.md`); the originating design body is recoverable via git history pre-2026-05-26 or `memex:run ask` (untracked in memex#22).

## Step 0 — Preflight

Step 0 runs BEFORE intent routing on every top-level `memex:run` invocation. It verifies (0.1) a usable Python interpreter, then (0.2) that `~/.memex/` is bootstrapped. If either is missing, Step 0 ends the turn — no routing, no fallback. The install-hardening design rationale is recoverable via git history pre-2026-05-26 or `memex:run ask` (untracked in memex#22).

### Step 0.1 — Verify Python ≥ 3.10 is available

Run via Bash, trying interpreters in order:

```bash
for cmd in python3 python "py -3"; do
  $cmd -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)' 2>/dev/null && {
    echo "PYTHON=$cmd"; exit 0
  }
done
exit 1
```

- **Exit 0** → capture `PYTHON=<token>`. Substitute the captured token unquoted wherever `python3` appears in Step 0.2 (e.g., `PYTHON=py -3` becomes `py -3 -m scripts.install` — `py` is the executable, `-3` is its arg).
- **Exit 1** → no interpreter ≥ 3.10. Detect platform with a single shell:

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

Show the matching install block (`UNKNOWN` → show all three).

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

Then output verbatim (do not paraphrase):

```text
Memex requires Python 3.10 or newer.

Install it using the matching block shown above, then re-run `memex:run`.
```

End the turn. No further tool calls, no summarization.

### Step 0.2 — Verify Memex is initialized

Resolve `<RESOLVED_HOME>`: `$MEMEX_HOME` if set, else `~/.memex/`. (The Python layer validates this is non-symlink and under `$HOME` unless `MEMEX_HOME_ALLOW_UNUSUAL=1` is set.)

Resolve `<RESOLVED_PLUGIN_ROOT>` via the persistent-config cascade:

1. **Read `~/.memex/config.json`.** If it contains a valid `plugin_root` field whose target exists AND whose `scripts/install.py` is a regular file AND whose `.claude-plugin/plugin.json` contains `"name": "memex"` → use it.
2. **`$PWD` probe.** If `$PWD/scripts/install.py` exists AND `$PWD/.claude-plugin/plugin.json` contains `"name": "memex"` → use `$PWD`.
3. **`$PATH` probe.** Claude Code prepends the active plugin's `bin/` to `$PATH`:
   ```bash
   # SEP is ':' on POSIX, ';' on Windows — pick from the platform token captured in Step 0.1.
   matches=$(echo "$PATH" | tr "${SEP}" '\n' | grep -E '/memex/[^/]+/bin$' | sed 's:/bin$::' | sort -u)
   count=$(echo "$matches" | grep -c .)
   ```
   For each candidate, verify `<path>/scripts/install.py` exists AND `<path>/.claude-plugin/plugin.json` contains `"name": "memex"`. If exactly 1 candidate passes validation → use it.
4. **Ask the user.** If 0 or >1 from step 3, output verbatim:
   ```text
   I couldn't auto-locate the Memex plugin directory.
   What is the absolute path to your install (the directory containing scripts/install.py)?
   ```
   End the turn; use the user's reply. Validate; re-ask once if invalid, then STOP.

After successful resolution, write the resolved path back to `~/.memex/config.json` (creating `~/.memex/` first if needed):

```json
{
  "plugin_root": "/absolute/path/to/plugin"
}
```

Subsequent invocations read directly from this file (step 1) and skip discovery.

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

Check whether a v1 install is present:
```bash
[ -d "$HOME/.ai" ] && echo HAS_V1 || echo NO_V1
```

If `HAS_V1`, emit **Block A** (with v1 bullet); else emit **Block B** (without v1 bullet). Both blocks are verbatim — substitute `<RESOLVED_HOME>` and `<missing list>` with real values; do not paraphrase any line.

**Block A (v1 install present):**
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
- **Affirmative** (`yes`, `y`, `yeah`, `yep`, `sure`, `ok`, `okay`, `go`, `go ahead`, `do it`, `proceed`, `please`): forward `y`.
- **Negative** (`no`, `n`, `nope`, `not now`, `later`, `wait`, `stop`, `cancel`, `skip`): forward `n`.
- **Ambiguous or question**: answer concisely using only information from this Step 0 block (do not invent capabilities). Then re-display the matching block (A or B). End the turn.
- After 3 ambiguous cycles, forward `n` and tell the user "Repeated ambiguous replies; treating as decline. Re-invoke `memex:run` to retry."

**On `n`** — install.py exits 1; display:
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
2. Run via Bash (single call — no `cd` needed because plugin-root is on PYTHONPATH):
   ```bash
   echo "y" | PYTHONPATH="<RESOLVED_PLUGIN_ROOT>" MEMEX_HOME="<RESOLVED_HOME>" python3 -m scripts.install 2>/tmp/memex-install-stderr.log
   echo "EXIT=$?"
   tail -40 /tmp/memex-install-stderr.log
   ```
   (Substitute captured Python interpreter token for `python3`. Quote both env-var values to survive spaces. The `echo "y"` provides the consent token to install.py's stdin — Python does the strict `y`/`n` match.)
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

## v2 Brain user-facing intent routing

Brain operations are the daily-use second-brain verbs. The user expresses one of these intents in natural language — there is no `memex:brain:*` top-level skill because the 1% budget would be exceeded; instead, this skill reads the matching procedure and follows it.

| User intent | Internal procedure |
|---|---|
| Ingest an article / save a URL / capture a clipped page | `internal/brain/ingest/SKILL.md` |
| Ask a question / search / recall | `internal/brain/ask/SKILL.md` |
| Capture a note / jot a thought / log an observation | `internal/brain/capture/SKILL.md` |
| Run a Brain health check / lint Brain / audit my knowledge | `internal/brain/lint/SKILL.md` |
| Synthesize across documents / find the through-line / summarize this topic | `internal/brain/synthesize/SKILL.md` |

## v2 Core CRUD routing (agent-facing)

Memex Core is the CRUD substrate that agents — not the human user — invoke directly. These 10 procedures live at `internal/core/<name>/SKILL.md` and are reachable only via this routing table.

| Agent intent | Internal procedure |
|---|---|
| Provision a new SQLite store from a directory of `.sql` migrations | `internal/core/create-store/SKILL.md` |
| Apply additional migrations to an existing registered store | `internal/core/migrate/SKILL.md` |
| Read rows from a registered store (SELECT) | `internal/core/query/SKILL.md` |
| Insert a row into a non-document table | `internal/core/insert/SKILL.md` |
| Update a row by integer `id` PK | `internal/core/update/SKILL.md` |
| Delete a row by integer `id` PK | `internal/core/delete/SKILL.md` |
| Enumerate every registered store | `internal/core/list-stores/SKILL.md` |
| Register a new role in `agents.db.roles` | `internal/core/register-role/SKILL.md` |
| Register a new agent in `agents.db.agents` | `internal/core/register-agent/SKILL.md` |
| Fetch an agent's full profile by id | `internal/core/get-agent/SKILL.md` |

The Python implementations live under `scripts/` (`db.py`, `roles.py`, `agents/`, `registry.py`, `stores.py`, `install.py`). Each SKILL.md is a short documentation wrapper; the agent reads it for the API contract, then calls the implementation.

## v2 Index, Steward, and DBA routing (agent-facing)

Memex maintains a federated Index (`~/.memex/index.db`) plus five internal agents: Librarian, Reference Librarian, Archivist, DBA, Data Steward. Their procedures live at `internal/<category>/<name>/SKILL.md`. Like Core, these are agent-only — the human typically reaches them through Brain rather than directly.

| Agent intent | Internal procedure |
|---|---|
| Submit a document for centralized indexing (mandatory write path; archives raw, classifies, embeds, persists) | `internal/index/write/SKILL.md` |
| Ask a natural-language question against the federated Index; returns ranked, citation-ready results | `internal/index/search/SKILL.md` |
| Archive a raw payload to `~/.memex/raw/` without indexing (rare; usually called internally by index:write) | `internal/index/archive/SKILL.md` |
| Run a full integrity audit across every store + the Index; write a structured report | `internal/steward/audit/SKILL.md` |
| Audit a single registered store (reverse orphans, schema drift) | `internal/steward/audit-store/SKILL.md` |
| Authorized resolution of a flagged orphan (delete-index / repair / reindex / note) | `internal/steward/reconcile-orphan/SKILL.md` |
| Run a WAL checkpoint on a registered store | `internal/dba/checkpoint/SKILL.md` |
| Run `PRAGMA integrity_check` on a registered store | `internal/dba/integrity-check/SKILL.md` |
| Run `VACUUM` on a registered store (maintenance) | `internal/dba/vacuum/SKILL.md` |
| Backfill embeddings (encode rows where `embedding IS NULL`) | `internal/embed/backfill/SKILL.md` |
| Re-embed all rows after a provider/model change | `internal/embed/reembed/SKILL.md` |

The Librarian and Reference Librarian are themselves invoked as LLM subagents inside `index:write` and `index:search` respectively; they read their system prompts from `agents.db.agents.profile`. Archivist, DBA, and Data Steward are deterministic Python modules.

## Authority and override

User instructions override this skill's defaults at all times. If the user provides a direct instruction — "just answer," "skip routing," or any unambiguous bypass directive — comply immediately without re-asking. This skill defines default behavior; it does not constrain the user's authority to change it.

Priority order when instructions conflict:

1. **User's explicit instructions — highest priority.**
2. **Memex methodology (this skill).**
3. **Default system prompt.**
