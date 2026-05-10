---
id: memex:lesson:test-lesson
title: Approval gate must appear before any file write
stream: inbox
status: draft
tags: [test, approval-gate]
created: 2026-05-10
---

## Observation

When implementing skills that write files, the approval gate was skipped in an early prototype, leading to unreviewed writes during testing.

## Why it matters

Without the gate, lesson files accumulate noise — half-formed observations and task-local notes that should have been filtered. The review-lessons skill then has to sift through low-quality candidates.

## How to apply

Always show the approval gate before writing any lesson file, in both on-demand and session-end modes. The gate is the quality filter; it is not optional.
