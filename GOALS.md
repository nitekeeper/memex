# Goals — Memex

The AI consults this file when planning, deciding, or capturing lessons. Update during sessions with reasoning logged in `DESIGN_NOTES.md`.

---

## North star

**Give AI systems exact, persistent knowledge of any project they work in** — what the code does, what decisions were made, what's stale, what's reliable. No guessing. No re-discovering structure every session.

The first user is Skill Atelier itself (dogfooding). The second user is any AI + human pair working on a real codebase.

---

## Current focus

- ✅ Research, design, build, dogfood, and v0.1.0 release — complete (2026-05-10).
- ⏭️ **Next:** v0.2 planning — embedding-based search, cross-project federation, or release tooling skill. Decision deferred to next session.

---

## Anti-goals

- **Not a generic note-taker or second-brain.** Memex is for AI systems working on real repos with strict project-bound staleness semantics. Personal wikis and generic knowledge bases are out of scope.
- **Not a document store.** Memex manages structured wiki pages with git-anchored staleness, not arbitrary documents.
- **Not premature abstraction.** Features are driven by real workflows (Skill Atelier's own needs first), not speculative adopters.
- **Not cargo-culted from Superpowers.** Superpowers is one research source, ingested deliberately last. Memex's design must emerge from the full research synthesis.
- **Not a mega-product.** Memex provides project-wiki + self-improvement loop. The Development Skill (Product 2) builds on top of it — they are not merged.

---

## How to use this file

- Read at session start.
- Surface conflicts: if a request conflicts with anything here, flag before acting.
- Update during sessions; log reasoning in `DESIGN_NOTES.md`.
- Goals decay. Stale goals are revised or removed.
