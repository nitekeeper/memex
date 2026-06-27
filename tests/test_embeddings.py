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


def test_encode_returns_blob(bootstrapped_marker):
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


def test_encode_records_model_info(bootstrapped_marker):
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


def test_recorded_model_info_returns_none_before_any_encode(bootstrapped_marker):
    assert embeddings.recorded_model_info() is None


def test_recorded_model_info_returns_dict_after_encode(bootstrapped_marker):
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
    fake_module.BadRequestError = Exception  # required by hoisted import
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    vec = embeddings._call_provider("test text")
    assert len(vec) == 1536
    fake_client.embeddings.create.assert_called_once()
    call_kwargs = fake_client.embeddings.create.call_args.kwargs
    assert call_kwargs["model"] == "text-embedding-3-small"
    assert call_kwargs["input"] == "test text"


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
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._call_provider("x")
    assert exc_info.value.reason == "not_configured"
    assert exc_info.value.provider == "voyage"


def test_voyage_provider_raises_if_no_api_key(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    # Stub the SDK so we don't fail on missing dep
    fake_module = types.ModuleType("voyageai")
    fake_module.Client = MagicMock()
    monkeypatch.setitem(sys.modules, "voyageai", fake_module)
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._call_provider("x")
    assert exc_info.value.reason == "not_configured"
    assert "VOYAGE_API_KEY" in exc_info.value.detail


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


def test_local_provider_raises_embedding_unavailable_if_sdk_missing(monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "local")
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    embeddings._LOCAL_MODEL_CACHE.clear()
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._call_provider("x")
    assert exc_info.value.reason == "not_configured"
    assert exc_info.value.provider == "local"


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


def test_backfill_null_counts_correctly_dry_run(bootstrapped_marker):
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


def test_backfill_null_encodes_only_null_rows(bootstrapped_marker):
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


def test_backfill_null_tolerates_per_row_errors(bootstrapped_marker):
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


def test_reembed_all_overwrites_existing(bootstrapped_marker):
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


def test_reembed_all_dry_run_changes_nothing(bootstrapped_marker):
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


def test_detect_model_change_returns_none_when_unrecorded(bootstrapped_marker):
    """No __embedding_model__ in registry yet → no drift to report."""
    from scripts import install

    install.run()
    assert embeddings.detect_model_change() is None


def test_detect_model_change_returns_none_when_aligned(bootstrapped_marker, monkeypatch):
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")
    with patch("scripts.embeddings._call_provider", return_value=[0.0] * 1536):
        embeddings.encode("hello")  # records {provider:openai, model:..., dim:1536}
    # No provider change yet
    assert embeddings.detect_model_change() is None


def test_detect_model_change_flags_provider_switch(bootstrapped_marker, monkeypatch):
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


def test_reembed_all_records_previous_in_result(bootstrapped_marker, monkeypatch):
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


# ── EmbeddingUnavailable class ────────────────────────────────────────────


def test_embedding_unavailable_stores_reason():
    exc = embeddings.EmbeddingUnavailable(
        reason="not_configured", provider="openai", detail="no api key"
    )
    assert exc.reason == "not_configured"


def test_embedding_unavailable_stores_provider():
    exc = embeddings.EmbeddingUnavailable(
        reason="not_configured", provider="openai", detail="no api key"
    )
    assert exc.provider == "openai"


def test_embedding_unavailable_stores_detail():
    exc = embeddings.EmbeddingUnavailable(
        reason="not_configured", provider="openai", detail="no api key"
    )
    assert exc.detail == "no api key"


def test_embedding_unavailable_message_with_detail():
    exc = embeddings.EmbeddingUnavailable(
        reason="oversize_input", provider="openai", detail="max 8192, got 12041"
    )
    msg = str(exc)
    assert "provider='openai'" in msg
    assert "reason='oversize_input'" in msg
    assert "max 8192, got 12041" in msg


def test_embedding_unavailable_message_without_detail():
    exc = embeddings.EmbeddingUnavailable(reason="unknown", provider="local")
    msg = str(exc)
    assert "provider='local'" in msg
    assert "reason='unknown'" in msg
    # No trailing colon when detail is empty
    assert not msg.rstrip().endswith(":")


def test_embedding_unavailable_chains_cause():
    original = RuntimeError("network down")
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        try:
            raise original
        except RuntimeError as e:
            raise embeddings.EmbeddingUnavailable(
                reason="provider_error", provider="openai", detail=str(e)
            ) from e
    assert exc_info.value.__cause__ is original


# ── Per-provider classification — OpenAI ──────────────────────────────────


def test_openai_not_configured_on_import_error(monkeypatch):
    """ImportError on `from openai import OpenAI` → reason='not_configured'."""
    monkeypatch.setitem(sys.modules, "openai", None)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._openai_encode("hello")
    assert exc_info.value.reason == "not_configured"
    assert exc_info.value.provider == "openai"
    assert "openai" in exc_info.value.detail.lower()


def test_openai_oversize_input_on_context_length(monkeypatch):
    """openai.BadRequestError with 'context_length_exceeded' → 'oversize_input'."""
    fake_openai = types.ModuleType("openai")

    class FakeBadRequestError(Exception):
        pass

    fake_openai.BadRequestError = FakeBadRequestError

    def fake_client_factory(*a, **kw):
        client = MagicMock()
        client.embeddings.create.side_effect = FakeBadRequestError(
            "context_length_exceeded: max 8192, got 12041"
        )
        return client

    fake_openai.OpenAI = fake_client_factory
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")

    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._openai_encode("a" * 50000)
    assert exc_info.value.reason == "oversize_input"
    assert exc_info.value.provider == "openai"
    assert "context_length_exceeded" in exc_info.value.detail


def test_openai_provider_error_fallback(monkeypatch):
    """Generic exception from provider call → reason='provider_error'."""
    fake_openai = types.ModuleType("openai")

    class FakeBadRequestError(Exception):
        pass

    fake_openai.BadRequestError = FakeBadRequestError

    def fake_client_factory(*a, **kw):
        client = MagicMock()
        client.embeddings.create.side_effect = RuntimeError("connection reset")
        return client

    fake_openai.OpenAI = fake_client_factory
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")

    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._openai_encode("hello")
    assert exc_info.value.reason == "provider_error"


# ── Per-provider classification — Voyage ──────────────────────────────────


def test_voyage_not_configured_on_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "voyageai", None)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "fake")
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._voyage_encode("hello")
    assert exc_info.value.reason == "not_configured"
    assert exc_info.value.provider == "voyage"


def test_voyage_not_configured_when_api_key_missing(monkeypatch):
    fake_voyageai = types.ModuleType("voyageai")
    fake_voyageai.Client = MagicMock()
    monkeypatch.setitem(sys.modules, "voyageai", fake_voyageai)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._voyage_encode("hello")
    assert exc_info.value.reason == "not_configured"
    assert "VOYAGE_API_KEY" in exc_info.value.detail


def test_voyage_oversize_input_on_token_limit(monkeypatch):
    fake_voyageai = types.ModuleType("voyageai")
    fake_client = MagicMock()
    fake_client.embed.side_effect = RuntimeError("token count 50000 exceeds limit 32000")
    fake_voyageai.Client = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "voyageai", fake_voyageai)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "fake")
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._voyage_encode("a" * 100000)
    assert exc_info.value.reason == "oversize_input"
    assert "token count 50000 exceeds limit" in exc_info.value.detail


def test_voyage_provider_error_fallback(monkeypatch):
    fake_voyageai = types.ModuleType("voyageai")
    fake_client = MagicMock()
    fake_client.embed.side_effect = RuntimeError("connection refused")
    fake_voyageai.Client = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "voyageai", fake_voyageai)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "fake")
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._voyage_encode("hello")
    assert exc_info.value.reason == "provider_error"


# ── Per-provider classification — Local ───────────────────────────────────


def test_local_not_configured_on_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "local")
    embeddings._LOCAL_MODEL_CACHE.clear()
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._local_encode("hello")
    assert exc_info.value.reason == "not_configured"
    assert exc_info.value.provider == "local"


def test_local_oversize_input_on_max_seq_length(monkeypatch):
    fake_st = types.ModuleType("sentence_transformers")
    fake_model = MagicMock()
    fake_model.encode.side_effect = RuntimeError("Input length 800 exceeds max_seq_length 512")
    fake_st.SentenceTransformer = MagicMock(return_value=fake_model)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "local")
    embeddings._LOCAL_MODEL_CACHE.clear()
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._local_encode("a" * 5000)
    assert exc_info.value.reason == "oversize_input"
    assert "max_seq_length" in exc_info.value.detail


def test_local_provider_error_fallback(monkeypatch):
    fake_st = types.ModuleType("sentence_transformers")
    fake_model = MagicMock()
    fake_model.encode.side_effect = RuntimeError("model file corrupt")
    fake_st.SentenceTransformer = MagicMock(return_value=fake_model)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "local")
    embeddings._LOCAL_MODEL_CACHE.clear()
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._local_encode("hello")
    assert exc_info.value.reason == "provider_error"


# ── Central encode() defensive wrap ────────────────────────────────────────


def test_encode_wraps_unknown_leak(bootstrapped_marker, monkeypatch):
    """If _call_provider somehow leaks a non-EmbeddingUnavailable exception,
    encode() must re-raise as EmbeddingUnavailable(reason='unknown').
    """
    monkeypatch.setattr(
        "scripts.embeddings._call_provider",
        MagicMock(side_effect=RuntimeError("totally unexpected")),
    )
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "openai")
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings.encode("hello")
    assert exc_info.value.reason == "unknown"
    assert exc_info.value.provider == "openai"
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_encode_passes_through_embedding_unavailable(bootstrapped_marker, monkeypatch):
    """If _call_provider raises EmbeddingUnavailable, encode() must re-raise
    it as-is — NOT re-wrap it as reason='unknown'.
    """
    original = embeddings.EmbeddingUnavailable(
        reason="not_configured", provider="openai", detail="no key"
    )
    monkeypatch.setattr(
        "scripts.embeddings._call_provider",
        MagicMock(side_effect=original),
    )
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings.encode("hello")
    assert exc_info.value is original
    assert exc_info.value.reason == "not_configured"


# ── Skip log helper ───────────────────────────────────────────────────────


def test_append_skip_log_creates_audits_dir(bootstrapped_marker):
    """_append_skip_log() creates the audits/ directory if it doesn't exist
    and appends the entry to embedding-skip-log.md.
    """
    from scripts.db import memex_home

    audits_dir = memex_home() / "audits"
    log_path = audits_dir / "embedding-skip-log.md"
    assert not audits_dir.exists()

    embeddings._append_skip_log("\n- test entry\n")

    assert audits_dir.is_dir()
    assert log_path.is_file()
    assert log_path.read_text(encoding="utf-8") == "\n- test entry\n"


def test_log_skip_writes_required_fields(bootstrapped_marker):
    """log_skip() always writes timestamp, provider, reason."""
    exc = embeddings.EmbeddingUnavailable(
        reason="not_configured", provider="openai", detail="no api key"
    )
    embeddings.log_skip(exc)

    from scripts.db import memex_home

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert "provider=openai" in log
    assert "reason=not_configured" in log
    assert "timestamp=" in log
    assert "detail=no api key" in log


def test_log_skip_omits_empty_optional_fields(bootstrapped_marker):
    """Omitted optional fields are absent from the row entirely — never
    written as 'field=' with empty value."""
    exc = embeddings.EmbeddingUnavailable(reason="unknown", provider="local")
    embeddings.log_skip(exc)  # no caller_agent_id, index_id, input_chars

    from scripts.db import memex_home

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert "caller=" not in log
    assert "index_id=" not in log
    assert "input_chars=" not in log
    assert "detail=" not in log  # detail also empty


def test_log_skip_includes_optional_fields_when_provided(bootstrapped_marker):
    exc = embeddings.EmbeddingUnavailable(
        reason="oversize_input", provider="voyage", detail="token cap exceeded"
    )
    embeddings.log_skip(exc, caller_agent_id="librarian-1", index_id="abc-123", input_chars=42189)

    from scripts.db import memex_home

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert "caller=librarian-1" in log
    assert "index_id=abc-123" in log
    assert "input_chars=42189" in log


def test_log_skip_truncates_long_detail(bootstrapped_marker):
    """detail is truncated to 200 chars in the audit row."""
    long_detail = "x" * 500
    exc = embeddings.EmbeddingUnavailable(
        reason="provider_error", provider="openai", detail=long_detail
    )
    embeddings.log_skip(exc)

    from scripts.db import memex_home

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert "x" * 200 in log
    assert "x" * 201 not in log


def test_log_skip_escapes_pipe_in_detail(bootstrapped_marker):
    """Literal | in detail is replaced with / to keep rows parseable."""
    exc = embeddings.EmbeddingUnavailable(
        reason="provider_error", provider="openai", detail="error | with | pipes"
    )
    embeddings.log_skip(exc)

    from scripts.db import memex_home

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert "error / with / pipes" in log
    assert "error | with" not in log


def test_log_skip_collapses_newlines_in_detail(bootstrapped_marker):
    """Literal \\r and \\n in detail collapsed to single space — keeps the
    single-line markdown bullet intact when provider errors carry stack
    fragments."""
    exc = embeddings.EmbeddingUnavailable(
        reason="provider_error",
        provider="openai",
        detail="line one\nline two\r\nline three\rline four",
    )
    embeddings.log_skip(exc)

    from scripts.db import memex_home

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    # Detail substring should contain only one bullet's worth of text — no
    # embedded newlines that would break parsing.
    detail_line = next(line for line in log.splitlines() if "detail=" in line)
    assert "\n" not in detail_line and "\r" not in detail_line
    assert "line one line two line three line four" in detail_line


# ── encode_or_skip ────────────────────────────────────────────────────────


def test_encode_or_skip_returns_blob_on_success(bootstrapped_marker):
    """On success encode_or_skip returns the encoded BLOB, same as encode()."""
    with patch("scripts.embeddings._call_provider", return_value=[0.1, 0.2, 0.3]):
        result = embeddings.encode_or_skip("hello")
    assert isinstance(result, bytes)
    assert len(result) == 12  # 3 floats * 4 bytes


def test_encode_or_skip_logs_and_returns_none(bootstrapped_marker, monkeypatch):
    """On EmbeddingUnavailable, returns None and writes a skip row whose
    input_chars defaults to len(text)."""

    def fake_encode(text):
        raise embeddings.EmbeddingUnavailable(
            reason="provider_error", provider="openai", detail="transient"
        )

    monkeypatch.setattr("scripts.embeddings.encode", fake_encode)

    result = embeddings.encode_or_skip("hello world", caller_agent_id="librarian-1")
    assert result is None

    from scripts.db import memex_home

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert "reason=provider_error" in log
    assert "caller=librarian-1" in log
    assert f"input_chars={len('hello world')}" in log


def test_encode_or_skip_input_chars_zero_omits_field(bootstrapped_marker, monkeypatch):
    """input_chars=0 is honored and (being falsy) omits the field from the
    row — log_skip treats 0 as absent."""

    def fake_encode(text):
        raise embeddings.EmbeddingUnavailable(reason="unknown", provider="local")

    monkeypatch.setattr("scripts.embeddings.encode", fake_encode)

    result = embeddings.encode_or_skip("some text", input_chars=0)
    assert result is None

    from scripts.db import memex_home

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert "reason=unknown" in log
    assert "input_chars=" not in log


def test_encode_or_skip_propagates_non_embedding_errors(bootstrapped_marker, monkeypatch):
    """Only EmbeddingUnavailable is caught; a real bug propagates unchanged."""

    def fake_encode(text):
        raise ValueError("boom")

    monkeypatch.setattr("scripts.embeddings.encode", fake_encode)

    with pytest.raises(ValueError, match="boom"):
        embeddings.encode_or_skip("hello")


# ── Caller-loop behavior ──────────────────────────────────────────────────


def test_backfill_null_logs_skip_and_continues(bootstrapped_marker, monkeypatch):
    """backfill_null catches EmbeddingUnavailable narrowly, logs each skip,
    and continues processing remaining rows."""
    from scripts.db import get_connection, memex_home

    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    conn.executescript(
        """
        CREATE TABLE documents (
            index_id TEXT PRIMARY KEY,
            searchable TEXT,
            embedding BLOB
        );
        INSERT INTO documents VALUES ('id-1', 'text 1', NULL);
        INSERT INTO documents VALUES ('id-2', 'text 2', NULL);
        INSERT INTO documents VALUES ('id-3', 'text 3', NULL);
        """
    )
    conn.commit()
    conn.close()

    calls = {"n": 0}

    def fake_encode(text):
        calls["n"] += 1
        if calls["n"] == 2:
            raise embeddings.EmbeddingUnavailable(
                reason="provider_error", provider="openai", detail="transient"
            )
        return b"\x00" * 4

    monkeypatch.setattr("scripts.embeddings.encode", fake_encode)

    summary = embeddings.backfill_null()
    assert summary["considered"] == 3
    assert summary["encoded"] == 2
    assert summary["errors"] == 1

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert log.count("reason=provider_error") == 1


def test_reembed_all_logs_skip_and_continues(bootstrapped_marker, monkeypatch):
    """reembed_all catches EmbeddingUnavailable narrowly, logs each skip,
    and continues processing remaining rows."""
    from scripts.db import get_connection, memex_home

    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    conn.executescript(
        """
        CREATE TABLE documents (
            index_id TEXT PRIMARY KEY,
            searchable TEXT,
            embedding BLOB
        );
        INSERT INTO documents VALUES ('id-1', 'text 1', x'00000000');
        INSERT INTO documents VALUES ('id-2', 'text 2', x'00000000');
        """
    )
    conn.commit()
    conn.close()

    def fake_encode(text):
        raise embeddings.EmbeddingUnavailable(
            reason="not_configured", provider="openai", detail="no key"
        )

    monkeypatch.setattr("scripts.embeddings.encode", fake_encode)

    summary = embeddings.reembed_all()
    assert summary["considered"] == 2
    assert summary["encoded"] == 0
    assert summary["errors"] == 2

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert log.count("reason=not_configured") == 2
