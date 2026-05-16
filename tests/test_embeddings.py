"""Embeddings tests — pack/cosine round-trip + provider dispatch.

All three providers (openai, voyage, local) are now wired. SDK imports
happen lazily; tests mock the SDKs so they pass without any of them
installed and without any API keys configured.
"""
import os
import struct
import sys
import types
import pytest
from unittest.mock import patch, MagicMock
from scripts import embeddings


# ── pack / unpack / cosine ─────────────────────────────────────────────────


def test_encode_returns_blob():
    with patch("scripts.embeddings._call_provider", return_value=[0.1, 0.2, 0.3]):
        result = embeddings.encode("hello")
    assert isinstance(result, bytes)
    assert len(result) == 12  # 3 floats × 4 bytes


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
    assert info["provider"] == "openai"          # default
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
    fake_client.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1] * 1536)]
    )
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
