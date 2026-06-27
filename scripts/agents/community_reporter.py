"""Community Reporter — Python helpers for bottom-up community summarization.

GraphRAG summarizes each community into a structured report (title, summary,
importance rating, findings). Reports are built BOTTOM-UP:

  - **Leaf communities** (level 0, or any community with no child reports):
    context = member documents' `searchable` text, ordered by node degree
    (most-connected first), packed until a character budget fills.
  - **Higher-level communities:** when a community has children that already
    have reports, those CHILD REPORTS substitute for raw member text once the
    raw text would blow the budget — this is the bottom-up roll-up that keeps
    the prompt bounded as the hierarchy grows.

This is the Option-B pattern: `report_prepare(community_id)` builds the
subagent prompt; the skill dispatches the reporter subagent; `parse_report`
validates the structured JSON; `report_complete` persists to
`community_reports` (+ an embedding of the summary, EmbeddingUnavailable-
tolerant). Bounded to ONE LLM call per community.

DERIVED artifact (M3): community reports summarize already-indexed documents;
they are not a document-ingest path. Document writes still go through the
Librarian.

Public API:
    report_prepare(community_id, char_budget=8000) -> dict
    parse_report(response_text) -> dict
    report_complete(prepare_result, report, embedding=None) -> dict
    stale_community_ids() -> list[str]
"""

from __future__ import annotations

import json

from scripts.db import get_connection, memex_home
from scripts.paths import PROMPTS_DIR

_DEFAULT_CHAR_BUDGET = 8000


class CommunityNotFoundError(Exception):
    """Raised by report_prepare when the community_id has no members."""


def _node_degrees(conn, index_ids: list[str]) -> dict[str, float]:
    """Weighted degree per node across ALL rel_types (both directions)."""
    deg: dict[str, float] = dict.fromkeys(index_ids, 0.0)
    member_set = set(index_ids)
    for r in conn.execute("SELECT from_index_id, to_index_id, confidence FROM relations"):
        a, b = r["from_index_id"], r["to_index_id"]
        w = 1.0 if r["confidence"] is None else float(r["confidence"])
        if a in member_set:
            deg[a] += w
        if b in member_set:
            deg[b] += w
    return deg


def _child_reports(conn, community_id: str) -> list[dict]:
    """Return existing reports of this community's direct children."""
    rows = conn.execute(
        "SELECT cr.community_id, cr.title, cr.summary FROM community_reports cr "
        "JOIN communities c ON c.community_id = cr.community_id "
        "WHERE c.parent = ?",
        (community_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def report_prepare(community_id: str, char_budget: int = _DEFAULT_CHAR_BUDGET) -> dict:
    """Phase 1: assemble the bottom-up context + build the reporter prompt.

    Returns {"status": "ready", "community_id", "level", "context_blocks",
             "truncated", "used_child_reports", "subagent_prompt",
             "member_index_ids"}.

    Raises CommunityNotFoundError if the community has no members.
    """
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    try:
        crow = conn.execute(
            "SELECT community_id, level FROM communities WHERE community_id = ?",
            (community_id,),
        ).fetchone()
        members = [
            r["index_id"]
            for r in conn.execute(
                "SELECT index_id FROM community_members WHERE community_id = ?",
                (community_id,),
            )
        ]
        if not members:
            raise CommunityNotFoundError(f"No members for community {community_id!r}")
        level = crow["level"] if crow else 0

        # Order members by degree (most-connected first), tie-break index_id.
        deg = _node_degrees(conn, members)
        ordered = sorted(members, key=lambda idx: (-deg.get(idx, 0.0), idx))

        # Fetch searchable text for ordered members.
        text_by_id: dict[str, str] = {}
        for idx in ordered:
            row = conn.execute(
                "SELECT searchable FROM documents WHERE index_id = ?", (idx,)
            ).fetchone()
            text_by_id[idx] = (row["searchable"] if row and row["searchable"] else "") or ""

        child_reports = _child_reports(conn, community_id)
    finally:
        conn.close()

    # Build context bottom-up under the char budget.
    blocks: list[str] = []
    used = 0
    truncated = False
    for idx in ordered:
        text = text_by_id[idx]
        block = f"[{idx}] {text}".strip()
        if used + len(block) > char_budget and blocks:
            truncated = True
            break
        blocks.append(block)
        used += len(block)

    # If we truncated and child reports exist, append child-report summaries as
    # the bottom-up roll-up substitute for the dropped raw member text.
    used_child_reports = False
    if truncated and child_reports:
        for cr in child_reports:
            block = f"[child:{cr['community_id']}] {cr['title']}: {cr['summary']}".strip()
            if used + len(block) > char_budget and blocks:
                break
            blocks.append(block)
            used += len(block)
            used_child_reports = True

    context = "\n\n".join(blocks)
    template = (PROMPTS_DIR / "community_reporter.md").read_text(encoding="utf-8")
    subagent_prompt = (
        template.replace("{{COMMUNITY_ID}}", community_id)
        .replace("{{LEVEL}}", str(level))
        .replace("{{MEMBER_IDS}}", json.dumps(ordered, separators=(",", ":")))
        .replace("{{CONTEXT}}", context)
    )

    return {
        "status": "ready",
        "community_id": community_id,
        "level": level,
        "member_index_ids": ordered,
        "context_blocks": blocks,
        "truncated": truncated,
        "used_child_reports": used_child_reports,
        "subagent_prompt": subagent_prompt,
    }


def parse_report(response_text: str) -> dict:
    """Parse + validate the reporter subagent's structured JSON report.

    Required: title (str), summary (str), rating (number 0-10),
    findings (list of {summary, explanation}).

    Strips markdown code fences. Coerces rating into [0, 10]. Raises
    ValueError on malformed input.
    """
    s = response_text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0] if s.endswith("```") else s
    obj = json.loads(s.strip())
    if not isinstance(obj, dict):
        raise ValueError(f"community report must be a JSON object, got {type(obj).__name__}")
    for field in ("title", "summary", "rating", "findings"):
        if field not in obj:
            raise ValueError(f"community report missing field: {field!r}")
    if not isinstance(obj["title"], str) or not isinstance(obj["summary"], str):
        raise ValueError("community report title/summary must be strings")
    try:
        rating = float(obj["rating"])
    except (TypeError, ValueError) as e:
        raise ValueError(f"community report rating not numeric: {obj['rating']!r}") from e
    rating = max(0.0, min(10.0, rating))
    findings = obj["findings"]
    if not isinstance(findings, list):
        raise ValueError("community report findings must be a list")
    norm_findings = []
    for f in findings:
        if not isinstance(f, dict) or "summary" not in f or "explanation" not in f:
            raise ValueError("each finding must be {summary, explanation}")
        norm_findings.append({"summary": str(f["summary"]), "explanation": str(f["explanation"])})
    return {
        "title": obj["title"],
        "summary": obj["summary"],
        "rating": rating,
        "findings": norm_findings,
    }


def report_complete(
    prepare_result: dict,
    report: dict,
    embedding: bytes | None = None,
) -> dict:
    """Phase 2: persist a parsed report to `community_reports`.

    Args:
        prepare_result: dict from report_prepare() with status="ready".
        report: dict from parse_report().
        embedding: optional float32 BLOB of the report summary. If None, the
            caller did not (or could not) embed; persisted as NULL. The skill
            embeds report["summary"] and tolerates EmbeddingUnavailable.

    Returns {"status": "reported", "community_id": ..., "rating": ...}.
    Upserts (one report per community).
    """
    if prepare_result.get("status") != "ready":
        raise ValueError(
            f"report_complete called with prepare_result.status="
            f"{prepare_result.get('status')!r}; expected 'ready'"
        )
    community_id = prepare_result["community_id"]
    level = prepare_result["level"]
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO community_reports "
            "(community_id, level, title, summary, rating, findings, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                community_id,
                level,
                report["title"],
                report["summary"],
                report["rating"],
                json.dumps(report["findings"]),
                embedding,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "status": "reported",
        "community_id": community_id,
        "rating": report["rating"],
    }


def stale_community_ids() -> list[str]:
    """Return community_ids that have NO report yet (lazy/incremental).

    A community is 'stale' if it exists in `communities` but has no row in
    `community_reports`. The maintenance path generates reports only for
    these, bounding work to one LLM call per missing community.
    """
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    try:
        rows = conn.execute(
            "SELECT c.community_id FROM communities c "
            "LEFT JOIN community_reports cr ON cr.community_id = c.community_id "
            "WHERE cr.community_id IS NULL ORDER BY c.level DESC, c.community_id"
        ).fetchall()
        return [r["community_id"] for r in rows]
    finally:
        conn.close()
