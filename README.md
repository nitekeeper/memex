# Memex

A project-wiki capability for AI systems — with self-improvement loop and exact staleness semantics tied to git commits.

Built and maintained by [Skill Atelier](../skill-atelier/). Product 1 of the framework.

The name comes from Vannevar Bush's 1945 *As We May Think* — a "memory extender" that follows associative trails through documents.

---

## What it does

Memex gives AI systems the ability to:

- Build and maintain structured knowledge bases (project wikis) inside any repo
- Know precisely which wiki pages are stale — not heuristically, but by comparing `synced-at-commit` to repo HEAD
- Capture lessons from work, stage them, review them, and promote them into methodology
- Curate wiki entries deliberately: proposed by AI, approved by human, deleted by default when no longer useful

---

## How to enter a session

Read in this order:

1. **`CLAUDE.md`** — operating rules for AI sessions inside this product repo
2. **`GOALS.md`** — north-star, current focus, anti-goals
3. **`ROADMAP.md`** — current state; what's next
4. **`DESIGN_NOTES.md`** — decisions made so far

Then choose what you are doing (research, design, build, review, release) and proceed.

---

## Repo layout

```
memex/
├── README.md                  ← you are here
├── CLAUDE.md                  ← AI session entry instructions
├── GOALS.md                   ← north-star, current focus, anti-goals
├── ROADMAP.md                 ← product roadmap
├── CHANGELOG.md               ← release history
├── DESIGN_NOTES.md            ← decisions log
├── docs/                      ← format specs specific to Memex
├── skills/                    ← the skill files that make up the product
├── sources/                   ← research materials (inbox, analyzed)
├── lessons/                   ← lesson capture (inbox, feedback, promoted)
├── db/                        ← SQLite schema extension (project-wiki tables)
├── tests/                     ← validation
├── dist/                      ← released artifacts (cut deliberately, not auto)
└── .ai/                       ← Memex as its own project wiki
```

---

## Status

Research phase. Repo just scaffolded. First source to ingest: Karpathy's writings on self-improvement and LLM-as-OS.

See `ROADMAP.md` for what's next.
