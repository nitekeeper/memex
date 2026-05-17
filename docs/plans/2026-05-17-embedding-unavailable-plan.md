# EmbeddingUnavailable + skip log (v2.4.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the silent broad-`Exception` swallow at every `embeddings.encode()` call site with a typed `EmbeddingUnavailable` raise + structured audit-log entry, so operators see why embeddings are missing and consumers (Atelier) can narrow their catches.

**Architecture:** Per-provider classification keeps the existing lazy-import contract intact; central `encode()` is a thin pass-through with a defensive `unknown` wrapper. New `~/.memex/audits/embedding-skip-log.md` collects structured skip rows via a `log_skip()` helper mirroring `data_steward._append_audit`. All caller sites (8 audited: 6 skill markdown + 2 Python) tighten their broad `except Exception:` to `except embeddings.EmbeddingUnavailable as e:` and emit `embeddings.log_skip(e, ...)`. Behavior-preserving on happy path; failure path still ends at `embedding = None` but is now visible.

**Tech Stack:** Python 3.10+, pytest with monkeypatch, existing `scripts/embeddings.py` provider plumbing (OpenAI / Voyage / sentence-transformers), existing `data_steward._append_audit()` pattern for audit-log writes.

**Spec:** [docs/specs/2026-05-17-embedding-unavailable-design.md](../specs/2026-05-17-embedding-unavailable-design.md)

---

## File Map

| File | Responsibility | Change type |
|---|---|---|
| `scripts/embeddings.py` | Exception class, per-provider classify, central encode wrap, skip-log helpers, tightened backfill/reembed | Modify |
| `tests/test_embeddings.py` | Groups A–D test coverage | Modify |
| `internal/index/write/SKILL.md` | Step 4 tighten | Modify |
| `internal/index/search/SKILL.md` | Step 4 fallback tighten | Modify |
| `internal/brain/ingest/SKILL.md` | Encode catch tighten | Modify |
| `internal/brain/capture/SKILL.md` | Encode catch tighten | Modify |
| `internal/brain/synthesize/SKILL.md` | Encode catch tighten | Modify |
| `internal/brain/ask/SKILL.md` | Catch instruction tighten | Modify |
| `docs/specs/2026-05-16-memex-v2-redesign-design.md` | New §6.5 + DL-#26 | Modify |
| `USER_GUIDE.md` | New audit-logs subsection | Modify |
| `CHANGELOG.md` | v2.4.1 entry | Modify |
| `plugin.json`, `pyproject.toml` | Version bump (via `scripts/bump.py`) | Modify (mechanical) |

---

## Phase 1 — Foundation: `EmbeddingUnavailable` class

### Task 1: Exception class + Group A tests

**Files:**
- Modify: `scripts/embeddings.py` (add class after the module docstring, before `_OPENAI_DEFAULT_MODEL`)
- Modify: `tests/test_embeddings.py` (append new test section)

- [ ] **Step 1: Write the failing tests (Group A — 4 tests)**

Append to `tests/test_embeddings.py`:

```python
# ── EmbeddingUnavailable class (Group A) ──────────────────────────────────


def test_embedding_unavailable_stores_fields():
    exc = embeddings.EmbeddingUnavailable(
        reason="not_configured", provider="openai", detail="no api key"
    )
    assert exc.reason == "not_configured"
    assert exc.provider == "openai"
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
    try:
        try:
            raise original
        except RuntimeError as e:
            raise embeddings.EmbeddingUnavailable(
                reason="provider_error", provider="openai", detail=str(e)
            ) from e
    except embeddings.EmbeddingUnavailable as exc:
        assert exc.__cause__ is original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embeddings.py -k "embedding_unavailable" -v`
Expected: 4 FAILs with `AttributeError: module 'scripts.embeddings' has no attribute 'EmbeddingUnavailable'`

- [ ] **Step 3: Add the class to `scripts/embeddings.py`**

Insert immediately after the module docstring (after the `"""` close around line 24), before the `# ── Provider defaults ─` comment:

```python
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
    full contract."""

    def __init__(self, reason: str, provider: str, detail: str = ""):
        self.reason = reason
        self.provider = provider
        self.detail = detail
        super().__init__(
            f"embedding unavailable (provider={provider!r}, reason={reason!r})"
            + (f": {detail}" if detail else "")
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -k "embedding_unavailable" -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/embeddings.py tests/test_embeddings.py
git commit -m "embeddings: add EmbeddingUnavailable typed exception (spec §6.5)"
```

---

## Phase 2 — Per-provider classification

### Task 2: OpenAI classification + 3 tests

**Files:**
- Modify: `scripts/embeddings.py` (`_openai_encode` function around line 94-108)
- Modify: `tests/test_embeddings.py` (append OpenAI classification tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_embeddings.py`:

```python
# ── Per-provider classification (Group B — OpenAI) ────────────────────────


def test_openai_not_configured_on_import_error(monkeypatch):
    """ImportError on `from openai import OpenAI` → reason='not_configured'."""
    # Force ImportError by removing openai from sys.modules and blocking it
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
    assert exc_info.value.provider == "openai"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embeddings.py -k "openai_not_configured or openai_oversize or openai_provider_error" -v`
Expected: 3 FAILs (current `_openai_encode` raises a generic `RuntimeError`, not `EmbeddingUnavailable`).

- [ ] **Step 3: Rewrite `_openai_encode`**

Replace the entire current `_openai_encode` function in `scripts/embeddings.py` (around line 94-108):

```python
def _openai_encode(text: str) -> list[float]:
    """Call OpenAI text-embedding-3-small (or `MEMEX_OPENAI_MODEL` override).
    Requires OPENAI_API_KEY env var. Lazy import so the SDK isn't required
    when using a different provider.

    Raises EmbeddingUnavailable with classified reason:
      - not_configured: SDK missing OR OPENAI_API_KEY unset
      - oversize_input: BadRequestError with 'context_length_exceeded'
      - provider_error: any other failure from the API call"""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise EmbeddingUnavailable(
            "not_configured",
            "openai",
            "openai SDK not installed (`pip install openai`)",
        ) from e
    try:
        client = OpenAI()  # raises if OPENAI_API_KEY missing
    except Exception as e:
        raise EmbeddingUnavailable("not_configured", "openai", str(e)) from e
    model = _active_model()
    try:
        resp = client.embeddings.create(input=text, model=model)
    except Exception as e:
        try:
            from openai import BadRequestError

            is_oversize = isinstance(e, BadRequestError) and "context_length_exceeded" in str(e)
        except ImportError:
            is_oversize = False
        if is_oversize:
            raise EmbeddingUnavailable("oversize_input", "openai", str(e)) from e
        raise EmbeddingUnavailable("provider_error", "openai", str(e)) from e
    return list(resp.data[0].embedding)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -k "openai_not_configured or openai_oversize or openai_provider_error" -v`
Expected: 3 PASS.

Also re-run the full file to ensure no regressions:

Run: `pytest tests/test_embeddings.py -v`
Expected: all existing tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/embeddings.py tests/test_embeddings.py
git commit -m "embeddings: classify OpenAI failures as EmbeddingUnavailable"
```

---

### Task 3: Voyage classification + 4 tests

**Files:**
- Modify: `scripts/embeddings.py` (`_voyage_encode` function around line 111-129)
- Modify: `tests/test_embeddings.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_embeddings.py`:

```python
# ── Per-provider classification (Group B — Voyage) ────────────────────────


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embeddings.py -k "voyage" -v`
Expected: 4 FAILs (current code raises `RuntimeError`).

- [ ] **Step 3: Rewrite `_voyage_encode`**

Replace the entire `_voyage_encode` function in `scripts/embeddings.py`:

```python
def _voyage_encode(text: str) -> list[float]:
    """Call Voyage voyage-3 (or `MEMEX_VOYAGE_MODEL` override). Requires
    VOYAGE_API_KEY env var. Anthropic recommends Voyage for embeddings
    used alongside Claude. Lazy import.

    Raises EmbeddingUnavailable with classified reason."""
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -k "voyage" -v`
Expected: 4 PASS.

Run: `pytest tests/test_embeddings.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/embeddings.py tests/test_embeddings.py
git commit -m "embeddings: classify Voyage failures as EmbeddingUnavailable"
```

---

### Task 4: Local (sentence-transformers) classification + 3 tests

**Files:**
- Modify: `scripts/embeddings.py` (`_local_encode` function around line 148-170)
- Modify: `tests/test_embeddings.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_embeddings.py`:

```python
# ── Per-provider classification (Group B — Local) ─────────────────────────


def test_local_not_configured_on_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "local")
    # Clear the local model cache so the test path is taken
    embeddings._LOCAL_MODEL_CACHE.clear()
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._local_encode("hello")
    assert exc_info.value.reason == "not_configured"
    assert exc_info.value.provider == "local"


def test_local_oversize_input_on_max_seq_length(monkeypatch):
    fake_st = types.ModuleType("sentence_transformers")
    fake_model = MagicMock()
    fake_model.encode.side_effect = RuntimeError(
        "Input length 800 exceeds max_seq_length 512"
    )
    fake_st.SentenceTransformer = MagicMock(return_value=fake_model)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)
    monkeypatch.setenv("MEMEX_EMBEDDING_PROVIDER", "local")
    embeddings._LOCAL_MODEL_CACHE.clear()
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings._local_encode("a" * 5000)
    assert exc_info.value.reason == "oversize_input"


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embeddings.py -k "local_not_configured or local_oversize or local_provider_error" -v`
Expected: 3 FAILs.

- [ ] **Step 3: Rewrite `_local_encode`**

Replace the entire `_local_encode` function in `scripts/embeddings.py`:

```python
def _local_encode(text: str) -> list[float]:
    """Call sentence-transformers (default model all-MiniLM-L6-v2, 384-dim).
    No API key required. First call downloads model weights (~80MB) to the
    HuggingFace cache. Lazy import + cached model instance.

    Raises EmbeddingUnavailable with classified reason."""
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -k "local" -v`
Expected: 3 PASS (plus any pre-existing local tests).

Run: `pytest tests/test_embeddings.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/embeddings.py tests/test_embeddings.py
git commit -m "embeddings: classify local (sentence-transformers) failures as EmbeddingUnavailable"
```

---

### Task 5: Central `encode()` defensive wrap + unknown-leak test

**Files:**
- Modify: `scripts/embeddings.py` (`encode()` function around line 228-233)
- Modify: `tests/test_embeddings.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_embeddings.py`:

```python
# ── Central encode() defensive wrap ────────────────────────────────────────


def test_encode_wraps_unknown_leak(monkeypatch):
    """If _call_provider somehow leaks a non-EmbeddingUnavailable exception,
    encode() must re-raise as EmbeddingUnavailable(reason='unknown')."""
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


def test_encode_passes_through_embedding_unavailable(monkeypatch):
    """If _call_provider raises EmbeddingUnavailable, encode() must re-raise
    it as-is — NOT re-wrap it as reason='unknown'."""
    original = embeddings.EmbeddingUnavailable(
        reason="not_configured", provider="openai", detail="no key"
    )
    monkeypatch.setattr(
        "scripts.embeddings._call_provider",
        MagicMock(side_effect=original),
    )
    with pytest.raises(embeddings.EmbeddingUnavailable) as exc_info:
        embeddings.encode("hello")
    assert exc_info.value is original  # same instance, not re-wrapped
    assert exc_info.value.reason == "not_configured"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embeddings.py -k "encode_wraps_unknown or encode_passes_through" -v`
Expected: `test_encode_wraps_unknown_leak` FAILs (current encode() doesn't wrap); `test_encode_passes_through` may or may not pass (no wrapping currently means natural pass-through).

- [ ] **Step 3: Update `encode()`**

Replace the current `encode()` function (around line 228-233):

```python
def encode(text: str) -> bytes:
    """Encode text -> float32 BLOB.

    Records model info on every successful call so registry.json stays in
    sync with what's actually being used.

    Raises EmbeddingUnavailable on any failure. The four reason values are
    the frozen contract (see EmbeddingUnavailable docstring). Per-provider
    encoders classify their own failure modes; this central wrapper only
    catches the defensive `unknown` case for unexpected leaks."""
    try:
        vec = _call_provider(text)
    except EmbeddingUnavailable:
        raise  # already classified by the provider function
    except Exception as e:
        raise EmbeddingUnavailable("unknown", _active_provider(), str(e)) from e
    _record_model_info(len(vec))
    return _pack(vec)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/embeddings.py tests/test_embeddings.py
git commit -m "embeddings: wrap unknown leaks in encode() as EmbeddingUnavailable"
```

---

## Phase 3 — Skip-log helpers

### Task 6: `_append_skip_log` primitive + dir-creation test

**Files:**
- Modify: `scripts/embeddings.py` (add helpers after the `EmbeddingUnavailable` class definition)
- Modify: `tests/test_embeddings.py`

- [ ] **Step 1: Verify `tmp_memex_home` fixture exists**

The test file uses `tmp_memex_home` (see existing `test_encode_records_model_info`). Confirm it's defined in `tests/conftest.py`:

Run: `grep -n "tmp_memex_home" tests/conftest.py`
Expected: a fixture definition like `@pytest.fixture\ndef tmp_memex_home(...)`. If missing, the fixture must already exist for the existing tests to pass — proceed.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_embeddings.py`:

```python
# ── Skip log helper (Group C) ──────────────────────────────────────────────


def test_append_skip_log_creates_audits_dir(tmp_memex_home):
    """_append_skip_log() creates the audits/ directory if it doesn't exist
    and appends the entry to embedding-skip-log.md."""
    from scripts.db import memex_home

    audits_dir = memex_home() / "audits"
    log_path = audits_dir / "embedding-skip-log.md"
    assert not audits_dir.exists()

    embeddings._append_skip_log("\n- test entry\n")

    assert audits_dir.is_dir()
    assert log_path.is_file()
    assert log_path.read_text(encoding="utf-8") == "\n- test entry\n"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_embeddings.py -k "append_skip_log_creates" -v`
Expected: FAIL with `AttributeError: module 'scripts.embeddings' has no attribute '_append_skip_log'`.

- [ ] **Step 4: Add the helper to `scripts/embeddings.py`**

Insert immediately after the `EmbeddingUnavailable` class definition:

```python
# ── Skip log ──────────────────────────────────────────────────────────────


def _append_skip_log(entry: str) -> None:
    """Append a single audit row to ~/.memex/audits/embedding-skip-log.md.
    Mirrors data_steward._append_audit's shape; private file-write
    primitive. I/O exceptions propagate by design."""
    from scripts.db import memex_home

    audits_dir = memex_home() / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)
    log_path = audits_dir / "embedding-skip-log.md"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_embeddings.py -k "append_skip_log_creates" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/embeddings.py tests/test_embeddings.py
git commit -m "embeddings: add _append_skip_log file-write primitive"
```

---

### Task 7: `log_skip()` helper + 5 remaining Group C tests

**Files:**
- Modify: `scripts/embeddings.py`
- Modify: `tests/test_embeddings.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_embeddings.py`:

```python
def test_log_skip_writes_required_fields(tmp_memex_home):
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


def test_log_skip_omits_empty_optional_fields(tmp_memex_home):
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


def test_log_skip_includes_optional_fields_when_provided(tmp_memex_home):
    exc = embeddings.EmbeddingUnavailable(
        reason="oversize_input", provider="voyage", detail="token cap exceeded"
    )
    embeddings.log_skip(
        exc, caller_agent_id="librarian-1", index_id="abc-123", input_chars=42189
    )

    from scripts.db import memex_home

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert "caller=librarian-1" in log
    assert "index_id=abc-123" in log
    assert "input_chars=42189" in log


def test_log_skip_truncates_long_detail(tmp_memex_home):
    """detail is truncated to 200 chars in the audit row."""
    long_detail = "x" * 500
    exc = embeddings.EmbeddingUnavailable(
        reason="provider_error", provider="openai", detail=long_detail
    )
    embeddings.log_skip(exc)

    from scripts.db import memex_home

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    # The truncated detail is exactly 200 'x's; not 500.
    assert "x" * 200 in log
    assert "x" * 201 not in log


def test_log_skip_escapes_pipe_in_detail(tmp_memex_home):
    """Literal | in detail is replaced with / to keep rows parseable."""
    exc = embeddings.EmbeddingUnavailable(
        reason="provider_error", provider="openai", detail="error | with | pipes"
    )
    embeddings.log_skip(exc)

    from scripts.db import memex_home

    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert "error / with / pipes" in log
    # The row format itself uses pipes as separators, so the raw '|' chars in
    # detail must not appear in the substring we wrote.
    assert "error | with" not in log


def test_log_skip_collapses_newlines_in_detail(tmp_memex_home):
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
    detail_line = [
        line for line in log.splitlines() if "detail=" in line
    ][0]
    assert "\n" not in detail_line and "\r" not in detail_line
    assert "line one line two line three line four" in detail_line
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embeddings.py -k "log_skip" -v`
Expected: 6 FAILs with `AttributeError: module 'scripts.embeddings' has no attribute 'log_skip'`.

- [ ] **Step 3: Add the public helper to `scripts/embeddings.py`**

Insert immediately after `_append_skip_log`:

```python
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
    original embedding skip."""
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
            exc.detail.replace("\r\n", " ")
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("|", "/")
        )[:200]
        fields.append(f"detail={sanitized}")
    entry = "\n- " + " | ".join(fields) + "\n"
    _append_skip_log(entry)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -k "log_skip" -v`
Expected: 6 PASS.

Run: `pytest tests/test_embeddings.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/embeddings.py tests/test_embeddings.py
git commit -m "embeddings: add log_skip() helper writing structured audit rows"
```

---

## Phase 4 — Caller-loop tightening

### Task 8: Tighten `backfill_null` + Group D test

**Files:**
- Modify: `scripts/embeddings.py` (`backfill_null` function, the try/except around line 287-291)
- Modify: `tests/test_embeddings.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_embeddings.py`:

```python
# ── Caller-loop behavior (Group D) ─────────────────────────────────────────


def test_backfill_null_logs_skip_and_continues(tmp_memex_home, monkeypatch):
    """backfill_null catches EmbeddingUnavailable narrowly, logs each skip,
    and continues processing remaining rows."""
    from scripts.db import get_connection, memex_home

    # Set up a minimal index.db with three NULL-embedding rows
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

    # Patch encode so rows id-1 and id-3 succeed; id-2 raises
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

    # Skip log should contain one row for the failed encode
    log = (memex_home() / "audits" / "embedding-skip-log.md").read_text(encoding="utf-8")
    assert log.count("reason=provider_error") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_embeddings.py -k "backfill_null_logs_skip" -v`
Expected: FAIL — current `backfill_null` catches broad `Exception` and never writes to the skip log.

- [ ] **Step 3: Tighten `backfill_null` in `scripts/embeddings.py`**

Find the existing block (around line 286-291):

```python
        for i, row in enumerate(null_rows):
            try:
                blob = encode(row["searchable"] or "")
            except Exception:
                summary["errors"] += 1
                continue
```

Replace with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -k "backfill" -v`
Expected: PASS (plus any pre-existing backfill tests still PASS).

- [ ] **Step 5: Commit**

```bash
git add scripts/embeddings.py tests/test_embeddings.py
git commit -m "embeddings: backfill_null narrows catch + emits log_skip per row"
```

---

### Task 9: Tighten `reembed_all` + Group D test

**Files:**
- Modify: `scripts/embeddings.py` (`reembed_all` function, the try/except around line 351-354)
- Modify: `tests/test_embeddings.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_embeddings.py`:

```python
def test_reembed_all_logs_skip_and_continues(tmp_memex_home, monkeypatch):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_embeddings.py -k "reembed_all_logs_skip" -v`
Expected: FAIL.

- [ ] **Step 3: Tighten `reembed_all` in `scripts/embeddings.py`**

Find the existing block (around line 350-354):

```python
        for i, row in enumerate(all_rows):
            try:
                blob = encode(row["searchable"] or "")
            except Exception:
                summary["errors"] += 1
                continue
```

Replace with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/embeddings.py tests/test_embeddings.py
git commit -m "embeddings: reembed_all narrows catch + emits log_skip per row"
```

---

## Phase 5 — Skill markdown updates (6 sites)

### Task 10: Tighten `internal/index/write/SKILL.md` Step 4

**Files:**
- Modify: `internal/index/write/SKILL.md` (Step 4 code block)

- [ ] **Step 1: Read current Step 4**

Read the section around the current Step 4 code block. The block currently reads:

```python
from scripts import embeddings
try:
    embedding = embeddings.encode(librarian_output["searchable"])
except Exception as e:
    print(f"warn: embedding skipped ({e})")
    embedding = None
```

- [ ] **Step 2: Replace Step 4**

Replace the entire Step 4 code block with:

````markdown
### Step 4 — Encode embedding (optional)

```python
from scripts import embeddings
try:
    embedding = embeddings.encode(librarian_output["searchable"])
except embeddings.EmbeddingUnavailable as e:
    embeddings.log_skip(
        e,
        caller_agent_id=caller_agent_id,
        index_id=librarian_output["index_id"],
        input_chars=len(librarian_output["searchable"]),
    )
    embedding = None
```

Catches only `EmbeddingUnavailable` (degraded-mode signal) — any other
exception propagates so real bugs surface. `log_skip` writes a structured
row to `~/.memex/audits/embedding-skip-log.md`; the FTS5 path is
unaffected by the missing vector.
````

- [ ] **Step 3: Verify the change reads correctly**

Re-read the section: confirm `except embeddings.EmbeddingUnavailable as e:` replaced `except Exception as e:` and that `log_skip(...)` call uses the four kwargs shown above.

- [ ] **Step 4: Commit**

```bash
git add internal/index/write/SKILL.md
git commit -m "index:write: narrow embedding catch to EmbeddingUnavailable + log_skip"
```

---

### Task 11: Tighten `internal/index/search/SKILL.md` Step 4 fallback

**Files:**
- Modify: `internal/index/search/SKILL.md` (around line 50-52)

- [ ] **Step 1: Locate the current fallback**

Current code:

```python
try:
    results = reference_librarian.ask_execute(prep, query_plan, with_embedding=True)
except Exception:
    results = reference_librarian.ask_execute(prep, query_plan, with_embedding=False)
```

- [ ] **Step 2: Replace with typed catch + log_skip**

```python
try:
    results = reference_librarian.ask_execute(prep, query_plan, with_embedding=True)
except embeddings.EmbeddingUnavailable as e:
    embeddings.log_skip(
        e,
        caller_agent_id=caller_agent_id,
        input_chars=len(plan["vector_query"] or ""),
    )
    results = reference_librarian.ask_execute(prep, query_plan, with_embedding=False)
```

Also ensure `from scripts import embeddings` is added near the top of the recipe alongside the existing `from scripts.agents import reference_librarian`.

Note in the markdown: this narrows the fallback so it only triggers on
genuine embedding unavailability. Other exceptions (DB error, JSON parse
fail in `ask_execute`) propagate as real bugs rather than silently
becoming an FTS5-only search.

- [ ] **Step 3: Commit**

```bash
git add internal/index/search/SKILL.md
git commit -m "index:search: narrow fallback to EmbeddingUnavailable + log_skip"
```

---

### Task 12: Tighten `internal/brain/ingest/SKILL.md`

**Files:**
- Modify: `internal/brain/ingest/SKILL.md` (around line 76-77)

- [ ] **Step 1: Locate the current catch**

Current code:

```python
try:
    embedding = embeddings.encode(librarian_output["searchable"])
except Exception as e:
    ...
```

- [ ] **Step 2: Replace**

```python
try:
    embedding = embeddings.encode(librarian_output["searchable"])
except embeddings.EmbeddingUnavailable as e:
    embeddings.log_skip(
        e,
        caller_agent_id="brain-ingest",
        index_id=librarian_output["index_id"],
        input_chars=len(librarian_output["searchable"]),
    )
    embedding = None
```

- [ ] **Step 3: Commit**

```bash
git add internal/brain/ingest/SKILL.md
git commit -m "brain:ingest: narrow embedding catch to EmbeddingUnavailable + log_skip"
```

---

### Task 13: Tighten `internal/brain/capture/SKILL.md`

**Files:**
- Modify: `internal/brain/capture/SKILL.md` (around line 57-58)

- [ ] **Step 1: Locate the current catch**

Same shape as ingest.

- [ ] **Step 2: Replace**

```python
try:
    embedding = embeddings.encode(librarian_output["searchable"])
except embeddings.EmbeddingUnavailable as e:
    embeddings.log_skip(
        e,
        caller_agent_id="brain-capture",
        index_id=librarian_output["index_id"],
        input_chars=len(librarian_output["searchable"]),
    )
    embedding = None
```

- [ ] **Step 3: Commit**

```bash
git add internal/brain/capture/SKILL.md
git commit -m "brain:capture: narrow embedding catch to EmbeddingUnavailable + log_skip"
```

---

### Task 14: Tighten `internal/brain/synthesize/SKILL.md`

**Files:**
- Modify: `internal/brain/synthesize/SKILL.md` (around line 95-96)

- [ ] **Step 1: Read the current context**

Confirm the call site is the same shape (`embedding = embeddings.encode(...)` followed by `except Exception:`). The synthesizer may also have a `caller_agent_id` variable already in scope; if so, use it. Otherwise use the literal `"synthesizer-1"`.

- [ ] **Step 2: Replace**

```python
try:
    embedding = embeddings.encode(librarian_output["searchable"])
except embeddings.EmbeddingUnavailable as e:
    embeddings.log_skip(
        e,
        caller_agent_id="synthesizer-1",
        index_id=librarian_output["index_id"],
        input_chars=len(librarian_output["searchable"]),
    )
    embedding = None
```

- [ ] **Step 3: Commit**

```bash
git add internal/brain/synthesize/SKILL.md
git commit -m "brain:synthesize: narrow embedding catch to EmbeddingUnavailable + log_skip"
```

---

### Task 15: Tighten `internal/brain/ask/SKILL.md` instruction

**Files:**
- Modify: `internal/brain/ask/SKILL.md` (around line 68 — prose, not a try/except block)

- [ ] **Step 1: Read the current prose**

Current line ~68: "Wrap in try/except if `query_plan["vector_query"]` is set — `embeddings.encode()` for the query vector will raise if no API key:"

The skill instructs the agent on the catch pattern; updating the prose ensures the agent writes the typed catch.

- [ ] **Step 2: Update the instruction**

Replace the surrounding prose + any example code block so it reads:

````markdown
Wrap the query encode in `try / except embeddings.EmbeddingUnavailable`
— the query vector will raise if the provider is unavailable. Emit
`embeddings.log_skip(e, caller_agent_id="reference-librarian-1",
input_chars=len(query_plan["vector_query"]))` and fall back to
FTS5-only retrieval:

```python
from scripts import embeddings
try:
    qvec_blob = embeddings.encode(query_plan["vector_query"])
except embeddings.EmbeddingUnavailable as e:
    embeddings.log_skip(
        e,
        caller_agent_id="reference-librarian-1",
        input_chars=len(query_plan["vector_query"]),
    )
    qvec_blob = None
```

Catching only `EmbeddingUnavailable` lets unrelated failures (parse
errors, missing fields) propagate as real bugs.
````

- [ ] **Step 3: Commit**

```bash
git add internal/brain/ask/SKILL.md
git commit -m "brain:ask: narrow embedding catch instruction to EmbeddingUnavailable + log_skip"
```

---

## Phase 6 — Documentation

### Task 16: Add §6.5 + DL-#26 to the v2 spec

**Files:**
- Modify: `docs/specs/2026-05-16-memex-v2-redesign-design.md`

- [ ] **Step 1: Locate the insertion point**

Find §6.4 (the documents.key UNIQUE invariant section) and add §6.5 immediately after it. Locate the Decision Log section and find the last entry (`DL-#25`).

- [ ] **Step 2: Add §6.5**

Insert (after §6.4, before §6.6 if any, otherwise at the end of §6):

````markdown
### §6.5 Embedding failures are typed and audited (v2.4.1)

`embeddings.encode()` raises `EmbeddingUnavailable` on any failure to
produce an embedding. The exception carries three fields — `reason`,
`provider`, `detail` — chained via `from` to the original exception.

The `reason` taxonomy is a **frozen contract** (four values):

| `reason` | When raised |
|---|---|
| `not_configured` | API key missing OR provider SDK not installed |
| `oversize_input` | Provider rejected the text for exceeding its token cap |
| `provider_error` | Anything else from the provider (network, rate limit, 5xx) |
| `unknown` | Defensive catch-all in central `encode()` |

Consumers (Atelier, custom plugins) **MUST** catch
`EmbeddingUnavailable` specifically — not broad `Exception` — so real
bugs surface. Consumers **SHOULD** call
`embeddings.log_skip(exc, caller_agent_id=..., index_id=...,
input_chars=...)` for symmetric audit-log emission.

Skip events are recorded in `~/.memex/audits/embedding-skip-log.md`
(distinct from `reconciliation-log.md` which remains scoped to Data
Steward integrity actions). Row format: single-line markdown bullet,
ISO-8601 UTC timestamp, pipe-separated `key=value` fields, mirroring
`data_steward._append_audit`. Omitted optional fields are absent from
the row entirely; `\r`/`\n` in `detail` collapse to space; literal `|`
in `detail` becomes `/`; `detail` truncated to 200 chars.

**Forward-compat with v2.5 `encode_chunks`:** when v2.5 ships
multi-vector, `encode_chunks()` follows the same raise-on-system-fault
contract — system faults raise `EmbeddingUnavailable`; the empty-list
return is reserved for the natural "no chunks producible" case (binary
input, post-strip-empty). Single catch shape across both APIs.

See `docs/specs/2026-05-17-embedding-unavailable-design.md` for the full
design + decision log.
````

- [ ] **Step 3: Add DL-#26 to the Decision Log**

Append to the Decision Log section:

```markdown
- **DL-#26** (v2.4.1): typed embedding failures + audit log. Supersedes
  broad-Exception swallow pattern. See §6.5 and
  `docs/specs/2026-05-17-embedding-unavailable-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add docs/specs/2026-05-16-memex-v2-redesign-design.md
git commit -m "spec: add §6.5 embedding failures typed + audited (DL-#26)"
```

---

### Task 17: USER_GUIDE.md audit-logs subsection

**Files:**
- Modify: `USER_GUIDE.md`

- [ ] **Step 1: Find a sensible insertion point**

Pick the section that covers operational concerns or troubleshooting. If a "Troubleshooting" or "Operations" section exists, append under it. If not, add a new top-level "Audit logs" section before "Releases" / appendix.

- [ ] **Step 2: Write the subsection**

```markdown
## Audit logs

Memex writes two audit-log files under `~/.memex/audits/`:

### `reconciliation-log.md`

Rare, operator-triggered events from `memex:steward:reconcile-orphan`
(delete-index / repair / note). Each row is one action taken to resolve
a flagged orphan. Grows slowly.

### `embedding-skip-log.md`

Per-failed-encode events. Each row records that an embedding could not
be produced for some text. The document is still indexed via FTS5 — only
the vector slot is empty. Grows quickly during bulk ingest if your
embedding provider is misconfigured.

Row fields: `timestamp`, `provider`, `reason`
(`not_configured` | `oversize_input` | `provider_error` | `unknown`),
optionally `caller`, `index_id`, `input_chars`, `detail` (truncated to
200 chars).

**To watch live:** `tail -f ~/.memex/audits/embedding-skip-log.md`

**Common causes by reason:**
- `not_configured` → set your provider's env var (`OPENAI_API_KEY` /
  `VOYAGE_API_KEY`) or `pip install` the SDK; then run
  `memex:embed:backfill` to fill in the missing vectors.
- `oversize_input` → expected during heavy ingest of long documents
  until v2.5's multi-vector chunker ships. Documents are still indexed
  via FTS5.
- `provider_error` → transient network or rate-limit issue; retry the
  ingest or backfill later.
- `unknown` → unexpected leak; the row's `detail` field (and the
  exception's `__cause__`) carry the original error.

**Log rotation:** v2.4.x has no automatic rotation. Rename the file
periodically if it grows large:
`mv embedding-skip-log.md embedding-skip-log-$(date +%Y-%m).md`.
```

- [ ] **Step 3: Commit**

```bash
git add USER_GUIDE.md
git commit -m "docs: add audit-logs section covering reconciliation + embedding-skip"
```

---

### Task 18: CHANGELOG.md v2.4.1 entry

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Open CHANGELOG.md and find the top entry**

The current top entry should be `## v2.4.0 — 2026-05-17` (or similar). Insert the new entry above it.

- [ ] **Step 2: Add the v2.4.1 entry**

```markdown
## v2.4.1 — <RELEASE-DATE>

### Changed
- Embedding failures now raise a typed `embeddings.EmbeddingUnavailable`
  exception with `reason` / `provider` / `detail` fields, replacing the
  silent broad-`Exception` swallow across every `encode()` call site
  (audit: 6 skill markdown + 2 Python). New helper `embeddings.log_skip()`
  writes structured entries to `~/.memex/audits/embedding-skip-log.md`
  for operator visibility. Reason taxonomy (frozen contract):
  `not_configured` | `oversize_input` | `provider_error` | `unknown`.
- Consumers (Atelier) should narrow their existing `except Exception`
  catches to `except embeddings.EmbeddingUnavailable`. Behavior is
  backwards-compatible — `EmbeddingUnavailable` extends `Exception`.

### Migration
- No action required for upgrade. Existing broad-`Exception` callers
  continue to work. Operators may want to `tail -f
  ~/.memex/audits/embedding-skip-log.md` to surface previously-silent
  embedding failures.

### Spec
- New §6.5 "Embedding failures are typed and audited" in the v2 redesign
  spec; full design at `docs/specs/2026-05-17-embedding-unavailable-design.md`;
  DL-#26 in the Decision Log.
```

`<RELEASE-DATE>` is filled in at tag time by the bump script or
manually.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "changelog: v2.4.1 entry — typed embedding failures + audit log"
```

---

## Phase 7 — Pre-release verification

### Task 19: Local CI mirror

**Files:** none modified.

- [ ] **Step 1: Run the full pre-PR CI mirror**

From the worktree root, run every check the GitHub Actions CI workflow runs (per the `pre_pr_ci_mirror` user-feedback rule):

```bash
ruff check .
ruff format --check .
bandit -r scripts/ -ll
pytest tests/ -v
```

Expected: all PASS. If `ruff format --check` reports diffs, run `ruff format .` and re-stage / re-commit those files before proceeding.

- [ ] **Step 2: Manual smoke test — confirm the audit log writes a real row**

Force a `not_configured` skip end-to-end:

```bash
$env:MEMEX_EMBEDDING_PROVIDER = "openai"
$env:OPENAI_API_KEY = ""  # explicitly empty
python -c "from scripts import embeddings; embeddings.log_skip(embeddings.EmbeddingUnavailable(reason='not_configured', provider='openai', detail='smoke test'))"
type "$env:USERPROFILE\.memex\audits\embedding-skip-log.md"
```

Expected: one bullet row containing `provider=openai | reason=not_configured | detail=smoke test`.

(POSIX equivalent: `MEMEX_EMBEDDING_PROVIDER=openai OPENAI_API_KEY= python -c "..."; cat ~/.memex/audits/embedding-skip-log.md`.)

- [ ] **Step 3: If smoke test polluted the real audit log, restore**

Optional cleanup if you don't want the smoke row to persist:

```bash
# Remove the last line if it matches the smoke detail
# (manual edit — verify before saving)
```

- [ ] **Step 4: No commit — this task is verification only.**

---

### Task 20: Open PR with all changes

**Files:** none modified; uses git + gh.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin claude/epic-mccarthy-96373f
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "embeddings: typed EmbeddingUnavailable + skip audit log (v2.4.1 prep)" --body "$(cat <<'EOF'
## Summary
- New `EmbeddingUnavailable` typed exception replaces the silent broad-`Exception` swallow at every `encode()` call site
- Per-provider classification keeps the lazy-import contract intact; central `encode()` is a thin pass-through with defensive `unknown` wrap
- New `~/.memex/audits/embedding-skip-log.md` collects structured skip rows via `log_skip()` helper mirroring `data_steward._append_audit`
- All 8 audited call sites tightened (6 skill markdown + 2 Python); backwards-compatible (`EmbeddingUnavailable extends Exception`)
- Spec: [docs/specs/2026-05-17-embedding-unavailable-design.md](docs/specs/2026-05-17-embedding-unavailable-design.md); v2 spec gains §6.5 + DL-#26

## Test plan
- [x] Local CI mirror: `ruff check . && ruff format --check . && bandit -r scripts/ -ll && pytest tests/ -v`
- [x] Smoke test: `log_skip` writes to `~/.memex/audits/embedding-skip-log.md`
- [ ] Reviewer verifies the four reason values are reachable in the per-provider classify tests
- [ ] Reviewer confirms `EmbeddingUnavailable` extends `Exception` so legacy broad catches still work

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: After PR merges, run the release script**

(Separate session, after merge to main — not part of this plan's automation.)

```bash
python -m scripts.release 2.4.1
git push --tags
```

The tagged push triggers `release.yml` → GitHub Release published →
`repository_dispatch` → agora's `plugin-update.yml` opens an
auto-update PR.

- [ ] **Step 4: Send the coordination message to Atelier**

After v2.4.1 is tagged:

> Memex v2.4.1 shipped. Class to narrow your catch to:
> `scripts.embeddings.EmbeddingUnavailable`. Reason values you may want
> to branch on: `not_configured` / `oversize_input` / `provider_error`
> / `unknown`. Optional: call `embeddings.log_skip(exc,
> caller_agent_id="atelier-1", index_id=..., input_chars=...)` if
> you want your skips landing in Memex's audit log alongside ours.

---

## Self-review

**Spec coverage:**

| Spec section | Task(s) |
|---|---|
| Architectural choice (raise-only) | Task 1 (class), Task 5 (encode wrap) |
| Exception class shape | Task 1 |
| Reason taxonomy (frozen contract) | Tasks 2–4 (per-provider raise correct reason), Task 5 (unknown), Task 16 (spec) |
| Per-provider classification | Tasks 2 (OpenAI), 3 (Voyage), 4 (local) |
| Audit log file + helpers | Tasks 6 (_append_skip_log), 7 (log_skip) |
| Log growth + rotation note | Task 17 (USER_GUIDE.md) |
| Concurrency disclosure | Task 16 (§6.5 prose — covered by reference to design spec) |
| Call-site updates: 6 skill markdown | Tasks 10–15 |
| Call-site updates: 2 Python | Tasks 8–9 |
| Backwards compat note | Task 18 (CHANGELOG) |
| Testing Group A (4) | Task 1 |
| Testing Group B (9 + 1 leak + 1 passthrough) | Tasks 2–5 |
| Testing Group C (6) | Tasks 6–7 |
| Testing Group D (2) | Tasks 8–9 |
| Spec revision §6.5 + DL-#26 | Task 16 |
| USER_GUIDE.md audit-logs section | Task 17 |
| CHANGELOG.md v2.4.1 entry | Task 18 |
| v2.4.1 patch release | Task 20 |

No gaps.

**Placeholder scan:** None — every code step shows the actual code; every command is concrete. `<RELEASE-DATE>` in the CHANGELOG is the only placeholder, and it's the intentional contract (filled at tag time).

**Type consistency:** `EmbeddingUnavailable(reason, provider, detail)` signature is consistent across all tasks. `log_skip(exc, *, caller_agent_id, index_id, input_chars)` kwargs are consistent across tasks 7, 8, 9, 10–15. Reason values (`not_configured` / `oversize_input` / `provider_error` / `unknown`) match the spec's frozen contract everywhere.
