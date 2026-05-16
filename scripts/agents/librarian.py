"""Librarian — LLM-driven indexing harness.

build_prompt: assemble the prompt text from the template + caller context.
parse_response: validate and coerce the LLM's JSON output.
index_write: top-level orchestration — invoke LLM, write to index.db,
              delegate to Core for target-store insertion.
"""
from __future__ import annotations
import json
import uuid
from pathlib import Path
from scripts import registry, stores, agents as agents_mod
from scripts.db import get_connection, memex_home
from scripts import embeddings


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
    rows = [dict(r) for r in conn.execute(
        "SELECT index_id, key, domain FROM documents ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )]
    conn.close()
    return rows


def build_prompt(
    payload,
    target_store: str,
    caller_agent_id: str,
    existing_index_snippet: list[dict] | None = None,
) -> str:
    if existing_index_snippet is None:
        existing_index_snippet = _recent_index_snippet()
    template = _load_template()
    profile = _get_profile("librarian-1")
    return (template
        .replace("{{LIBRARIAN_PROFILE}}", profile)
        .replace("{{TARGET_STORE}}", target_store)
        .replace("{{CALLER_AGENT_ID}}", caller_agent_id)
        .replace("{{PAYLOAD_JSON}}", json.dumps(payload, ensure_ascii=False, indent=2))
        .replace("{{EXISTING_INDEX_SNIPPET}}", json.dumps(existing_index_snippet, ensure_ascii=False, indent=2))
    )


def parse_response(response_text: str) -> dict:
    """Parse and validate the Librarian's JSON output."""
    # Strip code fences if present
    s = response_text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0] if s.endswith("```") else s
    parsed = json.loads(s.strip())
    missing = _REQUIRED_FIELDS - set(parsed.keys())
    if missing:
        raise ValueError(f"Librarian response missing fields: {missing}")
    parsed.setdefault("metadata", {})
    parsed.setdefault("relations", [])
    return parsed


def _invoke_llm(prompt: str) -> str:
    """Invoke the Librarian subagent via Claude Code's Task tool.

    Plan 2's implementation wires this to the actual subagent invocation
    mechanism. For testing, this is mocked. The exact mechanism (Task tool
    vs inline skill) is deferred per spec §14.
    """
    raise NotImplementedError(
        "Subagent invocation TBD — patch this in tests; wire to Task tool in production."
    )


def _encode_embedding(text: str) -> bytes:
    """Wrapper for embeddings.encode — patched in tests to skip API calls."""
    return embeddings.encode(text)


def index_write(
    payload: dict,
    target_store: str,
    target_table: str,
    caller_agent_id: str,
) -> dict:
    """Top-level write path. Returns the dict Librarian produced (plus
    the target store row's PK).
    """
    prompt = build_prompt(payload, target_store, caller_agent_id)
    response = _invoke_llm(prompt)
    extracted = parse_response(response)

    # If LLM didn't supply index_id, generate one
    if not extracted.get("index_id"):
        extracted["index_id"] = str(uuid.uuid4())

    # Compute embedding from searchable text
    embedding_blob = _encode_embedding(extracted["searchable"])

    # Write to index.db
    index_db_path = str(memex_home() / "index.db")
    conn = get_connection(index_db_path)
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, metadata, embedding, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            extracted["index_id"],
            extracted.get("key"),
            extracted["domain"],
            target_store,
            target_table,
            "",  # row_id filled in after target-store insert
            extracted["searchable"],
            json.dumps(extracted["metadata"]),
            embedding_blob,
            caller_agent_id,
        ),
    )
    for rel in extracted.get("relations", []):
        conn.execute(
            "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
            (extracted["index_id"], rel["to_index_id"], rel["rel_type"]),
        )
    conn.commit()
    conn.close()

    # Delegate to Core for target store
    insert_row = {**payload, "index_id": extracted["index_id"]}
    inserted = stores.insert(target_store, target_table, insert_row)

    # Update documents.row_id with the actual PK now that we know it
    conn = get_connection(index_db_path)
    conn.execute(
        "UPDATE documents SET row_id = ? WHERE index_id = ?",
        (str(inserted.get("id", "")), extracted["index_id"]),
    )
    conn.commit()
    conn.close()

    return {**extracted, "row_id": inserted.get("id")}
