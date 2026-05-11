# Memex — dist/

Released artifacts for **v0.1.0** (2026-05-10).

---

## Contents

| File / Directory | Purpose |
|---|---|
| `USER_GUIDE.md` | Full setup and workflow instructions — start here |
| `MANIFEST.md` | What's in this release (skills, scripts, format specs) |
| `skills/` | The 7 Memex skills (each with SKILL.md + REFERENCE.md) |
| `scripts/` | rebuild.py, sync.py, search.py |
| `scripts/requirements.txt` | Runtime dependency: `python-frontmatter` |
| `db/schema.sql` | SQLite schema for memex.db |
| `docs/` | Format specs: WIKI_PAGE_FORMAT.md, LESSON_FORMAT.md, MEMEX_SPEC.md |

---

## Quick install

```bash
pip install python-frontmatter
mkdir -p .ai/wiki lessons/inbox lessons/feedback lessons/promoted
echo ".ai/memex.db" >> .gitignore
python scripts/rebuild.py .ai/
```

See `USER_GUIDE.md` for the full walkthrough.
