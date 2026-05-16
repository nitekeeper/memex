"""Reference Librarian — LLM-driven retrieval harness."""
from __future__ import annotations
import json
from pathlib import Path
from scripts.db import get_connection, memex_home
from scripts import embeddings, agents as agents_mod


def _get_agent(agent_id: str) -> dict:
    agents_db = str(memex_home() / "agents.db")
    return agents_mod.get_agent(agents_db, agent_id)


def _get_profile(agent_id: str) -> str:
    return _get_agent(agent_id)["profile"]


def build_prompt(query: str, caller_agent_id: str) -> str:
    template = Path("prompts/reference_librarian.md").read_text(encoding="utf-8")
    agent = _get_agent("reference-librarian-1")
    # Embed the agent's display name alongside the profile so callers (and
    # tests) can verify the right persona was bound into the prompt.
    profile_block = f"You are {agent['name']}.\n\n{agent['profile']}"
    return (template
        .replace("{{REFERENCE_LIBRARIAN_PROFILE}}", profile_block)
        .replace("{{QUERY}}", query)
    )


def parse_query_plan(response_text: str) -> dict:
    s = response_text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0] if s.endswith("```") else s
    return json.loads(s.strip())


def _invoke_llm(prompt: str) -> str:
    raise NotImplementedError("Subagent invocation TBD — see Librarian harness.")


def execute_query_plan(plan: dict, with_embedding: bool = True) -> list[dict]:
    """Execute a query plan against index.db. Returns ranked results."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)

    # Build base FTS query
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

    # Vector cosine
    qvec_blob = embeddings.encode(plan["vector_query"])
    # For the all-rows query, the WHERE prefix differs (no leading AND).
    where_vec = (" AND " + " AND ".join(where_clauses)) if where_clauses else ""
    sql_all = f"""
        SELECT index_id, key, domain, store, table_name, row_id, searchable, embedding
        FROM documents d
        WHERE embedding IS NOT NULL{where_vec}
    """
    all_rows = [dict(r) for r in conn.execute(sql_all, params)]
    conn.close()

    # Compute cosine
    scored = []
    for r in all_rows:
        if r["embedding"]:
            score = embeddings.cosine(qvec_blob, r["embedding"])
            scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    # Merge fts + vector (simple: union, dedupe by index_id, prefer higher rank)
    seen = {r["index_id"]: r for r in fts_rows}
    for score, r in scored[:limit]:
        if r["index_id"] not in seen:
            seen[r["index_id"]] = r
    return list(seen.values())[:limit]


def ask(query: str) -> list[dict]:
    """Top-level read path. Returns ranked results."""
    prompt = build_prompt(query, caller_agent_id="reference-librarian-1")
    plan_text = _invoke_llm(prompt)
    plan = parse_query_plan(plan_text)
    return execute_query_plan(plan, with_embedding=False)  # default off in v0.2 baseline; flip when embeddings backfilled
