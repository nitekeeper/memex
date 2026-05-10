---
id: source:karpathy-autoresearch
slug: karpathy-autoresearch
title: "AutoResearch — the self-improvement loop"
type: article
authors: [Andrej Karpathy]
url: "https://www.nextbigfuture.com/2026/03/andrej-karpathy-on-code-agents-autoresearch-and-the-self-improvement-loopy-era-of-ai.html"
captured: 2026-05-09
status: analyzed
relevance-to: [memex]
tags: [self-improvement, autoresearch, agentic-engineering, loop, evaluation]
informs-decisions: []
---

# AutoResearch — the self-improvement loop — Andrej Karpathy (2026)

*Primary source: NextBigFuture coverage of Karpathy's AutoResearch work (March 2026), cross-referenced with Fortune ("The Karpathy Loop") and StartupHub.ai. Direct Karpathy quotes verified across sources.*

## Summary

Karpathy built AutoResearch: an AI agent that autonomously designs experiments, edits training code, runs experiments, analyzes results, and iterates — closing the research loop entirely. In a two-day run on a 630-line Python training codebase (single GPU), the agent ran 700 experiments and discovered 20 optimizations that improved training efficiency by 11% on a larger model. The underlying insight: any metric that is efficient to evaluate can be autoresearched. The framing: we are entering a "self-improvement loopy era" where the bottleneck shifts from human coding to human judgment at checkpoints. The "Karpathy Loop" is the pattern: one agent, one file, one testable metric, fixed time per experiment.

## Key claims

- AutoResearch: AI agent autonomously runs the full research loop (design → implement → evaluate → iterate) with no human intervention per experiment.
- 700 experiments in 2 days on a single GPU; 20 optimizations discovered; 11% training efficiency gain on a larger model.
- "*any* metric you care about that is reasonably efficient to evaluate...can be autoresearched." — the metric is the key constraint.
- "The goal is not to emulate a single PhD student, it's to emulate a research community of them."
- "All LLM frontier labs will do this. It's the final boss battle."
- The Karpathy Loop (analyst framing): (1) agent modifies a single file, (2) one objectively testable optimization metric, (3) fixed time limits per experiment.
- Agentic engineering era: "humans direct and supervise agents rather than writing code directly." Technical expertise is "still a multiplier, but the bits humans contribute are sparse and rare."
- Manual coding skills are "atrophying because agents (Claude Code, OpenAI Codex, etc.) crossed a coherence threshold around Dec 2025."
- "The old single-file IDE is dead. The new unit is teams of agents."
- The loop does *not* achieve recursive self-improvement — it optimizes a *separate* smaller model, not itself. The loop is bounded.
- "seed for emulating a research community of agents collaborating asynchronously."

## Relevance

**To Memex's self-improvement loop design:**

This is the most directly actionable source for Memex's lesson capture/review/promotion cycle. The "Karpathy Loop" pattern maps cleanly:
- *One file* → one wiki page or lesson entry (bounded scope per iteration)
- *One testable metric* → for lessons: was this promoted? Did it change behavior? For wiki pages: staleness signal (testable via git diff against `describes-files`)
- *Fixed time per experiment* → review cadence (every session close for lessons; quarterly for wiki)

Karpathy's key insight — the metric is the constraint — has a direct implication for Memex: **the quality of the self-improvement loop is bounded by how measurable the improvement signal is.** Staleness is measurable (git). Accuracy and completeness are not (yet). Memex v0 should focus on what it can measure.

**To the broader "why Memex" argument:**

In the agentic era, AI agents modify codebases continuously. "Teams of agents" working asynchronously means project wikis become even more critical: without a reliable, queryable, git-anchored memory layer, agents working in parallel have no shared ground truth. The "research community of agents collaborating asynchronously" needs shared, structured memory. Memex is that layer.

**To Memex's human-in-the-loop design:**

The AutoResearch loop is not fully autonomous: humans provide "critical decisions" even when agents handle 30–50% of workflow. Karpathy's lesson review cadence (not specified explicitly but implied) is human-at-checkpoints, not human-per-step. This validates Memex's model: AI captures → human approves at session close — not human-per-capture.

## Open questions

- What does Karpathy's agent use for project memory between experiment runs? (The AutoResearch setup doesn't seem to use a structured wiki — it infers from the codebase directly. Does this mean Memex-style memory is optional if the codebase is small enough? Probably yes, but Memex targets large, complex projects where direct inference fails.)
- The "testable metric" constraint is strict. For Memex's lesson promotion loop, what is the testable metric beyond "human approved"? Can we instrument something more objective?
- The "coherence threshold" claim (Dec 2025) has direct implications for Memex's target user: if agents are now reliable enough that humans are "directing" rather than "writing," Memex is infrastructure for that direction layer — not a debugging aid for unreliable agents.

## Excerpts

> "*any* metric you care about that is reasonably efficient to evaluate...can be autoresearched."

> "The goal is not to emulate a single PhD student, it's to emulate a research community of them."

> "All LLM frontier labs will do this. It's the final boss battle."

> "the old single-file IDE is dead. The new unit is teams of agents."

> "technical expertise is still a multiplier, but the bits humans contribute are sparse and rare."

> "seed for emulating a research community of agents collaborating asynchronously."
