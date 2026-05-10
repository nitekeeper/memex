# Design Notes — Memex

Decisions log. Each entry records what was decided, why, and what alternatives were rejected.

---

## 2026-05-09 — Repo scaffolded; research phase begins

**Decision:** Scaffold the Memex repo at `C:\Users\user\Documents\Skills\memex\` as a sibling to `skill-atelier\`. Begin research phase with Karpathy as first source.

**Context:** Decided in Skill Atelier's first design session (2026-05-09). The repo was deferred from that session to keep focus on framework-level decisions. Now created in the second session.

**Structure adopted:**
- Follows Skill Atelier's Foundation Plan Layer 2 shape: own DESIGN_NOTES, ROADMAP, CHANGELOG, GOALS, .ai/, sources/, lessons/, db/, dist/, skills/, tests/.
- No format or schema locked yet — that waits for synthesis after all three research sources are ingested.

**Source ingestion order (inherited from first design session):**
1. Karpathy's writings on self-improvement and LLM-as-OS
2. User's existing LLM wiki build
3. Superpowers (deliberately last)

**Alternatives rejected:**
- Scaffold the full format spec now — rejected. Locking format before research contradicts the "research before design" principle (CLAUDE.md Working Rule 1).
- Use Skill Atelier's repo as a monorepo — rejected. Foundation Plan principle 2: each product is its own repo with its own lifecycle.
