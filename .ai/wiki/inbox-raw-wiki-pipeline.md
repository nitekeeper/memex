---
id: memex:wiki:inbox-raw-wiki-pipeline
slug: inbox-raw-wiki-pipeline
title: Raw is immutable; wiki is derived
status: approved
tags: [pipeline, ingestion, immutability, wiki-curation]
sources: [source:second-brain-blueprint]
related: []
proposed-in: session:2026-05-09
approved-in: session:2026-05-09
created: 2026-05-09
updated: 2026-05-09
---

# Raw is immutable; wiki is derived

Ingested material flows through three stages: `inbox/` (landed, unprocessed) → `raw/` (immutable archive) → wiki pages (derived artifacts). The source is never modified after archiving. Wiki pages are written *from* raw material, not *over* it.

## Why it matters

Treating wiki pages as edits to the source conflates two things with different purposes: the historical record (what was ingested, verbatim) and the synthesized knowledge (what was understood from it). Keeping them separate means the raw material can always be re-analyzed if the synthesis was wrong, and wiki pages can be regenerated without re-ingesting.

## The three stages

| Stage | Directory | Role | Mutable? |
|---|---|---|---|
| Landing | `inbox/` | Newly arrived; unprocessed | Yes — awaiting triage |
| Archive | `raw/` (or `sources/analyzed/`) | Verbatim record of what was ingested | No — append only |
| Knowledge | wiki pages | Derived synthesis | Yes — updated as understanding improves |

In the framework, `sources/analyzed/` serves the archive role; `wiki/` (or `.ai/wiki/`) serves the derived role.

## How to apply

- When ingesting a source: write the analyzed metadata to `sources/analyzed/`; do not modify it afterward.
- When curating wiki entries: write new pages or update existing ones; never edit the source file to match.
- If a wiki entry is wrong: correct the wiki entry. The source remains as the historical record of what it actually said.
- `inbox/` is a staging area only — nothing lives there permanently.

## Failure modes

- **Editing raw to match the wiki.** Destroys the historical record. Mitigation: treat `sources/analyzed/` as append-only after the `status: analyzed` stamp.
- **Letting `inbox/` accumulate.** Ingestion deferred is ingestion that doesn't happen. Mitigation: ingestion is the session's work, not a staging area (`meta:ingest-source` anti-patterns).
- **Generating wiki pages that can't be traced back to a source.** Mitigation: every wiki entry carries a `sources:` field pointing to the analyzed source(s) that informed it.

## References

- `source:second-brain-blueprint` — inbox/raw/wiki pipeline; "same input → zero state change" hash-check deduplication.
- `meta:ingest-source` — procedure that writes to `sources/analyzed/`.
