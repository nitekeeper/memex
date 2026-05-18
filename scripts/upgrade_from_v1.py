"""v1 -> v2 upgrade: detect prior v1 install, archive content (symlink-safe), log.

Per design decision §5 of the v2.0 spec: v1 wiki content is NOT migrated
to brain.db. The .ai/wiki/ directory is preserved as a legacy archive
the user can manually re-ingest if desired.

v2.5.0 (§F): validates $MEMEX_V1_PATH and .ai/ are not symlinks, and
preserves symlinks under .ai/ as links (not dereferenced).
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from scripts.db import memex_home


def detect_v1_install() -> Path | None:
    """Return the v1 install path if $MEMEX_V1_PATH is set, validated, and contains .ai/.

    Validation:
      - $MEMEX_V1_PATH (pre-resolve) must not be a symlink.
      - Resolved path must be under $HOME.
      - $MEMEX_V1_PATH/.ai must exist and not be a symlink itself.

    Raises ValueError on symlink violations. Returns None on validation
    failures that are not security-sensitive (path doesn't exist, no .ai
    inside, path outside $HOME).
    """
    v1_env = os.environ.get("MEMEX_V1_PATH")
    if not v1_env:
        return None
    candidate = Path(v1_env).expanduser()

    # Check is_symlink BEFORE resolve (resolve collapses symlinks).
    if candidate.is_symlink():
        raise ValueError(f"$MEMEX_V1_PATH is a symlink ({candidate}); refusing to archive.")

    if not candidate.exists():
        return None

    v1_root = candidate.resolve()
    if os.environ.get("MEMEX_V1_PATH_ALLOW_UNUSUAL") != "1":
        try:
            v1_root.relative_to(Path.home().resolve())
        except ValueError:
            # Outside $HOME — refuse to archive arbitrary paths.
            # Set MEMEX_V1_PATH_ALLOW_UNUSUAL=1 to opt out (test fixtures use this).
            return None

    ai = v1_root / ".ai"
    if not ai.exists():
        return None
    if ai.is_symlink():
        raise ValueError(f"{ai} is a symlink; refusing to archive (symlink target unknown).")

    return v1_root


def archive_v1() -> Path | None:
    """If a v1 install is detected, archive its .ai/ content to
    ~/.memex/legacy/v1-wiki/ — symlinks preserved as links.

    Returns the archive path, or None if no v1 was found.
    """
    v1_dir = detect_v1_install()
    if v1_dir is None:
        return None

    legacy_root = memex_home() / "legacy" / "v1-wiki"
    legacy_parent = legacy_root.parent
    if legacy_parent.exists() and legacy_parent.is_symlink():
        raise ValueError(f"{legacy_parent} is a symlink; refusing to write archive through it.")
    legacy_parent.mkdir(parents=True, exist_ok=True)

    if legacy_root.exists():
        # Already archived; idempotent no-op
        _append_log("v1 archive already present; skipping re-archive.")
        return legacy_root

    # symlinks=True preserves symlinks under .ai/ as links (not dereferenced).
    # ignore_dangling_symlinks=True allows broken symlinks to be archived as
    # broken symlinks rather than aborting the whole copy.
    shutil.copytree(
        v1_dir / ".ai",
        legacy_root,
        symlinks=True,
        ignore_dangling_symlinks=True,
    )
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
