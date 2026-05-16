"""v1 -> v2 upgrade: detect prior v1 install, archive content, log.

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
