"""Archivist — deterministic raw archive writer.

Owns ~/.memex/raw/. Content-addressable: each unique canonical-form
payload stored under raw/<hash-prefix>/<filename>. Same content → same path
(idempotent). Different content with same filename → new versioned path.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.db import memex_home, require_bootstrap


def _canonicalize(payload: bytes) -> bytes:
    """Normalize line endings and strip outer whitespace before hashing.

    The same canonicalization is applied on re-ingest to detect 'no real change'
    cases regardless of CRLF vs LF or trailing newline differences.
    """
    text = payload.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return text.encode("utf-8")


def _hash(canonical: bytes) -> str:
    return hashlib.sha256(canonical).hexdigest()


def archive(payload: bytes, filename: str) -> dict:
    """Write a payload to the raw archive.

    Returns:
        {"hash": <sha256 of canonical>, "path": <absolute path of stored file>}

    Idempotency: same canonical → same path → no rewrite if file already exists.
    """
    require_bootstrap()
    canonical = _canonicalize(payload)
    h = _hash(canonical)
    prefix = h[:2]
    raw_root = memex_home() / "raw" / prefix
    raw_root.mkdir(parents=True, exist_ok=True)

    # Use hash in the filename to avoid version-overwrite when content differs
    # but caller-supplied filename is reused. Pattern: <stem>-<hash8>.<suffix>
    name_path = Path(filename)
    stem = name_path.stem
    suffix = "".join(name_path.suffixes)
    versioned = f"{stem}-{h[:8]}{suffix}"
    target = raw_root / versioned

    if not target.exists():
        target.write_bytes(payload)
    return {"hash": h, "path": str(target)}
