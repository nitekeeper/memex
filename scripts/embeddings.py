"""Embedding encode/cosine helpers with pluggable provider.

v2.0 default: OpenAI text-embedding-3-small (1536-dim).
Provider is selected via env var MEMEX_EMBEDDING_PROVIDER (default: 'openai').
Alternative providers (voyage, anthropic, local) implement _call_provider
under their respective module path; this file imports them lazily.

Vectors are packed as little-endian float32 BLOBs in index.db.documents.embedding.
"""
from __future__ import annotations
import os
import math
import struct
import json
from typing import List
from scripts.db import memex_home

DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIM = 1536


def _pack(vec: List[float]) -> bytes:
    """Pack a list of floats as little-endian float32 BLOB."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack(blob: bytes) -> List[float]:
    """Unpack a float32 BLOB to a list of floats."""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def _call_provider(text: str) -> List[float]:
    """Call the configured embedding provider. Returns a list of floats."""
    provider = os.environ.get("MEMEX_EMBEDDING_PROVIDER", "openai")
    if provider == "openai":
        return _openai_encode(text)
    elif provider == "voyage":
        return _voyage_encode(text)
    elif provider == "local":
        return _local_encode(text)
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


def _openai_encode(text: str) -> List[float]:
    """Call OpenAI text-embedding-3-small. Requires OPENAI_API_KEY env var.
    Lazy import so the package isn't required when using a different provider."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.embeddings.create(input=text, model=DEFAULT_MODEL)
    return resp.data[0].embedding


def _voyage_encode(text: str) -> List[float]:
    """Stub: implement when switching to Voyage. Imports lazily."""
    raise NotImplementedError("Voyage provider not yet wired")


def _local_encode(text: str) -> List[float]:
    """Stub: implement with sentence-transformers when switching to local."""
    raise NotImplementedError("Local provider not yet wired")


def _record_model_info(dim: int) -> None:
    """Record the active embedding model + dimensionality in registry.json
    under a reserved key. Used by re-embed tooling to detect changes."""
    from scripts import registry
    data = registry._load()
    data["__embedding_model__"] = {
        "provider": os.environ.get("MEMEX_EMBEDDING_PROVIDER", "openai"),
        "model": DEFAULT_MODEL,
        "dim": dim,
    }
    registry._save(data)


def encode(text: str) -> bytes:
    """Encode text -> float32 BLOB. Records model info on first call."""
    vec = _call_provider(text)
    _record_model_info(len(vec))
    return _pack(vec)


def cosine(blob_a: bytes, blob_b: bytes) -> float:
    """Cosine similarity between two packed embedding BLOBs."""
    a = _unpack(blob_a)
    b = _unpack(blob_b)
    if len(a) != len(b):
        raise ValueError(f"Dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
