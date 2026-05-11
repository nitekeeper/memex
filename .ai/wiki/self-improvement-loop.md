---
id: memex:wiki:self-improvement-loop
title: Self-improvement loop
status: draft
created: 2026-05-10
updated: 2026-05-10
tags: [memex, architecture, sessions, lessons, wiki]
---

Memex's self-improvement loop converts raw session experience into durable wiki knowledge through four sequential stages, each with a human approval gate.

## Stage 1 — `capture-lesson`

At session end (or on-demand), the AI sweeps the conversation for non-obvious observations: corrections, decisions with a "why," patterns that help a future AI avoid mistakes. Each candidate requires explicit approval before writing to `lessons/inbox/` or `lessons/feedback/` as `status: draft`.

## Stage 2 — `review-lessons`

Draft lessons are surfaced for human review. Each lesson gets a **promote / discard / defer** decision. Promoted lessons move to `lessons/promoted/`; discarded lessons are deleted or retained with a logged reason.

## Stage 3 — `propose-wiki-entry`

Promoted lessons are rewritten into compact wiki prose and proposed for approval before writing to `.ai/wiki/`. The AI synthesizes the lesson's three sections (Observation / Why it matters / How to apply) into a reusable reference entry.

## Stage 4 — `sync` + `review-wiki`

`sync` detects entries whose source files have drifted (via git commit anchoring). `review-wiki` supports ongoing curation — updating or archiving stale entries.

## Key invariant

Every transition requires an explicit human gate. Nothing is promoted, written, or discarded silently. The loop closes when wiki entries are retrieved by `ask` in future sessions, giving the AI continuity across conversations.
