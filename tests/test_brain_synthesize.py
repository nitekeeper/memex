"""brain.synthesize tests — DEFERRED to Phase 3 of the Option-B refactor.

Synthesize involves two subagent dispatches (Synthesizer → produces text,
then Librarian → classifies it). The prepare/post-synthesis/complete
three-step API hasn't landed yet; Phase 1 only covers ingest + capture.

When Phase 3 lands, the marker below should be removed and tests rewritten
to feed synthetic Synthesizer + Librarian outputs through the new helpers.
"""
import pytest


pytestmark = pytest.mark.skip(
    reason="Synthesize Phase 3 refactor pending (Option-B Task-tool dispatch)."
)


def test_synthesize_writes_to_syntheses_table():
    """Placeholder — re-enable when synthesize_prepare/post/complete land."""
    pass
