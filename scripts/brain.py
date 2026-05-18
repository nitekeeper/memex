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
from scripts.db import memex_home, require_bootstrap
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
