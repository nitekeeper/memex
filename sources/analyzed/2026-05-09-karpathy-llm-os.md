---
id: source:karpathy-llm-os
slug: karpathy-llm-os
title: "LLM OS — kernel process framing"
type: article
authors: [Andrej Karpathy]
url: "https://x.com/karpathy/status/1707437820045062561"
captured: 2026-05-09
status: analyzed
relevance-to: [memex]
tags: [llm-os, memory, context-window, architecture, operating-system]
informs-decisions: []
---

# LLM OS — kernel process framing — Andrej Karpathy (2023)

*Primary source: X post (Sept 2023) + "Intro to Large Language Models" talk (Nov 2023, YouTube). X post is paywalled; framing reconstructed from talk summary and secondary coverage.*

## Summary

Karpathy proposes reconceptualizing LLMs not as chatbots but as "the kernel process of a new Operating System." The LLM coordinates resources — memory, storage, tools, I/O — the way an OS kernel manages hardware. The context window is RAM: fast, small, immediate. Persistent storage (internet, local files, embeddings) is the disk. The LLM "pages" information in and out of the context window to perform tasks, just as an OS kernel manages memory pages. This framing has direct architectural implications: the memory/storage hierarchy is not incidental — it is load-bearing infrastructure. He identifies self-improvement mechanisms as a first-class component of the envisioned LLM OS.

## Key claims

- LLMs should not be thought of as chatbots but as "the kernel process of a new Operating System."
- Context window = RAM: fast, finite, immediate access; everything must be paged in to be used.
- Internet/local files = hard disk: persistent, large-capacity, slower to access.
- The LLM OS orchestrates: I/O across modalities (text, audio, vision, image), code interpreter, browser/internet, embeddings database for memory, external tools (search, calculator, Python).
- Self-improvement mechanisms are listed as a component of the envisioned LLM OS — not a feature, a capability class.
- The LLM ecosystem mirrors the OS landscape: proprietary models (GPT, Claude) are like Windows/macOS; open-source (Llama-based) is like Linux.
- Looking at LLMs as chatbots is like looking at early computers as calculators: missing the entire paradigm.
- "The LLM tries to page relevant information in and out of its context window to perform your task, as the kernel process in an operating system manages its resources."

## Relevance

**To Memex's core design:**

This framing is the strongest single justification for Memex as an architectural layer rather than a nice-to-have. If the LLM is the kernel, Memex is a first-class component of the storage/memory subsystem — not bolted on, but structurally necessary. The "disk" in the LLM OS needs to be structured, queryable, and coherent for the kernel to function well. An unstructured, stale, unmaintained project wiki is the equivalent of a corrupted filesystem.

The "paging" metaphor is load-bearing for Memex's design: because the context window is finite and ephemeral (RAM), the LLM must selectively page in what it needs from the disk. This means:
- What's on disk must be accurate (staleness matters more than volume)
- What's on disk must be queryable (FTS5 + future vector search)
- What's on disk must be granular (small, focused pages that can be paged in selectively)

These translate directly to Memex's `synced-at-commit` staleness signal, its SQLite + FTS5 schema, and the "write small, link generously" wiki principle.

**To Memex's self-improvement loop:**

Self-improvement is listed as a first-class LLM OS capability — not an afterthought. This validates Memex's lesson capture/review/promotion loop as infrastructure-level, not optional.

## Open questions

- The LLM OS paging metaphor assumes the disk (project wiki) is maintained by *something* — who maintains it? Memex answers this (the AI captures, sync detects staleness, human approves) but the framing doesn't specify. Is this the AI's job, the human's, or a hybrid?
- The "embeddings database" component in the LLM OS is described at a high level. Does Karpathy mean vector search specifically, or any persistent structured store? This affects the Stage 1 (FTS5) vs Stage 2 (vec) prioritization in Memex's db schema.
- The LLM OS framing was articulated in 2023. In the 2026 "agentic engineering" era (see autoresearch source), the LLM is less of a kernel and more of an agent runtime. Does the OS analogy still hold, or has it evolved?

## Excerpts

> "a more complete picture is emerging of LLMs not as a chatbot, but the kernel process of a new Operating System" — X post, Sept 2023

> "The LLM tries to page relevant information in and out of its context window to perform your task, as the kernel process in an operating system manages its resources." — Intro to LLMs talk summary

> LLM OS components (from talk): context window = RAM, internet/local files = hard disk, tools = I/O peripherals, self-improvement = first-class capability class

> On the ecosystem: "distinguishing between proprietary models (GPT, Claude, Bard) and open-source alternatives built around Llama — similar to Windows/macOS versus Linux-based systems"
