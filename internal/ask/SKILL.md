---
description: "Use when the user asks a question about their project and wants an answer drawn from the project wiki first, then the web, then model knowledge. Also use when the user invokes /ask. Do NOT use for writing or updating wiki pages (use capture) or for checking page staleness (use sync)."
---

# ask — tiered knowledge resolution

## Project root detection

A project is detectable if it contains `.ai/wiki/` at its root — check each workspace root at this fixed path only; do not recurse. If no workspace context is available, treat the current working directory as the only root.

- Zero detectable projects (no `.ai/wiki/` found): stop. Tell user: "No project wiki found. Create an `.ai/wiki/` directory in your target project root before running ask."
- Exactly one: proceed. Announce: "Searching `<path>/.ai/`."
- More than one: list the found project paths, numbered. Ask: "Multiple project wikis found — which should I search? Reply with the number or path." Wait for explicit choice.

If `.ai/memex.db` is absent at the confirmed root: note "Wiki found but no DB index — skipping local search." Skip to Tier 2.

---

## Tier 1 — Local wiki

Run `python scripts/search.py .ai/ "<question>" --limit 10` from the confirmed project root. Set the working directory to the confirmed project root before running. (`scripts/search.py` is the memex skill's script — not a script in the user's project.)

On non-zero exit: show stderr to the user; skip to Tier 2.

Parse the JSON output. If `results` is empty: skip to Tier 2.

Read the `snippet` and `file_path` of each result. Use the Read tool to read any pages that look relevant.

**Judge sufficiency**: does the content directly answer the question with enough detail to act on?

- Sufficient: answer the user. Cite each page as `<title>` (`<file_path>`). Stop.
- Not sufficient: escalate to Tier 2.

Do not apply a score threshold. Sufficiency is a judgment call based on content, not `score` value.

---

## Tier 2 — Web search

Run `WebSearch` with the question as the query (refine query as needed for search engines).

If web search is unavailable: note "web search unavailable — answering from training knowledge"; skip to Tier 3.

If no usable results: escalate to Tier 3.

Synthesize an answer. Cite each source URL.

After answering, identify findings that are durable and project-relevant — design decisions, architecture patterns, API contracts. Do NOT flag one-off error fixes or environment-specific troubleshooting steps.

If durable findings exist: offer to capture them. Example: "I found [X] — worth capturing as a wiki entry? I can run /capture now." Wait for user response before invoking capture. Normal capture approval gate applies.

If no durable findings: do not offer capture.

---

## Tier 3 — Model knowledge

Answer from training knowledge.

Append this disclosure block immediately after the answer — no exceptions:

```
---
**Source:** Model knowledge
**Confidence:** <N>%
**Note:** This answer was not found in the project wiki or via web search. It is based on
training knowledge and may be incomplete, outdated, or incorrect. Verify before acting on it.
---
```

`<N>` = honest self-assessment integer 0–100. Do not omit or reword the block.

---

## Escalation rules

- Escalation is agent-driven. No score threshold triggers it.
- Always attempt Tier 1 first (unless DB absent — see root detection).
- Proceed to Tier 2 only when Tier 1 results are insufficient.
- Proceed to Tier 3 only when Tier 2 returns no usable results.
- Never skip a tier without stating why.
