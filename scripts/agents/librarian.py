"""Librarian — Python helpers for the indexing flow.

The Librarian agent itself is invoked as a Claude Code subagent via the
Task tool (see spec §8.5). Python here provides the prep work, prompt
construction, response parsing, and persistence — the LLM step happens
between `fetch_context()`+`build_prompt()` and `write_entry()`, dispatched
by the skill markdown.

Public API:
    fetch_context(target_store) -> dict
        Returns {profile, snippet} for the Librarian subagent's prompt.

    build_prompt(payload, target_store, caller_agent_id,
                 existing_index_snippet=None) -> str
        Assembles the full subagent prompt from the template.

    parse_response(response_text) -> dict
        Validates and coerces the subagent's JSON response.

    validate_output(obj) -> dict
        Validates a caller-built librarian_output dict against the same
        schema parse_response enforces. For consumers (e.g. Atelier) that
        know their domain and produce a librarian_output deterministically
        instead of dispatching the Librarian subagent. See spec §6.2.

    write_entry(payload, librarian_output, target_store, target_table,
                caller_agent_id, embedding=None) -> dict
        Persists: index.db.documents + relations + target store row.
        Returns the resulting dict (with row_id added).

Removed in v2.0 refactor: `_invoke_llm` and `index_write`. The LLM
invocation no longer happens in Python — the skill markdown dispatches
the Librarian subagent via Task tool and passes the parsed response to
`write_entry()`. See internal/brain/ingest/SKILL.md for the recipe.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from scripts import agents as agents_mod
from scripts import stores
from scripts.db import get_connection, memex_home

_REQUIRED_FIELDS = {"index_id", "key", "domain", "searchable"}


def _load_template() -> str:
    return Path("prompts/librarian.md").read_text(encoding="utf-8")


def _get_profile(agent_id: str) -> str:
    agents_db = str(memex_home() / "agents.db")
    record = agents_mod.get_agent(agents_db, agent_id)
    if record is None:
        raise ValueError(f"Agent not registered: {agent_id}")
    return record["profile"]


def _recent_index_snippet(limit: int = 20) -> list[dict]:
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    rows = [
        dict(r)
        for r in conn.execute(
            "SELECT index_id, key, domain FROM documents ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    ]
    conn.close()
    return rows


def fetch_context(target_store: str, snippet_limit: int = 20) -> dict:
    """Gather what the Librarian subagent needs to do classification.

    Returns {"profile": <str>, "snippet": <list[dict]>, "target_store": <str>}.
    The skill markdown passes this into build_prompt() to assemble the full
    subagent prompt.
    """
    return {
        "profile": _get_profile("librarian-1"),
        "snippet": _recent_index_snippet(limit=snippet_limit),
        "target_store": target_store,
    }


def build_prompt(
    payload,
    target_store: str,
    caller_agent_id: str,
    existing_index_snippet: list[dict] | None = None,
) -> str:
    """Build the Librarian subagent's full prompt by template substitution.

    The skill markdown calls this to construct the Task tool's `prompt`
    argument. Subagent_type=general-purpose; the system prompt is the
    Librarian profile embedded in the template.
    """
    if existing_index_snippet is None:
        existing_index_snippet = _recent_index_snippet()
    template = _load_template()
    profile = _get_profile("librarian-1")
    return (
        template.replace("{{LIBRARIAN_PROFILE}}", profile)
        .replace("{{TARGET_STORE}}", target_store)
        .replace("{{CALLER_AGENT_ID}}", caller_agent_id)
        .replace("{{PAYLOAD_JSON}}", json.dumps(payload, ensure_ascii=False, indent=2))
        .replace(
            "{{EXISTING_INDEX_SNIPPET}}",
            json.dumps(existing_index_snippet, ensure_ascii=False, indent=2),
        )
    )


def validate_output(obj: dict) -> dict:
    """Validate a librarian_output dict against the schema parse_response enforces.

    Used by both the subagent path (via parse_response) and the
    caller-built path (consumers that produce librarian_output
    deterministically). Same schema, one source of truth.

    Required: index_id, key, domain, searchable.
    Optional (defaults applied): metadata={}, relations=[].

    Raises:
        ValueError: if any required field is missing, or `obj` is not a dict.

    Returns:
        A new dict with defaults filled in. The input is not mutated.
    """
    if not isinstance(obj, dict):
        raise ValueError(f"librarian_output must be a dict, got {type(obj).__name__}")
    missing = _REQUIRED_FIELDS - set(obj.keys())
    if missing:
        raise ValueError(f"librarian_output missing fields: {missing}")
    out = dict(obj)
    out.setdefault("metadata", {})
    out.setdefault("relations", [])
    return out


def parse_response(response_text: str) -> dict:
    """Parse and validate the Librarian subagent's JSON output.

    Strips markdown code fences if present (subagents often wrap JSON in
    ```json ... ```). Validates via validate_output().

    Raises:
        ValueError: response missing required fields, or unparseable as JSON.
    """
    s = response_text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0] if s.endswith("```") else s
    parsed = json.loads(s.strip())
    return validate_output(parsed)


def write_entry(
    payload: dict,
    librarian_output: dict,
    target_store: str,
    target_table: str,
    caller_agent_id: str,
    embedding: bytes | None = None,
) -> dict:
    """Persist a classified document.

    Two-stage write per spec §6.1 (eventually consistent):
      1. Write index.db.documents + relations rows (commits)
      2. Write target-store row via stores.insert (commits)
      3. Update documents.row_id with the target-store PK (commits)

    A crash between steps 1 and 2 leaves an orphan in index.db; the Data
    Steward audit detects it.

    Args:
        payload: the row to insert into the target store (must NOT include
            `index_id` — this function adds it from librarian_output).
        librarian_output: parsed dict from parse_response(). Must have
            index_id, key, domain, searchable, plus optional metadata, relations.
        target_store: registered store name (e.g., "article").
        target_table: target table inside that store (e.g., "articles", "captures").
        caller_agent_id: who invoked this; recorded in documents.created_by.
        embedding: float32 BLOB from embeddings.encode(), or None to skip
            (vector search will be unavailable for this document; FTS5 still works).

    Returns:
        librarian_output augmented with "row_id" (the target-store PK).
    """
    librarian_output = validate_output(librarian_output)

    # Default in case the subagent supplied an empty/falsy index_id
    index_id = librarian_output.get("index_id") or str(uuid.uuid4())
    librarian_output = {**librarian_output, "index_id": index_id}

    metadata = librarian_output.get("metadata") or {}
    relations = librarian_output.get("relations") or []

    index_db_path = str(memex_home() / "index.db")

    # Step 1: Index row + relations
    conn = get_connection(index_db_path)
    try:
        conn.execute(
            "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
            "searchable, metadata, embedding, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                index_id,
                librarian_output.get("key"),
                librarian_output["domain"],
                target_store,
                target_table,
                "",  # row_id filled in after target-store insert
                librarian_output["searchable"],
                json.dumps(metadata),
                embedding,
                caller_agent_id,
            ),
        )
        for rel in relations:
            conn.execute(
                "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
                (index_id, rel["to_index_id"], rel["rel_type"]),
            )
        conn.commit()
    finally:
        conn.close()

    # Step 2: target-store row (via Core)
    insert_row = {**payload, "index_id": index_id}
    inserted = stores.insert(target_store, target_table, insert_row)

    # Step 3: Update documents.row_id with the actual PK
    conn = get_connection(index_db_path)
    try:
        conn.execute(
            "UPDATE documents SET row_id = ? WHERE index_id = ?",
            (str(inserted.get("id", "")), index_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {**librarian_output, "row_id": inserted.get("id")}
