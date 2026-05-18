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

import math
import os
import struct

from scripts.db import require_bootstrap

# ── Typed failure ─────────────────────────────────────────────────────────


class EmbeddingUnavailable(Exception):
    """Raised by encode() when no embedding can be produced for the input.

    Callers may catch and proceed with embedding=None (FTS5-only indexing)
    or surface as fatal — degraded-mode semantics, not an error.

    The four `reason` values are the frozen contract for consumers
    (Atelier, custom plugins) that want to branch on cause:

      - "not_configured"  → API key missing OR provider SDK not installed
      - "oversize_input"  → provider rejected text for exceeding token cap
      - "provider_error"  → network/rate-limit/5xx/parse fail from provider
      - "unknown"         → defensive catch-all for unexpected leaks

    Always raised via `raise EmbeddingUnavailable(...) from original_exc`
    so __cause__ preserves the original traceback.

    See docs/specs/2026-05-17-embedding-unavailable-design.md for the
    full contract.

    Attributes:
        reason:   one of the four frozen values above; branch on this.
        provider: the configured provider name at raise time (e.g. 'openai').
        detail:   optional human-readable elaboration; may be empty string.
    """

    def __init__(self, reason: str, provider: str, detail: str = ""):
        self.reason = reason
        self.provider = provider
        self.detail = detail
        super().__init__(
            f"embedding unavailable (provider={provider!r}, reason={reason!r})"
            + (f": {detail}" if detail else "")
        )


# ── Skip log ──────────────────────────────────────────────────────────────


def _append_skip_log(entry: str) -> None:
    """Append a single audit row to ~/.memex/audits/embedding-skip-log.md.
    Mirrors data_steward._append_audit's shape; private file-write
    primitive. I/O exceptions propagate by design.
    """
    from scripts.db import memex_home

    audits_dir = memex_home() / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)
    log_path = audits_dir / "embedding-skip-log.md"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


def log_skip(
    exc: EmbeddingUnavailable,
    *,
    caller_agent_id: str = "",
    index_id: str = "",
    input_chars: int = 0,
) -> None:
    """Public helper for callers to emit a structured audit row for an
    EmbeddingUnavailable they caught. Writes to
    ~/.memex/audits/embedding-skip-log.md.

    Row format: single-line markdown bullet, ISO-8601 UTC timestamp,
    pipe-separated `key=value` fields. Mirrors data_steward._append_audit's
    shape. Omitted optional fields (empty caller_agent_id / index_id /
    input_chars=0) are absent from the row entirely — no empty `field=`
    form is written.

    `detail` is sanitized for log readability: literal `|` → `/`, literal
    `\\r`/`\\n` → single space; then truncated to 200 chars. Full
    traceback is always available via `exc.__cause__`.

    I/O exceptions from the audit-log write (disk full, file locked, etc.)
    propagate by design — matches data_steward._append_audit's behavior.
    Consumers requiring isolation from audit-write failure should wrap
    log_skip() in their own try/except so audit failure cannot mask the
    original embedding skip.
    """
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).isoformat()
    fields = [
        f"timestamp={ts}",
        f"provider={exc.provider}",
        f"reason={exc.reason}",
    ]
    if caller_agent_id:
        fields.append(f"caller={caller_agent_id}")
    if index_id:
        fields.append(f"index_id={index_id}")
    if input_chars:
        fields.append(f"input_chars={input_chars}")
    if exc.detail:
        sanitized = (
            exc.detail.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("|", "/")
        )[:200]
        fields.append(f"detail={sanitized}")
    entry = "\n- " + " | ".join(fields) + "\n"
    _append_skip_log(entry)


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


def _pack(vec: list[float]) -> bytes:
    """Pack a list of floats as little-endian float32 BLOB."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
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


def _call_provider(text: str) -> list[float]:
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


def _openai_encode(text: str) -> list[float]:
    """Call OpenAI text-embedding-3-small (or `MEMEX_OPENAI_MODEL` override).
    Requires OPENAI_API_KEY env var. Lazy import so the SDK isn't required
    when using a different provider.

    Raises EmbeddingUnavailable with classified reason:
      - not_configured: SDK missing OR OPENAI_API_KEY unset
      - oversize_input: BadRequestError with 'context_length_exceeded'
      - provider_error: any other failure from the API call
    """
    try:
        from openai import BadRequestError, OpenAI
    except ImportError as e:
        raise EmbeddingUnavailable(
            "not_configured",
            "openai",
            "openai SDK not installed (`pip install openai`)",
        ) from e
    try:
        client = OpenAI()  # raises on misconfiguration (missing key, malformed base URL, etc.)
    except Exception as e:
        raise EmbeddingUnavailable("not_configured", "openai", str(e)) from e
    model = _active_model()
    try:
        resp = client.embeddings.create(input=text, model=model)
    except Exception as e:
        if isinstance(e, BadRequestError) and "context_length_exceeded" in str(e):
            raise EmbeddingUnavailable("oversize_input", "openai", str(e)) from e
        raise EmbeddingUnavailable("provider_error", "openai", str(e)) from e
    return list(resp.data[0].embedding)


def _voyage_encode(text: str) -> list[float]:
    """Call Voyage voyage-3 (or `MEMEX_VOYAGE_MODEL` override). Requires
    VOYAGE_API_KEY env var. Anthropic recommends Voyage for embeddings
    used alongside Claude. Lazy import.

    Raises EmbeddingUnavailable with classified reason:
      - not_configured: SDK missing OR VOYAGE_API_KEY unset
      - oversize_input: error message matches token-limit shape
      - provider_error: any other failure from the API call
    """
    try:
        import voyageai
    except ImportError as e:
        raise EmbeddingUnavailable(
            "not_configured",
            "voyage",
            "voyageai SDK not installed (`pip install voyageai`)",
        ) from e
    if not os.environ.get("VOYAGE_API_KEY"):
        raise EmbeddingUnavailable(
            "not_configured", "voyage", "VOYAGE_API_KEY environment variable is not set"
        )
    try:
        client = voyageai.Client()
        result = client.embed([text], model=_active_model(), input_type="document")
    except Exception as e:
        msg = str(e).lower()
        if "token" in msg and ("exceed" in msg or "limit" in msg):
            raise EmbeddingUnavailable("oversize_input", "voyage", str(e)) from e
        raise EmbeddingUnavailable("provider_error", "voyage", str(e)) from e
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


def _local_encode(text: str) -> list[float]:
    """Call sentence-transformers (default model all-MiniLM-L6-v2, 384-dim).
    No API key required. First call downloads model weights (~80MB) to the
    HuggingFace cache. Lazy import + cached model instance.

    Raises EmbeddingUnavailable with classified reason:
      - not_configured: sentence-transformers not installed
      - oversize_input: tokenizer overflow / max-length error
      - provider_error: any other failure (model load, corrupt cache, etc.)
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError as e:
        raise EmbeddingUnavailable(
            "not_configured",
            "local",
            "sentence-transformers not installed (`pip install sentence-transformers`)",
        ) from e
    model_name = _active_model()
    try:
        model = _LOCAL_MODEL_CACHE.get(model_name)
        if model is None:
            model = SentenceTransformer(model_name)
            _LOCAL_MODEL_CACHE[model_name] = model
        vec = model.encode(text, convert_to_numpy=False, normalize_embeddings=False)
    except Exception as e:
        msg = str(e).lower()
        if any(tok in msg for tok in ("max_seq_length", "exceeds", "too long")):
            raise EmbeddingUnavailable("oversize_input", "local", str(e)) from e
        raise EmbeddingUnavailable("provider_error", "local", str(e)) from e
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

    No bootstrap guard: pure env-var read, no filesystem side effects.
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
    require_bootstrap()
    from scripts import registry

    return registry._load().get("__embedding_model__")


# ── Public API ────────────────────────────────────────────────────────────


def encode(text: str) -> bytes:
    """Encode text -> float32 BLOB.

    Records model info on every successful call so registry.json stays in
    sync with what's actually being used.

    Raises EmbeddingUnavailable on any failure. The four reason values are
    the frozen contract (see EmbeddingUnavailable docstring). Per-provider
    encoders classify their own failure modes; this central wrapper only
    catches the defensive `unknown` case for unexpected leaks.
    """
    require_bootstrap()
    try:
        vec = _call_provider(text)
    except EmbeddingUnavailable:
        raise  # already classified by the provider function
    except Exception as e:
        raise EmbeddingUnavailable("unknown", _active_provider(), str(e)) from e
    _record_model_info(len(vec))
    return _pack(vec)


# ── Backfill / reembed ────────────────────────────────────────────────────


def backfill_null(batch_size: int = 100, dry_run: bool = False) -> dict:
    """Re-encode every documents row with `embedding IS NULL` using the
    currently-active provider. Idempotent — non-NULL rows are left alone.

    Use after configuring an embedding provider for the first time, or
    after ingesting documents with no provider configured (FTS5-only mode).

    Args:
        batch_size: how many rows to encode before committing. Higher = fewer
            commits but more loss on crash. Default 100.
        dry_run: if True, count the NULL rows and report what WOULD happen
            without making any API calls or DB writes.

    Returns:
        {"considered": N, "encoded": M, "errors": E,
         "provider": ..., "model": ..., "dim": ...,
         "dry_run": bool}.

    The skill markdown (`internal/embed/backfill/SKILL.md`) wraps this
    helper. Callers do NOT need to be in a Claude Code session — this is
    pure Python with no Task-tool dispatch.
    """
    require_bootstrap()
    from scripts.db import get_connection, memex_home

    index_db = str(memex_home() / "index.db")
    info = active_model_info()

    conn = get_connection(index_db)
    null_rows = conn.execute(
        "SELECT index_id, searchable FROM documents WHERE embedding IS NULL"
    ).fetchall()
    conn.close()

    summary = {
        "considered": len(null_rows),
        "encoded": 0,
        "errors": 0,
        "provider": info["provider"],
        "model": info["model"],
        "dim": info["dim"],
        "dry_run": dry_run,
    }
    if dry_run or not null_rows:
        return summary

    conn = get_connection(index_db)
    try:
        for i, row in enumerate(null_rows):
            try:
                blob = encode(row["searchable"] or "")
            except EmbeddingUnavailable as e:
                log_skip(
                    e,
                    index_id=row["index_id"],
                    input_chars=len(row["searchable"] or ""),
                )
                summary["errors"] += 1
                continue
            conn.execute(
                "UPDATE documents SET embedding = ? WHERE index_id = ?",
                (blob, row["index_id"]),
            )
            summary["encoded"] += 1
            if (i + 1) % batch_size == 0:
                conn.commit()
        conn.commit()
    finally:
        conn.close()
    return summary


def reembed_all(batch_size: int = 100, dry_run: bool = False) -> dict:
    """Re-encode EVERY documents row (NULL and non-NULL) using the active
    provider. Use after a deliberate provider/model change — existing
    embeddings from the old model are dimensionally or semantically
    incomparable.

    Heavier than backfill_null — touches every row. Run when needed, not
    on a schedule.

    Args:
        batch_size, dry_run: same as backfill_null.

    Returns: same shape as backfill_null, plus
        "previous_recorded": {provider, model, dim} | None  — what
            registry.json's __embedding_model__ said BEFORE this call.

    The skill markdown (`internal/embed/reembed/SKILL.md`) wraps this
    helper and adds a confirmation prompt because this is destructive
    (existing embeddings are overwritten).
    """
    require_bootstrap()
    from scripts.db import get_connection, memex_home

    index_db = str(memex_home() / "index.db")
    info = active_model_info()
    previous = recorded_model_info()

    conn = get_connection(index_db)
    all_rows = conn.execute("SELECT index_id, searchable FROM documents").fetchall()
    conn.close()

    summary = {
        "considered": len(all_rows),
        "encoded": 0,
        "errors": 0,
        "provider": info["provider"],
        "model": info["model"],
        "dim": info["dim"],
        "previous_recorded": previous,
        "dry_run": dry_run,
    }
    if dry_run or not all_rows:
        return summary

    conn = get_connection(index_db)
    try:
        for i, row in enumerate(all_rows):
            try:
                blob = encode(row["searchable"] or "")
            except EmbeddingUnavailable as e:
                log_skip(
                    e,
                    index_id=row["index_id"],
                    input_chars=len(row["searchable"] or ""),
                )
                summary["errors"] += 1
                continue
            conn.execute(
                "UPDATE documents SET embedding = ? WHERE index_id = ?",
                (blob, row["index_id"]),
            )
            summary["encoded"] += 1
            if (i + 1) % batch_size == 0:
                conn.commit()
        conn.commit()
    finally:
        conn.close()
    return summary


def detect_model_change() -> dict | None:
    """Compare the currently-active provider/model against what's recorded
    in registry.json. Returns None if they match (or nothing was ever
    recorded), otherwise a dict describing the drift:

        {"active": {provider, model, dim},
         "recorded": {provider, model, dim},
         "changed": ["provider" | "model" | "dim", ...]}

    Used by the reembed skill to warn the user before re-encoding.
    """
    require_bootstrap()
    active = active_model_info()
    recorded = recorded_model_info()
    if recorded is None:
        return None
    changed: list[str] = []
    for key in ("provider", "model", "dim"):
        if active.get(key) != recorded.get(key):
            changed.append(key)
    if not changed:
        return None
    return {"active": active, "recorded": recorded, "changed": changed}


# ── Cosine ────────────────────────────────────────────────────────────────


def cosine(blob_a: bytes, blob_b: bytes) -> float:
    """Cosine similarity between two packed embedding BLOBs."""
    a = _unpack(blob_a)
    b = _unpack(blob_b)
    if len(a) != len(b):
        raise ValueError(f"Dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
