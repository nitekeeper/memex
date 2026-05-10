# ask — Reference

## search.py CLI

```
python scripts/search.py <ai_dir> <query> [--limit N] [--status STATUS] [--tag TAG]
```

| Argument | Required | Notes |
|---|---|---|
| `ai_dir` | yes | Path to the `.ai/` directory. DB resolved as `<ai_dir>/memex.db`. |
| `query` | yes | FTS5 search string. Quote if it contains spaces. |
| `--limit` | no | Max results returned. Default: 10. |
| `--status` | no | Filter by status: `draft`, `approved`, or `archived`. |
| `--tag` | no | Filter by tag. Repeatable: `--tag auth --tag session`. |

Run from the confirmed project root. Pass the `.ai/` directory as `<ai_dir>` — not the wiki subdirectory.

---

## Output JSON shape

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

**`score`**: BM25 relevance score. Lower (more negative) = more relevant. Do not use as a threshold — read the content and judge sufficiency.

**`snippet`**: FTS5 excerpt with matched terms in brackets. Use to decide whether to read the full page via the Read tool.

**`file_path`**: relative to the project root. Prepend the project root to form an absolute path for the Read tool.

---

## Disclosure block (Tier 3)

Append verbatim after every Tier 3 answer. No exceptions. No rewording.

```
---
**Source:** Model knowledge
**Confidence:** <N>%
**Note:** This answer was not found in the project wiki or via web search. It is based on
training knowledge and may be incomplete, outdated, or incorrect. Verify before acting on it.
---
```

`<N>` = honest self-assessment integer 0–100.

---

## Tier decision summary

| Tier | Trigger | Tool |
|---|---|---|
| 1 — Local wiki | Always first (unless DB absent) | `scripts/search.py` |
| 2 — Web search | Tier 1 insufficient | `WebSearch` |
| 3 — Model knowledge | Tier 2 returns no usable results | (none — model answers) |

---

## Capture offer (Tier 2 only)

After a Tier 2 answer, offer to capture findings that are:
- Durable: relevant beyond this session
- Project-relevant: design decisions, architecture patterns, API contracts

Do NOT offer to capture: one-off error fixes, environment-specific steps, or ephemeral troubleshooting.

Wait for explicit user approval before invoking capture. Normal capture approval gate applies.
