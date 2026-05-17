# Typed embedding failures + audit log (v2.4.1)

**Status:** Draft (brainstormed 2026-05-17)
**Target release:** Memex v2.4.1 (patch)
**Supersedes:** broad-`Exception` swallow pattern at all `embeddings.encode()` call sites
**Cross-references:** v2 redesign spec §6 (Librarian write path), forthcoming v2.5 multi-vector design

## Motivation

`scripts/embeddings.py::encode()` can fail for several distinct reasons:
missing API key, SDK not installed, oversize input, provider rate limit /
network error. Today every call site catches the broad `Exception`,
silently sets `embedding = None`, and proceeds with FTS5-only indexing.

This was identified as a latent bug during Atelier's 1.D design review:
operators have no visibility into how many of their indexed documents lack
vectors or why, and consumers (Atelier) catching the broad `Exception`
can't differentiate "your env isn't configured" (loud, one-shot) from
"this one document was too long" (per-doc, expected during the v1.1.0
chunker bridge).

This patch ships ahead of v2.5's multi-vector work as an independent
correctness fix. Coordinated with Atelier as part of the 1.D resolution.

## Out of scope

- Chunker / `encode_chunks()` / `document_chunks` schema (v2.5).
- Hierarchical or late-interaction embeddings (v2.5+ at earliest, evidence-gated).
- Skip-rate reporting in Data Steward audit reports (deferred follow-up if operators ask for it).

## Design

### Architectural choice: raise-only, caller catches

`encode()` raises a typed exception; every caller wraps in a narrow
`except` and emits a structured audit row. Rejected alternatives:

- **Centralize the catch in `librarian.write_entry`** — would force Atelier
  to pass a sentinel like `skip_encode=True` to prevent double-encoding
  during their v1.1.0 chunk-and-mean-pool flow, and would have to be
  reshaped again at v2.5 when `chunks=` lands. Two breaking changes
  instead of one.
- **Helper wrapper (`encode_or_skip`) alongside `encode()`** — either
  silently logs (then `embeddings` module needs to know about the audit
  log, same layering objection as above) or returns a tuple (callers
  write essentially the same code). Two redundant APIs for no real
  saving.

### Exception class

In `scripts/embeddings.py`:

```python
class EmbeddingUnavailable(Exception):
    """Raised by encode() when no embedding can be produced. Callers may
    catch and proceed with embedding=None (FTS5-only indexing) or surface
    as fatal — degraded-mode semantics, not an error."""

    def __init__(self, reason: str, provider: str, detail: str = ""):
        self.reason = reason
        self.provider = provider
        self.detail = detail
        super().__init__(
            f"embedding unavailable (provider={provider!r}, reason={reason!r})"
            + (f": {detail}" if detail else "")
        )
```

Always raised via `raise EmbeddingUnavailable(...) from original_exc` so
`__cause__` carries the original traceback.

**Naming:** chose `EmbeddingUnavailable` over `EmbeddingError` because
the existing `*Error` classes (`DuplicateKeyError`, `OrphanNotFoundError`)
are fatal — caller must surface. Embedding skip is degraded-mode — caller
proceeds safely. Sharing the `*Error` suffix would mislead on severity.

### Reason taxonomy (frozen contract)

| `reason` value | When raised | Remediation |
|---|---|---|
| `not_configured` | API key missing OR provider SDK not installed | User sets env var or `pip install <sdk>` |
| `oversize_input` | Provider rejected the text for exceeding its token cap | Caller chunks (v2.5's `encode_chunks` will largely retire this case) |
| `provider_error` | Anything else from the provider (network, rate limit, 5xx, parse fail) | Usually transient — retry or skip |
| `unknown` | Catch-all for defensive `encode()` wrapping | Inspect `__cause__` |

Documented as the contract surface in the class docstring and
USER_GUIDE.md. Consumers (Atelier) may branch on `reason` for
differentiated logging or alerting.

**Forward-compat with v2.5 `encode_chunks`:** when v2.5 ships
multi-vector, `encode_chunks()` will follow the same raise-on-system-fault
contract as `encode()` — system faults (`not_configured`,
`provider_error`, `unknown`) raise `EmbeddingUnavailable`; the empty list
return is reserved for the natural "no chunks producible" case (binary
input, post-strip-empty, etc.). This keeps consumers writing a single
catch shape across both APIs and avoids reshaping wrappers at the v2.5
bump.

### Classification: per-provider catches

Each `_<provider>_encode` function in `scripts/embeddings.py` catches its
own provider-specific exception types and raises `EmbeddingUnavailable`
with the appropriate reason. Central `encode()` is a thin pass-through
with one defensive `except Exception` that re-raises as `unknown`.

This preserves the module's existing lazy-import contract ("Each
provider's SDK is imported lazily — installing the `memex` package itself
does NOT require any of these libraries"): SDK error classes only get
imported in the function that already imports the SDK.

**Per-provider classification logic:**

- **OpenAI:** `ImportError` on `from openai import OpenAI` → `not_configured`;
  client construction failure (missing `OPENAI_API_KEY`) → `not_configured`;
  `openai.BadRequestError` with `"context_length_exceeded"` in message →
  `oversize_input`; any other provider call exception → `provider_error`.
- **Voyage:** `ImportError` on `import voyageai` → `not_configured`;
  missing `VOYAGE_API_KEY` env var → `not_configured`; exception message
  matching `/token.*(exceed|limit)/i` → `oversize_input`; any other →
  `provider_error`.
- **Local (sentence-transformers):** `ImportError` on
  `from sentence_transformers import SentenceTransformer` → `not_configured`;
  exception message matching `max_seq_length|exceeds|too long` →
  `oversize_input`; any other → `provider_error`.

**Note on string-matching:** Voyage and local providers don't expose a
clean exception class for token-cap overflow. String inspection is
fragile but unavoidable at v2.x; v2.5's proactive chunking largely
retires the case, so this fragility has a short shelf life.

### Audit log

**File:** `~/.memex/audits/embedding-skip-log.md` (new — distinct from
`reconciliation-log.md` which remains scoped to Data Steward integrity
actions). Different cadence (bulk during ingest vs. rare operator
actions), different reader intent ("why aren't my embeddings working?"
vs. "what integrity actions did Data Steward take?") — separate file
keeps both clean.

**Helpers in `scripts/embeddings.py`:**

```python
def _append_skip_log(entry: str) -> None:
    """Append a single audit row. Private file-write primitive."""
    from scripts.db import memex_home
    audits_dir = memex_home() / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)
    log_path = audits_dir / "embedding-skip-log.md"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


def log_skip(exc: EmbeddingUnavailable, *, caller_agent_id: str = "",
             index_id: str = "", input_chars: int = 0) -> None:
    """Public helper for callers to emit a structured audit row for an
    EmbeddingUnavailable they caught. Centralizing the row format here
    means every call site emits the same shape; Atelier may call this if
    they want their skips landing in Memex's audit log alongside ours.

    I/O exceptions from the audit-log write (disk full, file locked, etc.)
    propagate by design — matches data_steward._append_audit's behavior.
    Consumers requiring isolation from audit-write failure should wrap
    log_skip() in their own try/except so audit failure cannot mask the
    original embedding skip."""
```

**Row format:** single-line markdown bullet, ISO-8601 UTC timestamp,
pipe-separated `key=value` fields. Mirrors the existing
`data_steward._append_audit` shape so operators familiar with the
reconciliation log can parse skip rows the same way.

**Example row:**

```
- timestamp=2026-05-17T14:23:01.123456+00:00 | provider=openai | reason=oversize_input | caller=librarian-1 | index_id=abc-123 | input_chars=42189 | detail=context_length_exceeded: max 8192, got 12041
```

- Pipe `|` is the field separator; any literal `|` in `detail` is
  converted to `/` so rows stay parseable. Any `\r` or `\n` in `detail`
  (common in stack-trace fragments) is collapsed to a single space so
  single-line markdown bullets stay intact.
- `detail` is truncated to 200 chars; full traceback available via
  `exc.__cause__`.
- `caller_agent_id`, `index_id`, `input_chars` are optional. Omitted
  optional fields are absent from the row entirely — no empty `field=`
  form is ever written, so audit parsers only need one code path.
  Backfill / reembed loops (which lack an agent-registry caller id) omit
  `caller_agent_id`.

**Log growth + rotation:** the skip log accumulates much faster than
`reconciliation-log.md` (per-failed-encode during ingest vs. rare
operator-triggered actions). A user migrating 200 rows with no provider
configured generates 200 rows in one batch; a bulk `reembed` could
generate thousands. v2.4.x has no automatic rotation; the operator
answer is manual rotation by renaming with a date suffix
(`mv embedding-skip-log.md embedding-skip-log-YYYY-MM.md`). Automatic
rotation may land in a later release if operators ask for it.

**Concurrency:** audit-log writes are atomic per-row on POSIX (`O_APPEND`
with sub-`PIPE_BUF` row size); Windows is best-effort. Multi-process
scenarios (e.g., two Claude Code windows running concurrent ingest) may
see rows interleaved but will not lose data. If row interleaving
becomes a real readability problem, the fallback is `fcntl.flock` /
`msvcrt.locking` per write — out of scope for v2.4.1.

### Call-site updates

Every site that today does `try: blob = embeddings.encode(...) except Exception:`
gets tightened to `except embeddings.EmbeddingUnavailable as e:` and emits
`embeddings.log_skip(e, ...)`.

**Skill-markdown sites (5 with behavioral change, 2 no-op):**

- `internal/index/write/SKILL.md` Step 4 — primary documented bug site.
- `internal/brain/ingest/SKILL.md` — `caller_agent_id="brain-ingest"`.
- `internal/brain/capture/SKILL.md` — `caller_agent_id="brain-capture"`.
- `internal/brain/synthesize/SKILL.md` — query-side encode skip.
- `internal/brain/ask/SKILL.md` — typed catch before FTS5-only fallback.
- `internal/embed/backfill/SKILL.md` — no markdown change; change in the
  Python helper.
- `internal/embed/reembed/SKILL.md` — no markdown change; change in the
  Python helper.

**Python-module sites (4):**

- `scripts/embeddings.py::backfill_null` — narrow catch, log_skip per row.
- `scripts/embeddings.py::reembed_all` — narrow catch, log_skip per row.
- `scripts/agents/reference_librarian.py` (query-side encode in
  `ask_execute`) — narrow catch + log_skip; preserve existing
  `with_embedding=False` fallback.
- `scripts/agents/librarian.py` / `scripts/brain.py` — tighten any
  remaining broad catches; add `log_skip`.

**Backwards compat:** Any caller still using `except Exception` continues
to work — `EmbeddingUnavailable` extends `Exception`. No code breaks.

## Testing

Extends `tests/test_embeddings.py`. All new tests are pure-Python with
monkeypatched SDK imports — no real provider calls, no new CI
dependencies.

**Group A — `EmbeddingUnavailable` class (4 tests):**

- Field population (`reason`, `provider`, `detail`).
- Message format with detail.
- Message format without detail.
- `__cause__` preserved on `raise ... from`.

**Group B — Per-provider classification (9 tests):**

For each of openai / voyage / local:

- `ImportError` on lazy import → `reason="not_configured"`.
- Token-cap-shaped error → `reason="oversize_input"`.
- Generic provider exception → `reason="provider_error"`.

Plus:

- Voyage with `VOYAGE_API_KEY` unset → `reason="not_configured"`.
- `encode()` wrapping unknown leaks → `reason="unknown"` with `__cause__` set.

**Group C — Skip-log helper (6 tests):**

- `_append_skip_log` creates the audits dir if missing.
- `log_skip` writes required fields (timestamp, provider, reason).
- Optional fields omitted when empty — field absent from row entirely (no
  empty `field=` form).
- `detail` truncated to 200 chars.
- Literal `|` in `detail` replaced with `/`.
- Literal `\r` and `\n` in `detail` collapsed to space.

**Group D — Caller-loop behavior (2 tests):**

- `backfill_null` logs skip and continues on `EmbeddingUnavailable`.
- `reembed_all` logs skip and continues.

**Explicitly not tested:**

- Real provider API calls.
- End-to-end oversize on local provider (would require loading the
  ~80MB model; mock the SDK call instead).
- Skill-markdown integration tests — Memex currently lacks
  skill-execution test infrastructure, and adding it for one patch is
  out of scope. May happen later as a separate workstream.

## Documentation

**Spec revision (`docs/specs/2026-05-16-memex-v2-redesign-design.md`):**

Add §6.5 "Embedding failures are typed and audited":

- Documents `EmbeddingUnavailable` as the contract surface.
- Documents the four-value reason taxonomy as a frozen contract.
- Documents `~/.memex/audits/embedding-skip-log.md` as a first-class
  audit file.
- Notes that callers MUST catch `EmbeddingUnavailable` specifically and
  SHOULD call `log_skip()` for symmetry.
- Cross-references the v2.5 multi-vector spec as the next step that
  retires `oversize_input` as a normal occurrence.

Add Decision Log entry: "DL-#26: typed embedding failures + audit log
(v2.4.1) — supersedes broad-Exception swallow pattern."

**USER_GUIDE.md:**

New "Audit logs" subsection covering both `reconciliation-log.md` and
`embedding-skip-log.md` with row formats and `tail -f` examples.

**CHANGELOG.md (v2.4.1 entry):**

```
## v2.4.1 — <RELEASE-DATE>

### Changed
- Embedding failures now raise a typed `embeddings.EmbeddingUnavailable`
  exception with `reason` / `provider` / `detail` fields, replacing the
  silent broad-Exception swallow across every `encode()` call site. New helper
  `embeddings.log_skip()` writes structured entries to
  `~/.memex/audits/embedding-skip-log.md` for operator visibility.
  Consumers (Atelier) should narrow their existing `except Exception`
  catches to `except embeddings.EmbeddingUnavailable`. Behavior is
  backwards-compatible — `EmbeddingUnavailable` extends `Exception`.

### Migration
- No action required for upgrade. Existing broad-Exception callers
  continue to work. Operators may want to inspect the new skip log to
  discover previously-silent embedding failures.
```

## Versioning + release sequencing

**v2.4.1 (patch).** Justification:

- Purely additive (new exception class, new helper, new audit file).
- Behavior-preserving on happy path (encode succeeds → identical bytes).
- Behavior-preserving on failure path (still ends with `embedding = None`
  at the call site; difference is that failure becomes visible in the
  audit log instead of silent).
- Consumers using `except Exception` continue to work.

**Release flow:**

1. PR opened against `main` with all changes (exception class +
   per-provider classification + skip-log helper + call-site updates +
   tests + spec revision + CHANGELOG).
2. CI mirrored locally before push (ruff check + ruff format --check +
   bandit + pytest).
3. After merge: `python -m scripts.release 2.4.1` builds `dist/v2.4.1/`.
4. Tag + push triggers `release.yml` → GitHub Release published →
   `repository_dispatch` fires → agora's `plugin-update.yml` opens an
   auto-update PR.

**Coordination message to Atelier** (their ask was "ping us with the
class name when it lands"):

> Memex v2.4.1 shipped. Class to narrow your catch to:
> `scripts.embeddings.EmbeddingUnavailable`. Reason values you may want
> to branch on: `not_configured` / `oversize_input` / `provider_error` /
> `unknown`. Optional: call `embeddings.log_skip(exc,
> caller_agent_id="atelier-1", index_id=..., input_chars=...)` if
> you want your skips landing in Memex's audit log alongside ours.

## Decision log (this design session)

- **Catch location:** raise-only, caller catches. Rejected centralization
  in `write_entry` (would force a sentinel for Atelier's
  chunk-and-mean-pool flow and a second reshape at v2.5).
- **Class name:** `EmbeddingUnavailable`. Rejected `EmbeddingError`
  (would conflate severity with the existing fatal `*Error` classes) and
  `EmbeddingSkipped` (names the caller's downstream decision, not the
  raise condition).
- **Reason taxonomy:** four-value constrained set. Rejected free-form
  string (loses programmatic branching) and six-value split (premature
  precision for what's currently uniform-handling).
- **Classification location:** per-provider catches. Rejected central
  `encode()` (would break the lazy-import contract).
- **Audit log file:** dedicated `embedding-skip-log.md`. Rejected reuse
  of `reconciliation-log.md` (scope drift on Data Steward's log) and
  dedicated-plus-summary-in-reports (premature coupling for unproven
  operator need).
- **Call-site scope:** every `encode()` call site (precise count to be
  enumerated during implementation; current grep shows ~9 confirmed
  with broad-`Exception` catches across skill markdown and Python).
  Rejected partial fix (would leave the same bug elsewhere and defeat
  the consumer-visibility goal).
- **Versioning:** v2.4.1 patch. Justified by purely-additive,
  behavior-preserving nature.
- **Forward-compat with v2.5 `encode_chunks`:** same raise-on-system-fault
  contract; empty list reserved for the natural no-chunks case. Locked
  here so consumers write a single catch shape across both APIs.
- **Audit row escaping:** `|` → `/`, `\r`/`\n` → space. Defensive
  against provider stack-trace fragments breaking single-line markdown
  bullet parsing.
- **Length field name:** `input_chars` (not `searchable_len`). Operators
  reading the audit log shouldn't have to know which Memex-internal
  field the count came from, and the unit (chars, not tokens) needs to
  be unambiguous.
- **Omitted-field semantics:** absent from row entirely, never written
  as empty `field=`. Audit parsers handle one shape, not two.
- **Log rotation policy for v2.4.x:** manual via date-suffix rename.
  Automatic rotation deferred to a later release pending operator
  demand. Naming the deferral explicitly avoids a future "the log is
  50MB" surprise issue.
- **`log_skip()` I/O failure propagation:** raises through by design,
  matching `data_steward._append_audit`. Consumers requiring isolation
  from audit-write failure must wrap defensively. Documented in the
  helper's docstring so the design intent is visible at the API.
- **Concurrency under multi-process:** POSIX atomic per-row,
  Windows best-effort; worst case interleaved rows, no data loss.
  `fcntl.flock` / `msvcrt.locking` is the fallback if interleaving
  becomes a readability problem — deferred.
