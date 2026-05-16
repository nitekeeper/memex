"""Embedding encode/cosine helpers with pluggable provider.

v2.0 supports three providers, selected via env var MEMEX_EMBEDDING_PROVIDER
(default: 'openai'):

    openai (default) — OpenAI text-embedding-3-small (1536-dim).
                       Requires OPENAI_API_KEY. SDK: `openai`.

    voyage           — Voyage AI voyage-3 (1024-dim). Anthropic-recommended
                       partner. Requires VOYAGE_API_KEY. SDK: `voyageai`.

    local            — sentence-transformers all-MiniLM-L6-v2 (384-dim).
                       No API key; offline-capable. First call downloads
                       ~80MB model. SDK: `sentence_transformers`.

Each provider's SDK is imported lazily — installing the `memex` package
itself does NOT require any of these libraries; only the provider you
actually configure needs to be installed.

Vectors are packed as little-endian float32 BLOBs in
`index.db.documents.embedding`. The active provider + model + dim are
recorded in `~/.memex/registry.json` under the reserved key
`__embedding_model__` so backfill/reembed tooling can detect changes.
"""
from __future__ import annotations
import os
import math
import struct
from typing import List


# ── Provider defaults ─────────────────────────────────────────────────────

# Per-provider model defaults. Override at the env-var level if you want a
# different model from the same provider (no separate code path needed):
#   $env:MEMEX_OPENAI_MODEL = "text-embedding-3-large"
#   $env:MEMEX_VOYAGE_MODEL = "voyage-3-large"
#   $env:MEMEX_LOCAL_MODEL  = "all-mpnet-base-v2"
_OPENAI_DEFAULT_MODEL = "text-embedding-3-small"
_VOYAGE_DEFAULT_MODEL = "voyage-3"
_LOCAL_DEFAULT_MODEL = "all-MiniLM-L6-v2"

# Back-compat constants (old callers / tests referenced these directly).
DEFAULT_MODEL = _OPENAI_DEFAULT_MODEL
DEFAULT_DIM = 1536


# ── Pack / unpack ─────────────────────────────────────────────────────────


def _pack(vec: List[float]) -> bytes:
    """Pack a list of floats as little-endian float32 BLOB."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack(blob: bytes) -> List[float]:
    """Unpack a float32 BLOB to a list of floats."""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


# ── Provider dispatch ─────────────────────────────────────────────────────


def _active_provider() -> str:
    return os.environ.get("MEMEX_EMBEDDING_PROVIDER", "openai")


def _active_model() -> str:
    """Return the configured model name for the active provider."""
    provider = _active_provider()
    if provider == "openai":
        return os.environ.get("MEMEX_OPENAI_MODEL", _OPENAI_DEFAULT_MODEL)
    if provider == "voyage":
        return os.environ.get("MEMEX_VOYAGE_MODEL", _VOYAGE_DEFAULT_MODEL)
    if provider == "local":
        return os.environ.get("MEMEX_LOCAL_MODEL", _LOCAL_DEFAULT_MODEL)
    raise ValueError(f"Unknown embedding provider: {provider}")


def _call_provider(text: str) -> List[float]:
    """Call the configured embedding provider. Returns a list of floats."""
    provider = _active_provider()
    if provider == "openai":
        return _openai_encode(text)
    elif provider == "voyage":
        return _voyage_encode(text)
    elif provider == "local":
        return _local_encode(text)
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


def _openai_encode(text: str) -> List[float]:
    """Call OpenAI text-embedding-3-small (or `MEMEX_OPENAI_MODEL` override).
    Requires OPENAI_API_KEY env var. Lazy import so the SDK isn't required
    when using a different provider."""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "openai SDK is not installed. `pip install openai`, "
            "or switch to a different provider via MEMEX_EMBEDDING_PROVIDER."
        ) from e
    client = OpenAI()
    model = _active_model()
    resp = client.embeddings.create(input=text, model=model)
    return list(resp.data[0].embedding)


def _voyage_encode(text: str) -> List[float]:
    """Call Voyage voyage-3 (or `MEMEX_VOYAGE_MODEL` override). Requires
    VOYAGE_API_KEY env var. Anthropic recommends Voyage for embeddings
    used alongside Claude. Lazy import."""
    try:
        import voyageai
    except ImportError as e:
        raise RuntimeError(
            "voyageai SDK is not installed. `pip install voyageai`, "
            "or switch to a different provider via MEMEX_EMBEDDING_PROVIDER."
        ) from e
    if not os.environ.get("VOYAGE_API_KEY"):
        raise RuntimeError(
            "VOYAGE_API_KEY environment variable is not set."
        )
    client = voyageai.Client()  # picks up VOYAGE_API_KEY from env
    model = _active_model()
    # Voyage's SDK takes a list and returns an EmbeddingsObject with
    # `.embeddings` -> list[list[float]]. Pass a single-item list, take [0].
    result = client.embed([text], model=model, input_type="document")
    return list(result.embeddings[0])


# Cache the local model instance so repeated calls don't reload the
# ~80MB SentenceTransformer weights on every encode().
_LOCAL_MODEL_CACHE: dict[str, object] = {}


def _voyage_dim(model: str) -> int:
    """Known output dimensions for Voyage models. Returns -1 if unknown
    (will be filled in after the first real call via _record_model_info)."""
    return {
        "voyage-3": 1024,
        "voyage-3-lite": 512,
        "voyage-3-large": 1024,
        "voyage-code-3": 1024,
    }.get(model, -1)


def _local_encode(text: str) -> List[float]:
    """Call sentence-transformers (default model all-MiniLM-L6-v2, 384-dim).
    No API key required. First call downloads model weights (~80MB) to the
    HuggingFace cache. Lazy import + cached model instance."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "`pip install sentence-transformers`, "
            "or switch to a different provider via MEMEX_EMBEDDING_PROVIDER."
        ) from e
    model_name = _active_model()
    model = _LOCAL_MODEL_CACHE.get(model_name)
    if model is None:
        # Loads from HuggingFace on first use; cached afterward.
        model = SentenceTransformer(model_name)
        _LOCAL_MODEL_CACHE[model_name] = model
    vec = model.encode(text, convert_to_numpy=False, normalize_embeddings=False)
    # sentence-transformers returns either a Tensor or a list-like; coerce to list[float].
    if hasattr(vec, "tolist"):
        return [float(x) for x in vec.tolist()]
    return [float(x) for x in vec]


# ── Model-info recording (for backfill / reembed detection) ───────────────


def _record_model_info(dim: int) -> None:
    """Record the active embedding provider + model + dimensionality in
    registry.json under `__embedding_model__`. Used by backfill and reembed
    tooling to detect changes that invalidate existing embeddings."""
    from scripts import registry
    data = registry._load()
    data["__embedding_model__"] = {
        "provider": _active_provider(),
        "model": _active_model(),
        "dim": dim,
    }
    registry._save(data)


def active_model_info() -> dict:
    """Return the currently-active provider + model + (best-known) dim,
    without making an API call. dim is -1 for OpenAI / local until we've
    encoded at least one text (it's then recorded in registry.json), and
    drawn from `_voyage_dim` for Voyage.

    Backfill / reembed tooling uses this to compare against
    registry.json:__embedding_model__ and detect mismatches.
    """
    provider = _active_provider()
    model = _active_model()
    if provider == "voyage":
        dim = _voyage_dim(model)
    elif provider == "openai" and model == "text-embedding-3-small":
        dim = 1536
    elif provider == "openai" and model == "text-embedding-3-large":
        dim = 3072
    elif provider == "local" and model == "all-MiniLM-L6-v2":
        dim = 384
    elif provider == "local" and model == "all-mpnet-base-v2":
        dim = 768
    else:
        dim = -1
    return {"provider": provider, "model": model, "dim": dim}


def recorded_model_info() -> dict | None:
    """Return the LAST recorded provider/model/dim from registry.json, or
    None if nothing has been recorded yet."""
    from scripts import registry
    return registry._load().get("__embedding_model__")


# ── Public API ────────────────────────────────────────────────────────────


def encode(text: str) -> bytes:
    """Encode text -> float32 BLOB. Records model info on every call so
    registry.json stays in sync with what's actually being used."""
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
