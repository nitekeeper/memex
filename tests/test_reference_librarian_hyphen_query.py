"""Regression: a hyphenated FTS5 query (e.g. a slug) must not crash MATCH.

Root cause (memex#27, C2): execute_query_plan passes fts_query straight to
`documents_fts MATCH ?`. A bare hyphenated term like a capture slug
(`memex22-superpower-2026-05-10-sync-skill`) is parsed by FTS5 as operator /
column-filter syntax, raising sqlite3.OperationalError ("no such column: …")
before any matching happens. The fix retries once with the query escaped as a
single quoted FTS5 phrase. These tests assert the bare-slug path no longer
raises and still returns the matching document, while valid boolean queries are
untouched.
"""

import pytest

from scripts import brain, install, onboarding
from scripts.db import get_connection, memex_home

SLUG = "memex22-superpower-2026-05-10-sync-skill"


@pytest.fixture
def installed_with_human(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")


def _insert_doc(index_id: str, key: str, searchable: str) -> None:
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            index_id,
            key,
            "memex-process-artifact",
            "article",
            "captures",
            "1",
            searchable,
            "librarian-1",
        ),
    )
    conn.commit()
    conn.close()


def test_hyphenated_slug_query_does_not_raise_and_returns_doc(installed_with_human):
    # searchable leads with the slug verbatim + a hyphens-as-spaces form, the
    # same shape capture_artifact.py writes (FIX-A). The query is the BARE slug.
    searchable = f"{SLUG} {SLUG.replace('-', ' ')} sync skill design"
    _insert_doc("idx-slug", SLUG, searchable)

    prep = brain.ask_prepare(f"ask {SLUG}")
    plan = {"fts_query": SLUG, "vector_query": None, "filters": {}, "limit": 10}

    # (a) must NOT raise sqlite3.OperationalError (the C2 crash).
    results = brain.ask_execute(prep, plan, with_embedding=False)

    # (b) the matching document is returned.
    keys = [r["key"] for r in results]
    assert SLUG in keys, f"expected {SLUG!r} in results, got {keys!r}"


def test_valid_boolean_query_unaffected_by_retry_path(installed_with_human):
    # A legitimate multi-term boolean query parses on the first try and must
    # return its match — the retry path must not change behavior for it.
    _insert_doc("idx-bool", "bool-key", "alpha beta gamma")

    prep = brain.ask_prepare("alpha or delta")
    plan = {"fts_query": "alpha OR delta", "vector_query": None, "filters": {}, "limit": 10}
    results = brain.ask_execute(prep, plan, with_embedding=False)
    assert "idx-bool" in [r["index_id"] for r in results]
