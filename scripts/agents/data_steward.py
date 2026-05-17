"""Data Steward — periodic integrity auditor.

Detects:
  - Orphans: documents row references a store/table/row that doesn't exist
  - Reverse orphans: a store row with an index_id column whose value is not in documents
  - Broken relations: relations row pointing to a nonexistent index_id

Writes structured audit reports to ~/.memex/audits/AUD-YYYY-MM-DD-NNN.md.
Never auto-fixes. Reports findings + recommended actions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scripts import registry
from scripts.db import get_connection, memex_home, safe_identifier


def _index_conn(index_db: str):
    return get_connection(index_db)


def find_orphans(index_db: str) -> list[dict]:
    """Find documents rows whose (store, table, row_id) does not resolve to
    an existing row in the target store."""
    conn = _index_conn(index_db)
    docs = [
        dict(r) for r in conn.execute("SELECT index_id, store, table_name, row_id FROM documents")
    ]
    conn.close()

    orphans = []
    for d in docs:
        rec = registry.get_store(d["store"])
        if rec is None:
            orphans.append({**d, "reason": f"store '{d['store']}' not registered"})
            continue
        target_conn = get_connection(rec["path"])
        try:
            safe_table = safe_identifier(d["table_name"])
            row = target_conn.execute(
                f"SELECT 1 FROM {safe_table} WHERE id = ?",  # nosec B608 - identifier validated
                (d["row_id"],),
            ).fetchone()
            if row is None:
                orphans.append({**d, "reason": "row_id not found in target table"})
        except Exception as e:
            orphans.append({**d, "reason": f"query error: {e}"})
        finally:
            target_conn.close()
    return orphans


def find_reverse_orphans(index_db: str, store: str, table: str) -> list[dict]:
    """Find rows in the named store/table with an index_id that doesn't
    appear in documents."""
    rec = registry.get_store(store)
    if rec is None:
        return []

    store_conn = get_connection(rec["path"])
    try:
        safe_table = safe_identifier(table)
        rows = [
            dict(r)
            for r in store_conn.execute(
                f"SELECT id, index_id FROM {safe_table} WHERE index_id IS NOT NULL"  # nosec B608 - identifier validated
            )
        ]
    except Exception:
        store_conn.close()
        return []
    store_conn.close()

    if not rows:
        return []

    conn = _index_conn(index_db)
    indexed_ids = {r["index_id"] for r in conn.execute("SELECT index_id FROM documents")}
    conn.close()

    return [
        {"index_id": r["index_id"], "row_id": r["id"], "store": store, "table_name": table}
        for r in rows
        if r["index_id"] not in indexed_ids
    ]


def find_broken_relations(index_db: str) -> list[dict]:
    """Find relations rows whose from_index_id or to_index_id is not in documents."""
    conn = _index_conn(index_db)
    broken = [
        dict(r)
        for r in conn.execute("""
        SELECT r.from_index_id, r.to_index_id, r.rel_type
        FROM relations r
        LEFT JOIN documents df ON df.index_id = r.from_index_id
        LEFT JOIN documents dt ON dt.index_id = r.to_index_id
        WHERE df.index_id IS NULL OR dt.index_id IS NULL
    """)
    ]
    conn.close()
    return broken


def audit(index_db: str) -> str:
    """Run a full audit and write a report. Returns the report path."""
    orphans = find_orphans(index_db)
    broken = find_broken_relations(index_db)

    audits_dir = memex_home() / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Find next sequential N for today
    existing = list(audits_dir.glob(f"AUD-{date_str}-*.md"))
    n = len(existing) + 1
    report_path = audits_dir / f"AUD-{date_str}-{n:03d}.md"

    findings = []
    for o in orphans:
        findings.append(
            {
                "severity": 3,
                "category": "orphan",
                "detail": f"index_id `{o['index_id']}` -> {o['store']}/{o['table_name']}/{o['row_id']} : {o['reason']}",
                "recommendation": "Re-attempt target store write, OR delete the documents row.",
            }
        )
    for b in broken:
        findings.append(
            {
                "severity": 4,
                "category": "broken_relation",
                "detail": f"{b['from_index_id']} -[{b['rel_type']}]-> {b['to_index_id']} (one or both index_ids missing)",
                "recommendation": "Delete the broken relations row.",
            }
        )

    lines = [
        f"# Audit Report — {report_path.name}",
        "",
        f"Audit run at: {datetime.now(timezone.utc).isoformat()}",
        f"Audited DB: {index_db}",
        "",
        "## Summary",
        "",
        f"- Orphans found: {len(orphans)}",
        f"- Broken relations found: {len(broken)}",
        f"- Total findings: {len(findings)}",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("(no findings)")
    else:
        for i, f in enumerate(findings, 1):
            lines.append(f"### Finding {i} (Severity {f['severity']}, {f['category']})")
            lines.append("")
            lines.append(f"**Detail:** {f['detail']}")
            lines.append("")
            lines.append(f"**Recommendation:** {f['recommendation']}")
            lines.append("")

    report_path.write_text("\n".join(lines))
    return str(report_path)


class OrphanNotFoundError(Exception):
    """Raised when reconcile_orphan() is called for an index_id that either
    doesn't exist in documents or — for `repair` — is already linked
    (row_id is non-empty, so it's not the orphan class repair handles)."""

    def __init__(self, index_id: str, reason: str = "no documents row"):
        self.index_id = index_id
        self.reason = reason
        super().__init__(f"orphan not found for index_id={index_id!r} ({reason})")


def _append_audit(entry: str) -> None:
    audits_dir = memex_home() / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)
    log_path = audits_dir / "reconciliation-log.md"
    with open(log_path, "a") as f:
        f.write(entry)


def reconcile_orphan(
    index_id: str,
    action: str,
    note_text: str | None = None,
    repair_row_id: str | None = None,
) -> dict:
    """Resolve a flagged orphan.

    Actions:
      - delete-index: remove the documents row AND its relations (target row already gone)
      - repair: backfill documents.row_id from a known target PK (forward-orphan
        where the target row exists but the link was never written). Requires
        repair_row_id; validates the target row exists in the registered store.
      - reindex: re-run Librarian on the orphaned target row (Plan 3+; raises
        NotImplementedError for now if the target row also missing)
      - note: leave as-is but record acknowledgment in audits/

    Raises OrphanNotFoundError when index_id is not present in documents (all
    actions), or for `repair` when the row's row_id is already non-empty.

    Returns dict describing the action taken.
    """
    valid_actions = {"delete-index", "repair", "reindex", "note"}
    if action not in valid_actions:
        raise ValueError(f"Unknown action: {action}. Valid: {valid_actions}")

    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    row = conn.execute(
        "SELECT store, table_name, row_id FROM documents WHERE index_id = ?",
        (index_id,),
    ).fetchone()
    conn.close()
    if row is None:
        raise OrphanNotFoundError(index_id)

    if action == "delete-index":
        conn = get_connection(index_db)
        conn.execute(
            "DELETE FROM relations WHERE from_index_id = ? OR to_index_id = ?",
            (index_id, index_id),
        )
        conn.execute("DELETE FROM documents WHERE index_id = ?", (index_id,))
        conn.commit()
        conn.close()
        _append_audit(
            f"\n- {datetime.now(timezone.utc).isoformat()} | index_id={index_id} | "
            f"action=delete-index | result=removed\n"
        )
        return {"action": "delete-index", "index_id": index_id, "result": "removed"}

    elif action == "repair":
        if not repair_row_id:
            raise ValueError("repair action requires repair_row_id")
        if row["row_id"]:
            raise OrphanNotFoundError(
                index_id,
                reason=f"row_id already populated ({row['row_id']!r}); not a link-missing orphan",
            )
        store_name = row["store"]
        table_name = row["table_name"]
        rec = registry.get_store(store_name)
        if rec is None:
            raise ValueError(f"store '{store_name}' not registered")
        safe_table = safe_identifier(table_name)
        target_conn = get_connection(rec["path"])
        try:
            target = target_conn.execute(
                f"SELECT 1 FROM {safe_table} WHERE id = ?",  # nosec B608 - identifier validated
                (repair_row_id,),
            ).fetchone()
        finally:
            target_conn.close()
        if target is None:
            raise ValueError(
                f"target row not found: store={store_name} table={table_name} id={repair_row_id}"
            )
        conn = get_connection(index_db)
        conn.execute(
            "UPDATE documents SET row_id = ? WHERE index_id = ?",
            (repair_row_id, index_id),
        )
        conn.commit()
        conn.close()
        _append_audit(
            f"\n- {datetime.now(timezone.utc).isoformat()} | index_id={index_id} | "
            f"action=repair | store={store_name} | table={table_name} | "
            f"row_id={repair_row_id}\n"
        )
        return {
            "action": "repair",
            "index_id": index_id,
            "row_id": repair_row_id,
            "result": "linked",
        }

    elif action == "note":
        _append_audit(
            f"\n- {datetime.now(timezone.utc).isoformat()} | index_id={index_id} | "
            f"action=note | text={note_text or ''}\n"
        )
        return {"action": "note", "index_id": index_id, "result": "logged"}

    elif action == "reindex":
        # Reverse-orphan case: row exists in target store but not in index.
        # Full implementation would re-invoke Librarian on the target row.
        # Plan 3 stub: raise NotImplementedError pointing to Plan 4 enhancement.
        raise NotImplementedError("reindex action requires Plan 4 re-embedding tooling")
