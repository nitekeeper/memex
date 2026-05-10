---
id: source:superpowers-skill-system
slug: superpowers-skill-system
title: Superpowers — Official Claude Code Skill Plugin (v5.0.7)
type: repo
authors: [Anthropic / claude-plugins-official]
url: "C:\\Users\\user\\.claude\\plugins\\cache\\claude-plugins-official\\superpowers\\5.0.7"
captured: 2026-05-09
status: analyzed
relevance-to: [memex]
tags: [skill-system, workflow-governance, context-injection, llm-discipline, checklists, git-worktrees, subagents, anti-rationalization, skill-authoring, tdd-for-documentation, cso]
informs-decisions: []
---

# Superpowers — Official Claude Code Skill Plugin (v5.0.7)

## Summary

Superpowers is Anthropic's official Claude Code plugin implementing a skill-based workflow governance system. Skills are markdown files that inject methodology instructions into the LLM's context on demand; they are not code. The system's central mechanism is a mandatory invocation rule ("even 1% chance → invoke") enforced through explicit anti-rationalization tables, hard-gate blocks, and checklists converted to TodoWrite tasks. Version 5.0.7 contains 14 skills spanning the full development lifecycle: brainstorming → writing-plans → executing-plans → finishing-a-development-branch, with cross-cutting skills for testing discipline, code review, parallel dispatch, and verification. The system treats workflow discipline as an LLM governance problem, not a technical enforcement problem.

## Key claims

- **Context-injection is the primitive.** Skills are markdown files loaded on demand via the `Skill` tool. No code, no plugins in the traditional sense — pure instruction injection into the LLM's active context window.
- **The 1% rule enforces mandatory invocation.** The root skill (`using-superpowers`) declares: "If you think there is even a 1% chance a skill might apply, you ABSOLUTELY MUST invoke the skill." This is the load-bearing governance mechanism; every other discipline depends on skills being loaded consistently.
- **Anti-rationalization tables are first-class design elements.** Each skill contains explicit tables of excuses and their refutations ("I remember this skill" → "Skills evolve. Read current version."). The system treats LLM rationalization as a known failure mode, not an edge case.
- **Skills chain explicitly.** Each skill names its successor: brainstorming ends by invoking `writing-plans`; writing-plans offers `subagent-driven-development` or `executing-plans`; executing-plans ends with `finishing-a-development-branch`. The pipeline is a declared dependency graph, not emergent behavior.
- **Hard gates prevent step-skipping.** Brainstorming contains a `<HARD-GATE>` block: "Do NOT invoke any implementation skill, write any code, scaffold any project, or take any implementation action until you have presented a design and the user has approved it." The instruction names the exact prohibited actions.
- **Verification-before-completion is an iron law.** The skill names a precise gate function: identify the proof command → run it fresh → read full output → check exit code → only then make the claim. It includes a failure-mode table mapping each claim type to the exact evidence required.
- **TodoWrite converts checklists to tracked tasks.** The root skill instructs: if an invoked skill has a checklist, create one TodoWrite item per checklist item. This externalizes working memory to the tool layer.
- **Git worktrees enforce isolation.** `using-git-worktrees` is declared a required integration for `executing-plans` — each feature gets an isolated workspace. The worktree is the unit of in-flight work.
- **Subagent dispatch is an explicit skill.** `dispatching-parallel-agents` and `subagent-driven-development` codify the pattern of dispatching one fresh subagent per task with review between tasks, rather than executing inline.
- **Skill type distinguishes rigidity.** Skills are either rigid ("TDD, debugging: follow exactly. Don't adapt away discipline.") or flexible ("patterns: adapt principles to context"). The skill itself declares which.
- **User instructions always beat skills.** The priority stack is explicit: user CLAUDE.md / direct request > Superpowers skills > default system prompt. Skills override defaults but cannot override users.
- **Version management exists at 5.0.7.** The versioned path (`superpowers/5.0.7/`) implies 50+ minor releases, suggesting the skill content evolves actively. The anti-rationalization note "Skills evolve. Read current version." is load-bearing, not boilerplate.
- **Skill creation is TDD for documentation.** `writing-skills` maps the full RED-GREEN-REFACTOR cycle onto skill authoring: run a pressure scenario without the skill (baseline), document exact rationalizations the agent uses, write the skill to address those specific failures, re-test. New rationalizations → refactor → re-test until bulletproof.
- **The CSO description trap is a known failure mode.** If a skill description summarizes its workflow, the LLM follows the description instead of reading the full skill. Tested empirically: description "dispatches subagent per task with code review between tasks" caused one review; description "Use when executing implementation plans" caused two (per the flowchart). The rule: descriptions describe WHEN to use, never WHAT the skill does.
- **Skill frontmatter is minimal by design.** Only `name` and `description` are required (max 1024 chars total). The formal spec lives at `agentskills.io/specification`. Heavy frontmatter is an anti-pattern — every token loaded into every conversation is a cost.
- **Token efficiency is a first-class constraint.** Getting-started workflows target <150 words; frequently-loaded skills <200 words. Techniques: defer to `--help` flags, cross-reference other skills rather than repeat, use minimal examples (20 words over 42 words).

## Relevance

**To Memex core design questions:**

- **Project-wiki format:** Superpowers uses markdown with structured body sections (Summary, Key claims, Relevance, etc.) — consistent with Karpathy's and second-brain-blueprint's finding that prose markdown is the right persistent layer. No counter-evidence here.
- **SQLite/persistence layer:** Superpowers has no persistence layer at all. Skills are stateless context injections. This is a deliberate design choice for a *workflow governance* system, not a knowledge system — the two problems are different. Memex needs persistence; Superpowers confirms that skill mechanics alone do not provide it.
- **Session discipline (meta:run-session):** The Superpowers pipeline (brainstorm → plan → execute → finish) is a concrete exemplar of what session discipline looks like in a mature system. The chaining pattern (each skill names its successor) is directly applicable to the framework's `meta:run-session` substantiation.
- **Skill format (docs/SKILL_FORMAT.md):** Superpowers `writing-skills` specifies the canonical structure: YAML frontmatter (name + description only, max 1024 chars), Overview, When to Use, Core Pattern, Quick Reference, Implementation, Common Mistakes. The framework's current SKILL_FORMAT.md uses heavier frontmatter (id, slug, type, status, version, owner, tags, created, updated, sources) — a deliberate divergence that warrants a reasoned decision.
- **Anti-rationalization as design element:** The framework's meta-skills do not yet include explicit anti-rationalization content. Superpowers treats this as essential and derives the tables empirically from baseline testing. Worth evaluating whether meta-skills should adopt this pattern.
- **Mandatory invocation enforcement:** The 1% rule is the system's single most important design element. Memex skills (once written) will face the same LLM rationalization problem. The rule and its anti-rationalization tables are the solution the framework should study before writing any Memex skills.
- **CSO directly constrains Memex skill description writing.** The description trap (summarizing workflow causes the LLM to skip the skill body) is directly applicable to any skill the framework writes. Memex skill descriptions must describe triggering conditions only.

**What Superpowers does NOT inform:**

- Project-wiki page schema (Memex's primary design problem).
- SQLite FTS shape, staleness detection, or `synced-at-commit` mechanics.
- Ingestion pipeline (inbox → raw → wiki).
- Cross-file linking or disambiguation.
- Session snapshot format.

## Open questions

- **Should Memex skills adopt the DOT graph process flow format?** Superpowers uses DOT diagrams for non-obvious decision flows. `writing-skills` says: "Use flowcharts ONLY for non-obvious decision points, process loops where you might stop too early, or when-to-use-A-vs-B decisions." The framework's SKILL_FORMAT.md does not mention this. Decision: adopt the conditional rule (flowchart only for non-obvious decisions), not blanket inclusion.
- **Should the framework adopt a mandatory-invocation root skill?** Superpowers has `using-superpowers` as a session-start anchor. The framework's `meta:run-session` could serve an analogous function — but the framework is an AI-operated repo, not a user-facing product. The invocation model may differ.
- **How does skill versioning interact with `synced-at-commit`?** Superpowers versions skills by directory path. If Memex skills evolve, what is the staleness signal? This maps directly onto the framework's `synced-at-commit` + `describes-files` pattern.
- **Should the framework's SKILL_FORMAT.md adopt minimal frontmatter?** Superpowers uses only `name` + `description` (max 1024 chars). The framework uses 10+ fields. The extra fields (id, type, status, version, sources) serve the framework's own tracking needs — but they inflate every skill that gets loaded. The question is whether the framework's tracking fields belong in the skill file or in a separate registry/index.
- **Should meta-skills be tested with the TDD-for-documentation approach?** `writing-skills` prescribes running baseline scenarios (agent without the skill) to document natural failure modes, then writing the skill to address those specific rationalizations. The framework's meta-skills were written without this. Worth doing for `meta:run-session` before shipping it.

## Excerpts

> "If you think there is even a 1% chance a skill might apply, you ABSOLUTELY MUST invoke the skill. IF A SKILL APPLIES TO YOUR TASK, YOU DO NOT HAVE A CHOICE. YOU MUST USE IT. This is not negotiable. This is not optional. You cannot rationalize your way out of this."

— `using-superpowers`, skill invocation rule

> "Claiming work is complete without verification is dishonesty, not efficiency. Core principle: Evidence before claims, always."

— `verification-before-completion`, core principle

> "Do NOT invoke any implementation skill, write any code, scaffold any project, or take any implementation action until you have presented a design and the user has approved it. This applies to EVERY project regardless of perceived simplicity."

— `brainstorming`, HARD-GATE block

> "Each step is one action (2–5 minutes): 'Write the failing test' — step. 'Run it to make sure it fails' — step. 'Implement the minimal code to make the test pass' — step."

— `writing-plans`, bite-sized task granularity

> "Writing skills IS Test-Driven Development applied to process documentation. You write test cases (pressure scenarios with subagents), watch them fail (baseline behavior), write the skill (documentation), watch tests pass (agents comply), and refactor (close loopholes)."

— `writing-skills`, core principle

> "CRITICAL: Description = When to Use, NOT What the Skill Does. Testing revealed that when a description summarizes the skill's workflow, Claude may follow the description instead of reading the full skill content."

— `writing-skills`, Claude Search Optimization section
