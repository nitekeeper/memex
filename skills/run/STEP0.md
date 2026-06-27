# Memex Step 0 cold-path detail

This is a plain data document (no skill frontmatter, so Claude Code never registers
it as a second skill). It holds the verbose cold-path branches of `skills/run/SKILL.md`
Step 0. The always-loaded Step 0 region in SKILL.md points here for detail.

## Python install

This section is reached from Step 0.1 when no interpreter ≥ 3.10 is found. Detect platform with a single shell:

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

## Plugin-root resolution

This section is reached from Step 0.2 when `~/.memex/config.json` did not yield a valid `plugin_root` (cascade steps 2-4). On success, write the path back and PROCEED to the five-path checks in SKILL.md; only a failed re-ask ends the turn.

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

## Bootstrap prompt

This section is reached from Step 0.2 when ANY of the five paths is missing.

Build the missing list with EXACTLY these line shapes:
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
