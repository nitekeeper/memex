"""Settings-recommendation-on-upgrade: the canonical single source of truth.

When the memex plugin version is bumped, the first ``memex:run`` on that version
OFFERS the user (y/N, default No — see ``internal/core/settings-recommendation/``)
to apply the cost-optimized recommended settings to ``~/.claude/settings.json``.
On consent the settings are MERGED in (merge-safe: every pre-existing top-level
key is preserved; only the 3 recommended keys are touched). The offer is
consent-gated and fires at most once per version.

This module owns the RECOMMENDED constant plus all version/settings/state
mechanics. It has two read-only compute paths (``eligibility`` and its inputs)
and two mutating paths (``apply_recommended`` and ``write_state``). Every public
function is wrapped to a graceful no-op on any error so it can NEVER crash a
memex invocation.

M3 distinction (load-bearing).
``~/.claude/settings.json`` is a LOCAL Claude Code config file, NOT a
memex-managed store. M3 ("all writes through the Librarian", spec §6) governs
writes that land in a Memex-managed store (agents.db / index.db / article.db
via ``internal/index/write``). It does NOT apply here: this module writes
``settings.json`` (and its per-version state marker) DIRECTLY with an atomic
temp-file + ``os.replace``, never via the Librarian / Archivist / Memex Core.
It also NEVER touches ``managed-settings.json``.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path

from scripts.db import MemexHomeInvalidError, memex_home
from scripts.paths import PLUGIN_ROOT

# The cost-optimized recommendation. ``model`` MUST be the family alias
# "sonnet", NOT a pinned ``claude-sonnet-*`` id — the alias tracks the latest
# Sonnet so installers inherit the cost posture without a stale pin. The
# constant-pin test (tests/test_recommended_settings.py) fails if this drifts.
RECOMMENDED: dict[str, object] = {
    "model": "sonnet",
    "effortLevel": "high",
    "autoCompactEnabled": True,
}

# Errors that any read/write path may legitimately hit and must swallow so a
# bad $MEMEX_HOME, a missing file, or malformed JSON can never crash a memex run.
_GRACEFUL_ERRORS = (OSError, ValueError, TypeError, MemexHomeInvalidError)


def settings_path() -> Path:
    """Resolve ``~/.claude/settings.json``.

    Honors ``$CLAUDE_SETTINGS_PATH`` (used by hermetic tests) else falls back to
    ``Path.home() / '.claude' / 'settings.json'`` — never a hardcoded
    ``/home/<user>`` path.
    """
    override = os.environ.get("CLAUDE_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "settings.json"


def state_path() -> Path:
    """Resolve the per-version state marker under memex's home.

    Reuses ``scripts.db.memex_home()`` (which honors ``$MEMEX_HOME`` +
    ``MEMEX_HOME_ALLOW_UNUSUAL``) — we do NOT reinvent ``~/.memex`` resolution.
    Overridable via ``$MEMEX_SETTINGS_REC_STATE_PATH`` for tests.
    """
    override = os.environ.get("MEMEX_SETTINGS_REC_STATE_PATH")
    if override:
        return Path(override).expanduser()
    return memex_home() / "settings_rec_state.json"


def current_plugin_version() -> str | None:
    """Read the plugin version from ``PLUGIN_ROOT/.claude-plugin/plugin.json``.

    Anchored via ``scripts.paths.PLUGIN_ROOT`` (``__file__``-relative), NEVER a
    cwd walk. Returns ``None`` on missing/malformed.
    """
    try:
        raw = (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        version = json.loads(raw).get("version")
        return version if isinstance(version, str) and version else None
    except (OSError, ValueError, TypeError):
        return None


def load_settings(path: Path | None = None) -> dict:
    """Load ``settings.json`` as a dict. Returns ``{}`` on missing/malformed JSON.

    Never raises — a corrupt or absent settings file must not crash a memex run.
    """
    try:
        target = path if path is not None else settings_path()
        data = json.loads(Path(target).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except _GRACEFUL_ERRORS:
        return {}


def compute_changes(current: dict, recommended: dict = RECOMMENDED) -> dict:
    """Return only the recommended keys that are absent-or-different in ``current``.

    ``{}`` when ``current`` already satisfies every recommended key (idempotent):
    this is what makes ``apply_recommended`` a no-op on the second call.
    """
    try:
        return {k: v for k, v in recommended.items() if k not in current or current.get(k) != v}
    except (AttributeError, TypeError):
        return {}


def read_state() -> dict:
    """Load the per-version state marker. Returns ``{}`` on missing/malformed."""
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except _GRACEFUL_ERRORS:
        return {}


def _atomic_write_json(target: Path, data: dict) -> None:
    """Atomically write ``data`` as JSON to ``target``.

    Writes to a temp file in the SAME directory (so ``os.replace`` is a rename
    within one filesystem, hence atomic) then replaces. Creates the parent
    directory if missing. Leaves no debris: the temp file is either renamed into
    place or unlinked on error.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".tmp-", suffix=".json")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, target)
    except BaseException:
        # Clean up the temp file so no debris is left in the directory.
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def write_state(version: str, decision: str) -> None:
    """Record that ``version`` was handled with ``decision`` ('applied'|'declined').

    Atomic temp-in-same-dir + ``os.replace``; mkdir parent if missing. Graceful
    no-op on any error so it never crashes a memex invocation.
    """
    if decision not in {"applied", "declined"}:
        return
    try:
        _atomic_write_json(state_path(), {"last_handled_version": version, "decision": decision})
    except _GRACEFUL_ERRORS:
        return


def eligibility() -> dict | None:
    """Read-only: is an offer due for the current version? NEVER writes.

    Returns ``{'eligible': True, 'current_version': v, 'changes': c}`` iff the
    plugin version is resolvable AND differs from the last handled version AND
    there are recommended changes to apply; else ``None``.
    """
    try:
        version = current_plugin_version()
        if version is None:
            return None
        if version == read_state().get("last_handled_version"):
            return None
        changes = compute_changes(load_settings())
        if not changes:
            return None
        return {"eligible": True, "current_version": version, "changes": changes}
    except Exception:
        return None


# Alias per the action-item spec (atelier parity: maybe_offer == eligibility).
maybe_offer = eligibility


def apply_recommended(path: Path | None = None) -> dict:
    """MERGE the recommended settings into ``settings.json``. Returns the changes.

    Merge-safety (AI-2): starts from the current settings (or ``{}``), preserves
    EVERY existing top-level key (env, enabledPlugins, permissions, statusLine,
    hooks, …) and only writes the recommended keys that are absent-or-different.
    Atomic temp-in-same-dir + ``os.replace``; mkdir parent if missing. Idempotent
    — a second call computes ``{}`` changes and rewrites identical content.

    This is a LOCAL CONFIG write, outside M3/Librarian scope (see module
    docstring). Graceful no-op (returns ``{}``) on any error.
    """
    try:
        target = path if path is not None else settings_path()
        current = load_settings(target)
        changes = compute_changes(current)
        merged = {**current, **changes}
        _atomic_write_json(Path(target), merged)
        return changes
    except _GRACEFUL_ERRORS:
        return {}


def main(argv: list[str]) -> int:
    """CLI for manual recovery (mirrors onboarding.py / install.py style).

    ``status`` — print the read-only eligibility result.
    ``apply``  — apply the recommended settings (mutating) and record state.
    """
    if len(argv) < 2 or argv[1] not in {"status", "apply"}:
        print("usage: python -m scripts.recommended_settings {status|apply}", file=sys.stderr)
        return 2
    if argv[1] == "status":
        e = eligibility()
        print(json.dumps(e) if e else "")
        return 0
    # apply (mutating)
    changes = apply_recommended()
    version = current_plugin_version()
    if version is not None:
        write_state(version, "applied")
    print(json.dumps({"applied": changes}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
