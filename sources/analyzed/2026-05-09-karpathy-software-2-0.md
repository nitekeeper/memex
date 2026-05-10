---
id: source:karpathy-software-2-0
slug: karpathy-software-2-0
title: "Software 2.0"
type: article
authors: [Andrej Karpathy]
url: "https://karpathy.medium.com/software-2-0-a64152b37c35"
captured: 2026-05-09
status: analyzed
relevance-to: [memex]
tags: [software-paradigm, datasets, tooling, neural-networks, programming]
informs-decisions: []
---

# Software 2.0 — Andrej Karpathy (2017)

## Summary

Karpathy argues that neural networks represent not just a better classifier but a fundamental shift in the nature of software itself. Software 1.0 is explicit code written by humans; Software 2.0 is weights — a program defined by a dataset and an architecture, compiled by the training process. The shift is already underway across vision, speech, translation, and games. The deeper implication: the "programming" activity in SW 2.0 is dataset accumulation, curation, and labeling, and the tooling ecosystem for that activity barely exists yet.

## Key claims

- "Neural networks are not just another classifier, they represent the beginning of a fundamental shift in how we develop software. They are Software 2.0."
- SW 2.0 source code = (1) the dataset defining desired behavior + (2) the network architecture as skeleton. Training *compiles* the dataset into a binary (the weights).
- "In most practical applications today...most of the active 'software development' takes the form of curating, growing, massaging and cleaning labeled datasets."
- "it is significantly easier to collect the data (or more generally, identify a desirable behavior) than to explicitly write the program" — this property drives the transition.
- Teams split: *2.0 programmers* (data labelers) edit and grow datasets; *1.0 programmers* maintain training infrastructure.
- SW 2.0 programs have desirable properties: computationally homogeneous, portable, agile (halve channels → halve runtime), modules can be jointly optimized end-to-end.
- The tooling ecosystem for SW 2.0 is missing: "Who is going to develop the first Software 2.0 IDEs, which help with all of the workflows in accumulating, visualizing, cleaning, labeling, and sourcing datasets?"
- "Software (1.0) is eating the world, and now AI (Software 2.0) is eating software."
- "when we develop AGI, it will certainly be written in Software 2.0."

## Relevance

**To Memex directly:**

The SW 2.0 framing positions *the dataset* as the source code. For an AI working on a software project, the project wiki is the equivalent: the structured record of what the codebase does, what decisions were made, what's changed — the "dataset" that trains the AI's project-specific behavior. Memex is building the SW 2.0 IDE for this: tooling to accumulate, organize, keep current, and query the project dataset.

The "accumulate, massage, clean" cycle maps directly to Memex's capture/sync/curate cycle. Karpathy notes the 2.0 IDE should "bubble up" cases where the dataset is likely wrong (mislabeled examples → stale wiki pages). The `synced-at-commit` staleness signal is Memex's answer to this.

The question "Is there space for a Software 2.0 GitHub? In this case repositories are datasets" is directly adjacent to what Memex is building: a per-project, git-anchored knowledge base that travels with the project.

**To Memex's self-improvement loop:**

The self-improvement loop in Memex (lessons captured → reviewed → promoted) is a 2.0-style feedback cycle: the "dataset" of methodology is what gets improved, not explicit rules.

## Open questions

- The SW 2.0 IDE Karpathy describes (bubbling up mislabeled examples, suggesting uncertain cases) assumes the "label" is the atomic unit. For project wikis, what is the atomic unit of quality signal? Staleness (computable from git) is clear; but *accuracy* and *completeness* are harder to detect.
- Karpathy wrote this in 2017 before LLMs were dominant. Software 3.0 (LLMs as universal programs describable in natural language) may be the more relevant paradigm now — see his 2023 X post. Do the SW 2.0 tooling implications still apply in a 3.0 world?

## Excerpts

> "Neural networks are not just another classifier, they represent the beginning of a fundamental shift in how we develop software. They are Software 2.0."

> "most of the active 'software development' takes the form of curating, growing, massaging and cleaning labeled datasets"

> "Who is going to develop the first Software 2.0 IDEs, which help with all of the workflows in accumulating, visualizing, cleaning, labeling, and sourcing datasets?"

> "Is there space for a Software 2.0 Github? In this case repositories are datasets and commits are made up of additions and edits of the labels."

> "Software (1.0) is eating the world, and now AI (Software 2.0) is eating software."
