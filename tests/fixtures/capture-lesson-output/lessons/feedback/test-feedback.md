---
id: memex:lesson:test-feedback
title: Feedback lessons preserve user direction verbatim
stream: feedback
status: draft
tags: [test, feedback-stream]
created: 2026-05-10
---

## Observation

User stated: "Always route user corrections to feedback, not inbox — I want to be able to find my own directions separately."

## Why it matters

Feedback stream lessons carry higher priority than AI-inferred lessons. Mixing them into inbox makes review harder and risks treating user direction as a mere suggestion.

## How to apply

When the user explicitly states a correction, preference, or direction, route to `lessons/feedback/` not `lessons/inbox/`. Default ambiguous cases to inbox.
