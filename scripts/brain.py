"""Memex Brain operations: ingest, ask, capture, lint, synthesize.

Brain is a consumer of Memex's Index + Librarian. All writes route
through memex:index:write. All reads route through memex:index:search.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from scripts import stores
from scripts.agents import librarian, reference_librarian, archivist
from scripts.agents import data_steward
from scripts.db import memex_home


def _canonical_hash(body: str) -> str:
    """Compute a stable hash for a body, normalized for rerun safety."""
    text = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _find_existing_by_hash(source_hash: str) -> dict | None:
    rows = stores.query("article", "SELECT * FROM articles WHERE source_hash = ? LIMIT 1", (source_hash,))
    return rows[0] if rows else None


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text or "untitled"


def ingest(
    title: str,
    body: str,
    caller_agent_id: str,
    source_url: str | None = None,
) -> dict:
    """Ingest an article into article.db. Returns dict with status+index_id."""
    source_hash = _canonical_hash(body)
    existing = _find_existing_by_hash(source_hash)
    if existing is not None:
        return {
            "status": "skipped",
            "reason": "source_hash matches existing article",
            "existing_index_id": existing["index_id"],
        }

    # Archive raw payload
    archive_result = archivist.archive(body.encode("utf-8"), filename=f"{_slugify(title)}.md")

    payload = {
        "title": title,
        "body": body,
        "source_url": source_url,
        "source_hash": source_hash,
        "raw_path": archive_result["path"],
        "created_by": caller_agent_id,
    }

    result = librarian.index_write(
        payload=payload,
        target_store="article",
        target_table="articles",
        caller_agent_id=caller_agent_id,
    )
    return {"status": "ingested", **result}


def capture(body: str, caller_agent_id: str, title: str | None = None) -> dict:
    """Capture a free-form note into article.db.captures.

    Lighter than ingest — no source URL, no hash check, but still routes
    through the Librarian.
    """
    payload = {
        "title": title,
        "body": body,
        "created_by": caller_agent_id,
    }
    result = librarian.index_write(
        payload=payload,
        target_store="article",
        target_table="captures",
        caller_agent_id=caller_agent_id,
    )
    return {"status": "captured", **result}
