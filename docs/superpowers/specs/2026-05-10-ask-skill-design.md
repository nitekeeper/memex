# ask skill v0 — design spec
_2026-05-10_

## Overview

The `ask` skill is a tiered knowledge resolution pipeline. When the agent or user has a question, `ask` finds the best possible answer by working through three tiers in order, stopping as soon as the agent judges the answer sufficient.

The wiki grows as a side effect: every web-sourced answer that gets captured means the next similar question hits tier 1 instead of tier 2.

---

## Tiers

Escalation is agent-driven: no score threshold triggers it. The agent reads the results from each tier and decides whether they sufficiently answer the question before escalating. This is intentional — BM25 scores are poor proxies for answer quality.

### Tier 1 — Local wiki
Query `memex.db` via `scripts/search.py`. FTS5 BM25-ranked search against `pages_fts`. Returns JSON with ranked results and body snippets. Agent reads results and judges whether they answer the question.

### Tier 2 — Web search
If tier 1 is insufficient, run `WebSearch`. Agent evaluates results, synthesizes an answer, and cites sources. After answering, the agent identifies project-relevant and durable findings and offers to ingest them via the `capture` skill (normal approval gate). Ingest is post-answer — the user gets the answer first.

Only durable, project-relevant findings are capture candidates. One-off error fixes and ephemeral results are not.

### Tier 3 — Model knowledge
If tiers 1 and 2 are both insufficient (or web search is unavailable), the agent answers from training knowledge. A mandatory disclosure block appears after the answer:

```
---
**Source:** Model knowledge
**Confidence:** <N>%
**Note:** This answer was not found in the project wiki or via web search. It is based on
training knowledge and may be incomplete, outdated, or incorrect. Verify before acting on it.
---
```

Confidence is the agent's honest self-assessment — not a formula. Well-documented public technology: high. Private project conventions: low. The block is always shown when tier 3 is used, no exceptions.

---

## Components

| File | Purpose |
|---|---|
| `scripts/search.py` | DB query only. FTS5 MATCH with bm25() ranking and snippet() extraction. Returns JSON to stdout. |
| `skills/ask/SKILL.md` | Agent-facing procedure. Project root detection, tier orchestration, answer formatting, disclosure block. |
| `skills/ask/REFERENCE.md` | Script CLI reference, disclosure block format, error handling table. |
| `tests/test_search_script.py` | Unit tests for search.py. |

No schema changes — `pages_fts` already exists and is populated by `rebuild.py`.

---

## script: search.py

### CLI

```
python scripts/search.py <ai_dir> <query> [--limit N] [--status STATUS] [--tag TAG]
```

- `ai_dir`: path to the project's `.ai/` directory
- `query`: FTS5 search string
- `--limit`: max results (default 10)
- `--status`: filter by status (`draft`, `approved`, `archived`)
- `--tag`: filter by tag (repeatable)

### SQL

```sql
SELECT p.id, p.title, p.file_path, p.status, p.updated,
       snippet(pages_fts, 2, '[', ']', '...', 20) AS snippet,
       bm25(pages_fts) AS score
FROM pages_fts
JOIN pages p ON pages_fts.rowid = p.rowid
WHERE pages_fts MATCH ?
ORDER BY bm25(pages_fts)
LIMIT ?
```

Lower BM25 score = better match (SQLite convention).

### Output (stdout)

```json
{
  "query": "token expiry",
  "results": [
    {
      "id": "myproject:wiki:auth-design",
      "title": "Auth design decisions",
      "file_path": ".ai/wiki/auth-design.md",
      "status": "approved",
      "updated": "2026-05-10",
      "snippet": "...handles [token] [expiry] by refreshing...",
      "score": -1.23
    }
  ]
}
```

Empty `results` array when nothing matches. Non-zero exit + stderr on any error.

---

## Skill: project root detection

Same rules as capture and sync:

- **Zero detectable projects**: stop. Tell user: "No project wiki found. Create an `.ai/wiki/` directory in your target project root before running ask."
- **Exactly one**: proceed automatically. Announce: "Searching `<path>/.ai/`."
- **More than one**: ask the user which project. Wait for explicit choice.

**Additional rule**: if `memex.db` is absent or empty (wiki exists but rebuild hasn't been run), skip tier 1 silently and note: "Wiki found but no DB index — skipping local search." Proceed to tier 2.

---

## Skill: invocation

Triggered when:
- The user explicitly invokes `/ask <question>`
- The agent judges that the project wiki may contain a relevant answer to the user's question

---

## Tests: test_search_script.py

| # | Test | What it verifies |
|---|---|---|
| 1 | Basic match | Single page in DB, query matches title → result returned with correct fields |
| 2 | BM25 ranking | Two pages, one more relevant → higher-ranked page appears first |
| 3 | Snippet extraction | Body contains query terms → snippet includes bracketed highlights |
| 4 | No results | Query matches nothing → empty results array, exit 0 |
| 5 | Status filter | `--status approved` → only approved pages returned |
| 6 | Tags filter | `--tag auth` → only tagged pages returned |
| 7 | Limit | `--limit 3` with 5 matching pages → at most 3 results |
| 8 | DB not found | Non-existent ai_dir → non-zero exit, stderr message |
| 9 | Empty query | Blank string → non-zero exit, stderr message |

Skill behavior (tier escalation, disclosure block) is not unit-tested — it is agent behavior, tested by use.
