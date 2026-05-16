"""Embeddings tests — pack/cosine round-trip + provider dispatch.

All three providers (openai, voyage, local) are now wired. SDK imports
happen lazily; tests mock the SDKs so they pass without any of them
installed and without any API keys configured.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from scripts import embeddings

# ── pack / unpack / cosine ─────────────────────────────────────────────────


def test_encode_returns_blob():
    with patch("scripts.embeddings._call_provider", return_value=[0.1, 0.2, 0.3]):
        result = embeddings.encode("hello")
    assert isinstance(result, bytes)
    assert len(result) == 12  # 3 floats * 4 bytes


def test_decode_round_trips():
    vec_in = [0.5, -0.5, 1.0, 0.0]
    blob = embeddings._pack(vec_in)
    vec_out = embeddings._unpack(blob)
    assert vec_out == pytest.approx(vec_in, rel=1e-6)


def test_cosine_identical_vectors_is_one():
    a = [1.0, 0.0, 0.0]
    assert embeddings.cosine(embeddings._pack(a), embeddings._pack(a)) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors_is_zero():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert embeddings.cosine(embeddings._pack(a), embeddings._pack(b)) == pytest.approx(0.0)


def test_cosine_opposite_vectors_is_negative_one():
    a = [1.0, 0.0, 0.0]
    b = [-1.0, 0.0, 0.0]
    assert embeddings.cosine(embeddings._pack(a), embeddings._pack(b)) == pytest.approx(-1.0)


# ── Model-info recording ───────────────────────────────────────────────────


def test_encode_records_model_info(tmp_memex_home):
    """encode() records the active provider/model/dim in registry.json."""
    with patch("scripts.embeddings._call_provider", return_value=[0.0] * 1536):
        embeddings.encode("hello")
    from scripts import registry

    info = registry._load().get("__embedding_model__")
    assert info is not None
    assert info["dim"] == 1536
    assert info["provider"] == "openai"  # default
    assert info["model"] == "text-embedding-3-small"


def test_active_model_info_for_openai(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")
    info = embeddings.active_model_info()
    assert info["provider"] == "openai"
    assert info["model"] == "text-embedding-3-small"
    assert info["dim"] == 1536


def test_active_model_info_respects_model_override(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("MEMEX_OPENAI_MODEL", "text-embedding-3-large")
    info = embeddings.active_model_info()
    assert info["model"] == "text-embedding-3-large"
    assert info["dim"] == 3072


def test_active_model_info_for_voyage(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "voyage")
    info = embeddings.active_model_info()
    assert info["provider"] == "voyage"
    assert info["model"] == "voyage-3"
    assert info["dim"] == 1024


def test_active_model_info_for_local(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "local")
    info = embeddings.active_model_info()
    assert info["provider"] == "local"
    assert info["model"] == "all-MiniLM-L6-v2"
    assert info["dim"] == 384


def test_recorded_model_info_returns_none_before_any_encode(tmp_memex_home):
    assert embeddings.recorded_model_info() is None


def test_recorded_model_info_returns_dict_after_encode(tmp_memex_home):
    with patch("scripts.embeddings._call_provider", return_value=[0.0] * 1024):
        embeddings.encode("hello")
    info = embeddings.recorded_model_info()
    assert info is not None
    assert info["dim"] == 1024


# ── Provider dispatch ──────────────────────────────────────────────────────


def test_dispatch_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "nonsense")
    with pytest.raises(ValueError, match="Unknown embedding provider"):
        embeddings._call_provider("hello")


def test_openai_provider_calls_sdk(monkeypatch):
    """The openai provider lazy-imports `openai` and calls embeddings.create."""
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")

    fake_module = types.ModuleType("openai")
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = MagicMock(data=[MagicMock(embedding=[0.1] * 1536)])
    fake_module.OpenAI = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    vec = embeddings._call_provider("test text")
    assert len(vec) == 1536
    fake_client.embeddings.create.assert_called_once()
    call_kwargs = fake_client.embeddings.create.call_args.kwargs
    assert call_kwargs["model"] == "text-embedding-3-small"
    assert call_kwargs["input"] == "test text"


def test_openai_provider_raises_runtime_error_if_sdk_missing(monkeypatch):
    """When openai SDK is not installed, the error message points at the
    user-facing fix (install or switch provider) rather than a bare ImportError."""
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")
    # Make `from openai import OpenAI` fail at import time
    monkeypatch.setitem(sys.modules, "openai", None)  # raises ModuleNotFoundError
    with pytest.raises(RuntimeError, match="openai SDK is not installed"):
        embeddings._call_provider("x")


def test_voyage_provider_calls_sdk(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    fake_module = types.ModuleType("voyageai")
    fake_client = MagicMock()
    fake_result = MagicMock()
    fake_result.embeddings = [[0.2] * 1024]
    fake_client.embed.return_value = fake_result
    fake_module.Client = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "voyageai", fake_module)

    vec = embeddings._call_provider("test text")
    assert len(vec) == 1024
    fake_client.embed.assert_called_once()
    call_kwargs = fake_client.embed.call_args.kwargs
    assert call_kwargs["model"] == "voyage-3"
    assert call_kwargs["input_type"] == "document"


def test_voyage_provider_raises_runtime_error_if_sdk_missing(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setitem(sys.modules, "voyageai", None)
    with pytest.raises(RuntimeError, match="voyageai SDK is not installed"):
        embeddings._call_provider("x")


def test_voyage_provider_raises_if_no_api_key(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    # Stub the SDK so we don't fail on missing dep
    fake_module = types.ModuleType("voyageai")
    fake_module.Client = MagicMock()
    monkeypatch.setitem(sys.modules, "voyageai", fake_module)
    with pytest.raises(RuntimeError, match="VOYAGE_API_KEY"):
        embeddings._call_provider("x")


def test_local_provider_calls_sentence_transformers(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "local")
    # Reset cache so the test sets up fresh
    embeddings._LOCAL_MODEL_CACHE.clear()

    fake_module = types.ModuleType("sentence_transformers")
    fake_model = MagicMock()
    fake_model.encode.return_value = [0.3] * 384
    fake_module.SentenceTransformer = MagicMock(return_value=fake_model)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    vec = embeddings._call_provider("test text")
    assert len(vec) == 384
    fake_module.SentenceTransformer.assert_called_once_with("all-MiniLM-L6-v2")
    fake_model.encode.assert_called_once()


def test_local_provider_caches_model_instance(monkeypatch):
    """Second call should reuse the cached SentenceTransformer instance."""
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "local")
    embeddings._LOCAL_MODEL_CACHE.clear()

    fake_module = types.ModuleType("sentence_transformers")
    fake_model = MagicMock()
    fake_model.encode.return_value = [0.4] * 384
    fake_module.SentenceTransformer = MagicMock(return_value=fake_model)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    embeddings._call_provider("one")
    embeddings._call_provider("two")
    # Constructor called once; encode called twice
    assert fake_module.SentenceTransformer.call_count == 1
    assert fake_model.encode.call_count == 2


def test_local_provider_raises_runtime_error_if_sdk_missing(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "local")
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(RuntimeError, match="sentence-transformers is not installed"):
        embeddings._call_provider("x")


# ── Backfill / reembed / model-change detection ───────────────────────────


def _seed_documents(rows: list[dict]):
    """Helper: insert documents rows directly into ~/.memex/index.db."""
    from scripts.db import get_connection, memex_home

    conn = get_connection(str(memex_home() / "index.db"))
    for r in rows:
        conn.execute(
            "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
            "searchable, embedding, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                r["index_id"],
                r.get("key", r["index_id"]),
                r.get("domain", "article"),
                r.get("store", "no-store"),
                r.get("table_name", "t"),
                r.get("row_id", "1"),
                r["searchable"],
                r.get("embedding"),
                r.get("created_by", "librarian-1"),
            ),
        )
    conn.commit()
    conn.close()


def test_backfill_null_counts_correctly_dry_run(tmp_memex_home):
    from scripts import install

    install.run()
    _seed_documents(
        [
            {"index_id": "a", "searchable": "alpha"},
            {"index_id": "b", "searchable": "beta", "embedding": b"\x00\x00\x00\x00"},
            {"index_id": "c", "searchable": "gamma"},
        ]
    )
    result = embeddings.backfill_null(dry_run=True)
    assert result["considered"] == 2  # a, c — b already has embedding
    assert result["encoded"] == 0
    assert result["errors"] == 0
    assert result["dry_run"] is True


def test_backfill_null_encodes_only_null_rows(tmp_memex_home):
    from scripts import install

    install.run()
    _seed_documents(
        [
            {"index_id": "a", "searchable": "alpha"},
            {"index_id": "b", "searchable": "beta", "embedding": b"\xff" * 8},
            {"index_id": "c", "searchable": "gamma"},
        ]
    )
    with patch("scripts.embeddings._call_provider", return_value=[0.1] * 4):
        result = embeddings.backfill_null()
    assert result["considered"] == 2
    assert result["encoded"] == 2
    assert result["errors"] == 0
    # b's existing embedding untouched
    from scripts.db import get_connection, memex_home

    conn = get_connection(str(memex_home() / "index.db"))
    rows = {
        r["index_id"]: r["embedding"]
        for r in conn.execute("SELECT index_id, embedding FROM documents")
    }
    conn.close()
    assert rows["b"] == b"\xff" * 8
    assert rows["a"] is not None
    assert rows["c"] is not None


def test_backfill_null_tolerates_per_row_errors(tmp_memex_home):
    from scripts import install

    install.run()
    _seed_documents(
        [
            {"index_id": "good", "searchable": "ok"},
            {"index_id": "bad", "searchable": "fail"},
        ]
    )
    call_count = {"n": 0}

    def flaky_provider(text):
        call_count["n"] += 1
        if "fail" in text:
            raise RuntimeError("provider hiccup")
        return [0.0] * 4

    with patch("scripts.embeddings._call_provider", side_effect=flaky_provider):
        result = embeddings.backfill_null()
    assert result["considered"] == 2
    assert result["encoded"] == 1
    assert result["errors"] == 1


def test_reembed_all_overwrites_existing(tmp_memex_home):
    from scripts import install

    install.run()
    _seed_documents(
        [
            {"index_id": "a", "searchable": "alpha", "embedding": b"\x01" * 8},
            {"index_id": "b", "searchable": "beta", "embedding": b"\x02" * 8},
        ]
    )
    with patch("scripts.embeddings._call_provider", return_value=[0.5] * 4):
        result = embeddings.reembed_all()
    assert result["considered"] == 2
    assert result["encoded"] == 2

    from scripts.db import get_connection, memex_home

    conn = get_connection(str(memex_home() / "index.db"))
    rows = list(conn.execute("SELECT embedding FROM documents"))
    conn.close()
    # All rows now have the new 16-byte float32 BLOB (4 floats * 4 bytes), not
    # the 8-byte placeholders we seeded.
    for r in rows:
        assert len(r["embedding"]) == 16


def test_reembed_all_dry_run_changes_nothing(tmp_memex_home):
    from scripts import install

    install.run()
    _seed_documents(
        [
            {"index_id": "a", "searchable": "alpha", "embedding": b"\x01" * 8},
        ]
    )
    result = embeddings.reembed_all(dry_run=True)
    assert result["considered"] == 1
    assert result["encoded"] == 0

    from scripts.db import get_connection, memex_home

    conn = get_connection(str(memex_home() / "index.db"))
    embedding = conn.execute("SELECT embedding FROM documents WHERE index_id = 'a'").fetchone()[
        "embedding"
    ]
    conn.close()
    assert embedding == b"\x01" * 8  # unchanged


def test_detect_model_change_returns_none_when_unrecorded(tmp_memex_home):
    """No __embedding_model__ in registry yet → no drift to report."""
    from scripts import install

    install.run()
    assert embeddings.detect_model_change() is None


def test_detect_model_change_returns_none_when_aligned(tmp_memex_home, monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")
    with patch("scripts.embeddings._call_provider", return_value=[0.0] * 1536):
        embeddings.encode("hello")  # records {provider:openai, model:..., dim:1536}
    # No provider change yet
    assert embeddings.detect_model_change() is None


def test_detect_model_change_flags_provider_switch(tmp_memex_home, monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")
    with patch("scripts.embeddings._call_provider", return_value=[0.0] * 1536):
        embeddings.encode("hello")
    # Now switch to voyage
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "voyage")
    drift = embeddings.detect_model_change()
    assert drift is not None
    assert "provider" in drift["changed"]
    assert drift["active"]["provider"] == "voyage"
    assert drift["recorded"]["provider"] == "openai"


def test_reembed_all_records_previous_in_result(tmp_memex_home, monkeypatch):
    from scripts import install

    install.run()  # need index.db for _seed_documents
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")
    with patch("scripts.embeddings._call_provider", return_value=[0.0] * 1536):
        embeddings.encode("seed")  # records previous

    # Switch + reembed
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    _seed_documents([{"index_id": "x", "searchable": "x"}])
    with patch("scripts.embeddings._call_provider", return_value=[0.1] * 1024):
        result = embeddings.reembed_all()
    assert result["previous_recorded"]["provider"] == "openai"
    assert result["provider"] == "voyage"
