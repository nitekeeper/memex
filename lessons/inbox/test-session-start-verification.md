---
id: memex:lesson:test-session-start-verification
title: TEST ARTIFACT — inbox triage should run before any session work begins
stream: inbox
status: draft
tags: [test-artifact, inbox-triage, session-start]
created: 2026-05-11
---

## Observation

**THIS IS A TEST ARTIFACT. Discard it. Do not promote.**

During session bootstrap, the queue-processing pass should evaluate all `draft` lessons in `lessons/inbox/` before other work begins. This lesson exists solely to confirm that pass runs and that the discard path is exercised. It duplicates content already covered by the `inbox-raw-wiki-pipeline` wiki entry (see `.ai/wiki/inbox-raw-wiki-pipeline.md`) and is therefore a discard candidate on two grounds: (1) it is a synthetic test fixture, and (2) its substance — that inbox items must be triaged before they accumulate — is already captured in the wiki.

## Why it matters

If this lesson is still present at the end of a session without a discard record, the session-start queue-processing pass did not run. A summary that mentions discarding this artifact confirms the pass ran and the discard heuristic evaluated it correctly.

## How to apply

No action required for this lesson itself — it is a canary. If the pass runs correctly:

1. It finds this file (status: draft, stream: inbox).
2. It evaluates the content against the existing wiki.
3. It determines the substance duplicates `inbox-raw-wiki-pipeline` and the file is explicitly a test artifact.
4. It records a discard and moves on.

If the pass does not discard this file, investigate whether the session-start hook is wired correctly and whether the discard heuristic checks for the `test-artifact` tag or the explicit marker in the Observation section.
