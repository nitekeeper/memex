"""Memex Brain operations.

Each LLM-mediated flow (ingest, capture, ask, synthesize) is split into
two Python helpers — `*_prepare` (sync prep) and `*_complete` (sync
persistence) — around a Task-tool subagent dispatch performed by the
skill markdown. See spec §8.5 and internal/brain/*/SKILL.md for the
orchestration recipes.

The Synthesizer flow has an extra step in the middle (the Synthesizer
subagent produces text that the Librarian then classifies); see
synthesize_prepare/complete for the contract.
"""

from __future__ import annotations

import hashlib
import json
import re

from scripts import stores
from scripts.agents import archivist, data_steward, librarian, reference_librarian
from scripts.db import get_connection, memex_home, require_bootstrap
from scripts.paths import PROMPTS_DIR

# ── Internal helpers ──────────────────────────────────────────────────────


def _canonical_hash(body: str) -> str:
    """Compute a stable hash for a body, normalized for rerun safety."""
    text = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _find_existing_by_hash(source_hash: str) -> dict | None:
    rows = stores.query(
        "article",
        "SELECT * FROM articles WHERE source_hash = ? LIMIT 1",
        (source_hash,),
    )
    return rows[0] if rows else None


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text or "untitled"


def _fetch_source_bodies(index_ids: list[str]) -> list[dict]:
    """Fetch the full row for each index_id from the article store."""
    sources = []
    for idx in index_ids:
        rows = stores.query("article", "SELECT * FROM articles WHERE index_id = ?", (idx,))
        if rows:
            sources.append(
                {
                    "index_id": idx,
                    "body": rows[0]["body"],
                    "title": rows[0].get("title", ""),
                }
            )
    return sources


# ── ingest ─────────────────────────────────────────────────────────────────


def ingest_prepare(
    title: str,
    body: str,
    caller_agent_id: str,
    source_url: str | None = None,
) -> dict:
    """Phase 1 of brain ingest: hash-check, archive, build Librarian prompt.

    Returns one of:
      {"status": "skipped",
       "reason": "source_hash matches existing article",
       "existing_index_id": "<uuid>"}
        — caller stops here; nothing was written.

      {"status": "ready",
       "payload": {<row-to-be-inserted-into-article.db.articles>},
       "target_store": "article",
       "target_table": "articles",
       "caller_agent_id": "<id>",
       "raw_archive": {"hash": "<sha>", "path": "<abs path>"},
       "subagent_prompt": "<full prompt text for Task tool>"}
        — caller dispatches the Librarian subagent (subagent_type=general-purpose,
          prompt=subagent_prompt), receives the JSON response, passes both
          to ingest_complete().
    """
    require_bootstrap()
    source_hash = _canonical_hash(body)
    existing = _find_existing_by_hash(source_hash)
    if existing is not None:
        return {
            "status": "skipped",
            "reason": "source_hash matches existing article",
            "existing_index_id": existing["index_id"],
        }

    archive_result = archivist.archive(body.encode("utf-8"), filename=f"{_slugify(title)}.md")

    payload = {
        "title": title,
        "body": body,
        "source_url": source_url,
        "source_hash": source_hash,
        "raw_path": archive_result["path"],
        "created_by": caller_agent_id,
    }

    subagent_prompt = librarian.build_prompt(
        payload=payload,
        target_store="article",
        caller_agent_id=caller_agent_id,
    )

    return {
        "status": "ready",
        "payload": payload,
        "target_store": "article",
        "target_table": "articles",
        "caller_agent_id": caller_agent_id,
        "raw_archive": archive_result,
        "subagent_prompt": subagent_prompt,
    }


def ingest_complete(
    prepare_result: dict,
    librarian_output: dict,
    embedding: bytes | None = None,
) -> dict:
    """Phase 2 of brain ingest: persist to Index + article.db.

    Args:
        prepare_result: the dict returned by ingest_prepare() with status="ready".
        librarian_output: parsed dict from librarian.parse_response(<subagent response>).
        embedding: float32 BLOB from embeddings.encode() of librarian_output["searchable"],
            or None to skip (FTS5 still works; vector cosine will not).

    Returns:
        {"status": "ingested", "index_id": ..., "key": ..., "domain": ...,
         "row_id": ..., "relations": [...]}

    Raises:
        ValueError: prepare_result is not "ready", or librarian_output is malformed.
    """
    require_bootstrap()
    if prepare_result.get("status") != "ready":
        raise ValueError(
            f"ingest_complete called with prepare_result.status="
            f"{prepare_result.get('status')!r}; expected 'ready'"
        )
    result = librarian.write_entry(
        payload=prepare_result["payload"],
        librarian_output=librarian_output,
        target_store=prepare_result["target_store"],
        target_table=prepare_result["target_table"],
        caller_agent_id=prepare_result["caller_agent_id"],
        embedding=embedding,
    )
    return {"status": "ingested", **result}


# ── capture ────────────────────────────────────────────────────────────────


def capture_prepare(
    body: str,
    caller_agent_id: str,
    title: str | None = None,
) -> dict:
    """Phase 1 of brain capture. No source-hash check (captures are free-form);
    no archive (small notes don't go through immutable storage).

    Returns: {"status": "ready", "payload": {...},
              "target_store": "article", "target_table": "captures",
              "caller_agent_id": ..., "subagent_prompt": ...}
    """
    require_bootstrap()
    payload = {
        "title": title,
        "body": body,
        "created_by": caller_agent_id,
    }
    subagent_prompt = librarian.build_prompt(
        payload=payload,
        target_store="article",
        caller_agent_id=caller_agent_id,
    )
    return {
        "status": "ready",
        "payload": payload,
        "target_store": "article",
        "target_table": "captures",
        "caller_agent_id": caller_agent_id,
        "subagent_prompt": subagent_prompt,
    }


def capture_complete(
    prepare_result: dict,
    librarian_output: dict,
    embedding: bytes | None = None,
) -> dict:
    """Phase 2 of brain capture. Persists to article.db.captures."""
    require_bootstrap()
    if prepare_result.get("status") != "ready":
        raise ValueError(
            f"capture_complete called with prepare_result.status="
            f"{prepare_result.get('status')!r}; expected 'ready'"
        )
    result = librarian.write_entry(
        payload=prepare_result["payload"],
        librarian_output=librarian_output,
        target_store=prepare_result["target_store"],
        target_table=prepare_result["target_table"],
        caller_agent_id=prepare_result["caller_agent_id"],
        embedding=embedding,
    )
    return {"status": "captured", **result}


# ── ask (Reference Librarian — Phase 2 refactor) ───────────────────────────


def ask_prepare(query: str, caller_agent_id: str = "reference-librarian-1") -> dict:
    """Phase 1 of brain ask. Builds the Reference Librarian subagent prompt.

    Returns {"status": "ready", "query": <q>, "caller_agent_id": <id>,
             "subagent_prompt": <full Task-tool prompt>}.

    Skill markdown dispatches the subagent, parses the query plan, and
    calls ask_execute() with both.
    """
    require_bootstrap()
    return reference_librarian.ask_prepare(query, caller_agent_id=caller_agent_id)


def ask_execute(
    prepare_result: dict,
    query_plan: dict,
    with_embedding: bool = False,
) -> list[dict]:
    """Phase 2 of brain ask. Executes the query plan and returns ranked results."""
    require_bootstrap()
    return reference_librarian.ask_execute(
        prepare_result,
        query_plan,
        with_embedding=with_embedding,
    )


# ── GraphRAG ask modes: global (map-reduce) + local (neighborhood) ─────────
#
# `flat` mode is the existing ask_prepare/ask_execute path above and is left
# byte-for-byte unchanged. The two new modes below sit in front of the
# community layer:
#
#   global  — thematic / corpus-wide questions answered by map-reduce over
#             community_reports at a chosen level. MAP: each report -> a scored
#             (0-100) partial answer via subagent; drop the zeros. REDUCE:
#             sort by score desc, fill a budget, one final answer.
#   local   — entity / neighborhood questions answered by seeding on the most
#             similar documents (cosine), expanding via `relations`, pulling in
#             those docs' community reports, and answering over the assembled
#             context.
#
# All three are Option-B: Python builds prompts, the skill dispatches the
# subagent(s), Python parses + assembles.


def global_ask_prepare(query: str, level: int = 0) -> dict:
    """Phase 1 of global ask: build one MAP prompt per community report.

    Reads `community_reports` at `level` and produces a per-report map prompt
    asking the subagent to score helpfulness (0-100) + extract a partial
    answer. The skill dispatches one subagent per map unit, parses each via
    `parse_map_response`, then calls `global_ask_reduce_prepare`.

    Returns {"status": "ready" | "no_reports", "query", "level",
             "map_units": [{"community_id", "title", "map_prompt"}, ...]}.
    """
    require_bootstrap()
    template = (PROMPTS_DIR / "global_map.md").read_text(encoding="utf-8")
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    try:
        reports = [
            dict(r)
            for r in conn.execute(
                "SELECT community_id, title, summary, findings FROM community_reports "
                "WHERE level = ? ORDER BY rating DESC, community_id",
                (level,),
            )
        ]
    finally:
        conn.close()

    if not reports:
        return {"status": "no_reports", "query": query, "level": level, "map_units": []}

    map_units = []
    for rep in reports:
        try:
            findings = json.loads(rep.get("findings") or "[]")
        except (json.JSONDecodeError, TypeError):
            findings = []
        findings_md = "\n".join(
            f"- {f.get('summary', '')}: {f.get('explanation', '')}" for f in findings
        )
        report_body = (rep.get("summary") or "") + (
            ("\n\nFindings:\n" + findings_md) if findings_md else ""
        )
        # Substitute trusted/body placeholders FIRST and the user-supplied
        # QUERY LAST so a query that literally contains another placeholder
        # token (e.g. "{{REPORT_BODY}}") can never be re-expanded.
        map_prompt = (
            template.replace("{{COMMUNITY_ID}}", rep["community_id"])
            .replace("{{TITLE}}", rep.get("title") or "")
            .replace("{{REPORT_BODY}}", report_body)
            .replace("{{QUERY}}", query)
        )
        map_units.append(
            {
                "community_id": rep["community_id"],
                "title": rep.get("title") or "",
                "map_prompt": map_prompt,
            }
        )
    return {"status": "ready", "query": query, "level": level, "map_units": map_units}


def parse_map_response(response_text: str) -> dict:
    """Parse a global-map subagent response into {score:int, partial_answer:str}.

    Strips code fences; clamps score into [0, 100]. Raises ValueError on
    malformed input.
    """
    s = response_text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0] if s.endswith("```") else s
    obj = json.loads(s.strip())
    if not isinstance(obj, dict) or "score" not in obj:
        raise ValueError("global-map response must be a JSON object with a 'score'")
    try:
        score = round(float(obj["score"]))
    except (TypeError, ValueError) as e:
        raise ValueError(f"global-map score not numeric: {obj.get('score')!r}") from e
    score = max(0, min(100, score))
    return {"score": score, "partial_answer": str(obj.get("partial_answer") or "")}


def global_ask_reduce_prepare(
    query: str,
    scored_partials: list[dict],
    char_budget: int = 8000,
) -> dict:
    """Phase 2 of global ask: drop-zero, sort-desc, budget-fill, build REDUCE.

    Args:
        query: the original question.
        scored_partials: list of {"community_id", "score", "partial_answer"}
            (one per map unit; the skill builds this from parse_map_response).
        char_budget: max characters of partials to include in the reduce prompt.

    Returns {"status": "ready" | "no_signal", "query", "kept": [...],
             "reduce_prompt": <str>}.

    `no_signal` when every partial scored 0 (nothing relevant) — the skill
    reports that and stops.
    """
    require_bootstrap()
    # Drop zeros, sort by score desc (tie-break community_id for determinism).
    kept = [p for p in scored_partials if int(p.get("score", 0)) > 0]
    kept.sort(key=lambda p: (-int(p["score"]), p.get("community_id", "")))
    if not kept:
        return {"status": "no_signal", "query": query, "kept": [], "reduce_prompt": ""}

    blocks: list[str] = []
    used = 0
    for p in kept:
        block = (
            f"[{p.get('community_id', '')}] (score={p['score']}) "
            f"{p.get('partial_answer', '')}".strip()
        )
        if used + len(block) > char_budget and blocks:
            break
        blocks.append(block)
        used += len(block)

    template = (PROMPTS_DIR / "global_reduce.md").read_text(encoding="utf-8")
    # Substitute the trusted PARTIALS body FIRST and the user-supplied QUERY
    # LAST so a query containing a literal "{{PARTIALS}}" token can never be
    # re-expanded.
    reduce_prompt = template.replace("{{PARTIALS}}", "\n\n".join(blocks)).replace(
        "{{QUERY}}", query
    )
    return {"status": "ready", "query": query, "kept": kept, "reduce_prompt": reduce_prompt}


def local_ask(
    query: str,
    seed_limit: int = 5,
    hops: int = 1,
    with_embedding: bool = True,
) -> dict:
    """Local / neighborhood retrieval: seed on similar docs, expand via the
    relation graph, attach the seeds' community reports.

    Steps:
      1. Seed: top-`seed_limit` documents by cosine to the query embedding
         (falls back to FTS-less empty seeds if embeddings are unavailable and
         no seed_ids can be derived).
      2. Expand: walk `relations` up to `hops` from the seeds to gather the
         neighborhood.
      3. Communities: for every doc in seeds+neighborhood, attach the
         community_report of the community it belongs to (deduped).

    Returns {"status": "ready", "query", "seeds": [...index_ids],
             "neighborhood": [...index_ids], "documents": [{index_id,
             searchable}], "community_reports": [{community_id, title,
             summary}]}.

    This assembles context; the skill dispatches a single answering subagent
    over `documents` + `community_reports`. Degrades: no embeddings / empty
    graph -> empty seeds/neighborhood, no crash.

    Raises embeddings.EmbeddingUnavailable only if the caller did not request
    with_embedding=False AND seeding by embedding fails — callers typically
    pass with_embedding and wrap in try/except, matching the flat ask path.
    """
    require_bootstrap()
    from scripts import embeddings

    index_db = str(memex_home() / "index.db")

    # 1. Seed by cosine similarity to the query.
    seeds: list[str] = []
    if with_embedding:
        qvec = embeddings.encode(query)  # may raise EmbeddingUnavailable
        conn = get_connection(index_db)
        try:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT index_id, embedding FROM documents WHERE embedding IS NOT NULL"
                )
            ]
        finally:
            conn.close()
        scored = []
        for r in rows:
            if r["embedding"]:
                scored.append((embeddings.cosine(qvec, r["embedding"]), r["index_id"]))
        scored.sort(key=lambda t: (-t[0], t[1]))
        seeds = [idx for _s, idx in scored[:seed_limit]]

    # 2. Expand the neighborhood over `relations`.
    neighborhood: list[str] = []
    if seeds:
        conn = get_connection(index_db)
        try:
            frontier = set(seeds)
            visited = set(seeds)
            for _ in range(max(0, hops)):
                if not frontier:
                    break
                placeholders = ",".join("?" for _ in frontier)
                # nosec B608 - placeholders are '?' literals; values parameterized
                next_rows = conn.execute(
                    f"SELECT to_index_id AS nb FROM relations WHERE from_index_id IN ({placeholders}) "  # nosec B608
                    f"UNION SELECT from_index_id AS nb FROM relations WHERE to_index_id IN ({placeholders})",  # nosec B608
                    (*frontier, *frontier),
                ).fetchall()
                new_frontier = {r["nb"] for r in next_rows} - visited
                neighborhood.extend(sorted(new_frontier))
                visited |= new_frontier
                frontier = new_frontier
        finally:
            conn.close()

    all_ids = list(dict.fromkeys([*seeds, *neighborhood]))  # ordered dedup

    # 3. Documents + their community reports.
    documents: list[dict] = []
    report_ids: list[str] = []
    if all_ids:
        conn = get_connection(index_db)
        try:
            placeholders = ",".join("?" for _ in all_ids)
            # nosec B608 - placeholders are '?' literals; values parameterized
            for r in conn.execute(
                f"SELECT index_id, searchable FROM documents WHERE index_id IN ({placeholders})",  # nosec B608
                tuple(all_ids),
            ):
                documents.append({"index_id": r["index_id"], "searchable": r["searchable"]})
            # Community reports for communities containing any of these docs.
            for r in conn.execute(
                f"SELECT DISTINCT cm.community_id FROM community_members cm "  # nosec B608
                f"WHERE cm.index_id IN ({placeholders})",
                tuple(all_ids),
            ):
                report_ids.append(r["community_id"])
        finally:
            conn.close()

    community_reports: list[dict] = []
    if report_ids:
        conn = get_connection(index_db)
        try:
            placeholders = ",".join("?" for _ in report_ids)
            # nosec B608 - placeholders are '?' literals; values parameterized
            for r in conn.execute(
                f"SELECT community_id, title, summary FROM community_reports "  # nosec B608
                f"WHERE community_id IN ({placeholders}) ORDER BY rating DESC, community_id",
                tuple(report_ids),
            ):
                community_reports.append(dict(r))
        finally:
            conn.close()

    return {
        "status": "ready",
        "query": query,
        "seeds": seeds,
        "neighborhood": neighborhood,
        "documents": documents,
        "community_reports": community_reports,
    }


# ── lint (no LLM; Data Steward audit) ──────────────────────────────────────


def lint() -> str:
    """Run a Data Steward audit and return the report path."""
    require_bootstrap()
    index_db = str(memex_home() / "index.db")
    return data_steward.audit(index_db)


# ── synthesize (Synthesizer — Phase 3 Option-B refactor) ───────────────────


def synthesize_prepare(
    topic: str,
    input_index_ids: list[str],
    caller_agent_id: str,
) -> dict:
    """Phase 1 of brain synthesize: fetch source bodies, build Synthesizer prompt.

    Returns {"status": "ready",
             "topic": <str>,
             "input_index_ids": <list[str]>,
             "caller_agent_id": <id>,
             "sources": [{"index_id", "body", "title"}, ...],
             "synthesizer_prompt": <full Task-tool prompt for the Synthesizer>}.

    Skill markdown dispatches the Synthesizer subagent (subagent_type=
    general-purpose, prompt=synthesizer_prompt), receives the synthesis
    body, then dispatches the Librarian subagent to classify the synthesis,
    then calls synthesize_complete().
    """
    require_bootstrap()
    sources = _fetch_source_bodies(input_index_ids)
    sources_md = "\n\n".join(
        [f"### [{s['index_id']}] {s.get('title', '')}\n\n{s['body']}" for s in sources]
    )

    template = (PROMPTS_DIR / "synthesizer.md").read_text(encoding="utf-8")
    synthesizer_prompt = template.replace("{{TOPIC}}", topic).replace("{{SOURCES}}", sources_md)

    return {
        "status": "ready",
        "topic": topic,
        "input_index_ids": list(input_index_ids),
        "caller_agent_id": caller_agent_id,
        "sources": sources,
        "synthesizer_prompt": synthesizer_prompt,
    }


def synthesize_complete(
    prepare_result: dict,
    synthesis_body: str,
    librarian_output: dict,
    embedding: bytes | None = None,
) -> dict:
    """Phase 3 of brain synthesize: persist the synthesis + index entry.

    Args:
        prepare_result: dict from synthesize_prepare() with status="ready".
        synthesis_body: text returned by the Synthesizer subagent.
        librarian_output: parsed JSON from librarian.parse_response() applied
            to the Librarian subagent's classification of `synthesis_body`.
        embedding: optional embedding of librarian_output["searchable"].

    Augments the Librarian's relations with one `synthesizes` edge per
    input_index_id (deterministic — we know what got synthesized; the
    Librarian's relations are kept for any additional cross-references it
    inferred from the synthesis text).

    Returns {"status": "synthesized", **librarian_output_with_relations,
             "row_id": ...}.

    Raises:
        ValueError: prepare_result is not "ready", or librarian_output malformed.
    """
    if prepare_result.get("status") != "ready":
        raise ValueError(
            f"synthesize_complete called with prepare_result.status="
            f"{prepare_result.get('status')!r}; expected 'ready'"
        )
    require_bootstrap()

    # Auto-add `synthesizes` relations for each input. These are deterministic
    # (we know the inputs from prepare_result) — don't rely on the Librarian
    # to rediscover them. Merge with whatever the Librarian found, dedup by
    # (to_index_id, rel_type).
    enriched_relations = list(librarian_output.get("relations") or [])
    existing = {(r["to_index_id"], r["rel_type"]) for r in enriched_relations}
    for input_id in prepare_result["input_index_ids"]:
        key = (input_id, "synthesizes")
        if key not in existing:
            enriched_relations.append(
                {
                    "to_index_id": input_id,
                    "rel_type": "synthesizes",
                }
            )
            existing.add(key)
    enriched_output = {**librarian_output, "relations": enriched_relations}

    payload = {
        "topic": prepare_result["topic"],
        "body": synthesis_body,
        "inputs_json": json.dumps(prepare_result["input_index_ids"]),
        "created_by": prepare_result["caller_agent_id"],
    }

    result = librarian.write_entry(
        payload=payload,
        librarian_output=enriched_output,
        target_store="article",
        target_table="syntheses",
        caller_agent_id=prepare_result["caller_agent_id"],
        embedding=embedding,
    )
    return {"status": "synthesized", **result}
