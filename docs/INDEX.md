# Memex Index + Internal Agents (Plan 2)

Plan 2 builds the Memex Index — the mandatory write-path gateway and
read-path retrieval layer — plus the five internal agents.

## What Plan 2 ships

### Internal agents (seeded into agents.db on install)

| Agent | Role | Implementation |
|---|---|---|
| Librarian (Dr. Lakshmi Iyer-Ranganathan) | Librarian | LLM subagent (prompts/librarian.md) + scripts/agents/librarian.py harness |
| Reference Librarian (Dr. Eleanor Whitfield) | Reference Librarian | LLM subagent (prompts/reference_librarian.md) + scripts/agents/reference_librarian.py |
| Archivist (Dr. Heinrich Muhlbauer) | Archivist | Deterministic Python (scripts/agents/archivist.py) |
| Database Administrator (Dr. Rajesh Subramanian) | Database Administrator | Deterministic Python (scripts/agents/dba.py) |
| Data Steward (Dr. Ingrid Bergstrom) | Data Steward | Deterministic Python (scripts/agents/data_steward.py) |

### Skills

Per spec 8.0, the plugin registers only `memex:run`. The 9 procedures
below live at `internal/<category>/<name>/SKILL.md` and are reached on
demand through the routing table inside `skills/run/SKILL.md`.

| Procedure | Path | Purpose |
|---|---|---|
| memex:index:write | internal/index/write/SKILL.md | Mandatory write path: archive -> Librarian -> Core |
| memex:index:search | internal/index/search/SKILL.md | Read path: Reference Librarian -> ranked results |
| memex:index:archive | internal/index/archive/SKILL.md | Explicit raw archive (rare) |
| memex:steward:audit | internal/steward/audit/SKILL.md | Full integrity audit |
| memex:steward:audit-store | internal/steward/audit-store/SKILL.md | Per-store audit |
| memex:steward:reconcile-orphan | internal/steward/reconcile-orphan/SKILL.md | Authorized orphan fix (Plan 3 fully implements) |
| memex:dba:checkpoint | internal/dba/checkpoint/SKILL.md | WAL checkpoint |
| memex:dba:integrity-check | internal/dba/integrity-check/SKILL.md | PRAGMA integrity_check |
| memex:dba:vacuum | internal/dba/vacuum/SKILL.md | VACUUM |

### Data

| File | Contents |
|---|---|
| ~/.memex/index.db | documents + relations + FTS5 + embeddings |
| ~/.memex/raw/ | Content-addressable raw archive |
| ~/.memex/audits/ | Data Steward reports |

## Atomicity contract

Index write commits BEFORE target store write. The brief inconsistency
window means a crash between the two writes leaves an orphan in index.db.
The system is eventually consistent: Data Steward audits detect orphans;
resolution is authorized via memex:steward:reconcile-orphan. Data Steward
reconciles the gap on demand — it never auto-fixes.

## What Plan 2 does NOT ship

- Brain skills (ingest/ask/capture/lint/synthesize) — Plan 3.
- Embedding backfill / re-embed tooling — Plan 4.
- Reconcile-orphan full implementation — Plan 3.
- Onboarding flow for the human user — Plan 3.

## Acceptance criteria

1. `pytest tests/` passes 100% across all test files (Plan 1 + Plan 2).
2. `install.run()` is idempotent and creates index.db + seeds 5 internal agents.
3. The 9 new SKILL.md files exist at `internal/<category>/<name>/SKILL.md` with correct frontmatter.
4. `skills/run/SKILL.md` contains routing entries for all 9 new procedures.
5. `plugin.json` still registers only `memex:run` (no new top-level skills).
6. The end-to-end smoke test in tests/test_smoke_plan2.py passes with mocked LLM.
7. Manual sanity check: invoke Librarian against real Claude API, confirm
   reasonable index_id/domain/relations output on a sample article.
