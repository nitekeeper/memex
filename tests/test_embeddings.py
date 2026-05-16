import struct
import pytest
from unittest.mock import patch, MagicMock
from scripts import embeddings


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


def test_encode_caches_model_in_registry():
    """When encode runs, the model+dim must be recorded in ~/.memex/registry.json
    under a known key so re-embed/migration tooling can detect changes."""
    with patch("scripts.embeddings._call_provider", return_value=[0.0] * 1536):
        embeddings.encode("hello")
    from scripts import registry
    info = registry._load().get("__embedding_model__")
    assert info is not None
    assert info["dim"] == 1536
