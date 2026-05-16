"""Reference Librarian — Python helpers for the retrieval flow.

The Reference Librarian runs as a Claude Code subagent (Option-B
Task-tool dispatch). Its job is to translate the user's natural-language
question into a structured **query plan** (FTS5 query, vector query,
filters, limit). Python then executes the plan against `index.db`.

Public API (Phase-2 refactor):
    fetch_context(caller_agent_id) -> dict
        Returns the Reference Librarian's profile + display name.

    build_prompt(query, caller_agent_id) -> str
        Assembles the full subagent prompt from the template.

    parse_query_plan(response_text) -> dict
        Parses the subagent's JSON query plan (strips code fences).

    ask_prepare(query, caller_agent_id="reference-librarian-1") -> dict
        Phase 1 — builds the subagent prompt and returns it. The skill
        markdown dispatches the Task subagent and parses the result.

    ask_execute(prepare_result, query_plan, with_embedding=True) -> list[dict]
        Phase 2 — executes the plan against ~/.memex/index.db. Returns
        ranked results.

Removed in Phase 2: `_invoke_llm` (the subagent dispatch is now done in
skill markdown via the Task tool, not in Python). Legacy `ask()` is
retained as a thin convenience wrapper for callers passing through
`brain.ask` until those callers move to the prepare/execute split.
"""
from __future__ import annotations
import json
from pathlib import Path

from scripts.db import get_connection, memex_home
from scripts import embeddings, agents as agents_mod


def _get_agent(agent_id: str) -> dict:
    agents_db = str(memex_home() / "agents.db")
    rec = agents_mod.get_agent(agents_db, agent_id)
    if rec is None:
        raise ValueError(f"Agent not registered: {agent_id}")
    return rec


def fetch_context(caller_agent_id: str = "reference-librarian-1") -> dict:
    """Gather what the Reference Librarian subagent needs to build a plan.

    Returns {"profile": <str>, "name": <str>, "caller_agent_id": <str>}.
    The skill markdown passes this into build_prompt() to assemble the
    full subagent prompt.
    """
    agent = _get_agent(caller_agent_id)
    return {
        "profile": agent["profile"],
        "name": agent["name"],
        "caller_agent_id": caller_agent_id,
    }


def build_prompt(query: str, caller_agent_id: str = "reference-librarian-1") -> str:
    """Build the Reference Librarian subagent's full prompt by template substitution.

    The skill markdown calls this to construct the Task tool's `prompt`
    argument (subagent_type=general-purpose).
    """
    template = Path("prompts/reference_librarian.md").read_text(encoding="utf-8")
    agent = _get_agent(caller_agent_id)
    profile_block = f"You are {agent['name']}.\n\n{agent['profile']}"
    return (template
        .replace("{{REFERENCE_LIBRARIAN_PROFILE}}", profile_block)
        .replace("{{QUERY}}", query)
    )


def parse_query_plan(response_text: str) -> dict:
    """Parse the Reference Librarian's JSON query plan output.

    Strips markdown code fences if present.

    Raises:
        json.JSONDecodeError: response is not valid JSON.
    """
    s = response_text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0] if s.endswith("```") else s
    return json.loads(s.strip())


def ask_prepare(query: str, caller_agent_id: str = "reference-librarian-1") -> dict:
    """Phase 1 of brain ask: build the subagent prompt.

    Returns {"status": "ready",
             "query": <original query>,
             "caller_agent_id": <id>,
             "subagent_prompt": <full Task-tool prompt>}.

    Caller dispatches Task subagent (subagent_type=general-purpose,
    prompt=subagent_prompt), parses the response via parse_query_plan,
    then calls ask_execute() with the prepare_result + parsed plan.
    """
    return {
        "status": "ready",
        "query": query,
        "caller_agent_id": caller_agent_id,
        "subagent_prompt": build_prompt(query, caller_agent_id=caller_agent_id),
    }


def execute_query_plan(plan: dict, with_embedding: bool = True) -> list[dict]:
    """Execute a query plan against index.db. Returns ranked results.

    plan fields:
        fts_query (str, optional)    — FTS5 MATCH expression
        vector_query (str, optional) — text to embed for cosine similarity
        filters (dict, optional)     — {"domain": ..., "store": ...}
        limit (int, optional)        — max results (default 10)

    If with_embedding=True and the plan has a vector_query, hybrid
    retrieval merges FTS5 hits with vector cosine hits (dedup by
    index_id; FTS5 results take precedence). If no API key for
    embeddings, the call to embeddings.encode raises; caller can wrap
    with try/except and fall back to with_embedding=False.
    """
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)

    fts_q = plan.get("fts_query") or ""
    filters = plan.get("filters") or {}
    limit = plan.get("limit") or 10

    where_clauses = []
    params: list = []
    if filters.get("domain"):
        where_clauses.append("d.domain = ?")
        params.append(filters["domain"])
    if filters.get("store"):
        where_clauses.append("d.store = ?")
        params.append(filters["store"])

    where_extra = (" AND " + " AND ".join(where_clauses)) if where_clauses else ""

    fts_rows: list[dict] = []
    if fts_q:
        sql = f"""
            SELECT d.index_id, d.key, d.domain, d.store, d.table_name, d.row_id,
                   d.searchable, d.embedding
            FROM documents_fts f
            JOIN documents d ON d.rowid = f.rowid
            WHERE documents_fts MATCH ?{where_extra}
            ORDER BY rank
            LIMIT ?
        """
        fts_rows = [dict(r) for r in conn.execute(sql, (fts_q, *params, limit))]

    if not with_embedding or not plan.get("vector_query"):
        conn.close()
        return fts_rows

    # Hybrid: FTS5 + vector cosine
    qvec_blob = embeddings.encode(plan["vector_query"])
    where_vec = (" AND " + " AND ".join(where_clauses)) if where_clauses else ""
    sql_all = f"""
        SELECT index_id, key, domain, store, table_name, row_id, searchable, embedding
        FROM documents d
        WHERE embedding IS NOT NULL{where_vec}
    """
    all_rows = [dict(r) for r in conn.execute(sql_all, params)]
    conn.close()

    scored = []
    for r in all_rows:
        if r["embedding"]:
            score = embeddings.cosine(qvec_blob, r["embedding"])
            scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    # Merge fts + vector (dedupe by index_id; FTS hits keep their rank order)
    seen = {r["index_id"]: r for r in fts_rows}
    for score, r in scored[:limit]:
        if r["index_id"] not in seen:
            seen[r["index_id"]] = r
    return list(seen.values())[:limit]


def ask_execute(
    prepare_result: dict,
    query_plan: dict,
    with_embedding: bool = False,
) -> list[dict]:
    """Phase 2 of brain ask: execute the plan returned by the subagent.

    Args:
        prepare_result: dict returned by ask_prepare() (carries query metadata
            for downstream telemetry; not strictly used in execution today).
        query_plan: parsed JSON from parse_query_plan(<subagent response>).
        with_embedding: enable vector cosine alongside FTS5. Default False —
            without an embedding the plan is FTS5-only; flip to True when
            embeddings are populated and an API key is available for the
            query vector. Skills typically wrap in try/except and fall
            back to False on RuntimeError.

    Returns ranked list of result dicts.

    Raises:
        ValueError: prepare_result is not "ready".
    """
    if prepare_result.get("status") != "ready":
        raise ValueError(
            f"ask_execute called with prepare_result.status="
            f"{prepare_result.get('status')!r}; expected 'ready'"
        )
    return execute_query_plan(query_plan, with_embedding=with_embedding)
