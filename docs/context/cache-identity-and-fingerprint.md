# Cache identity, fingerprint & provenance — rationale

> Class-2 context for the cache/fingerprint/provenance and work-unit invariants of
> [AGENTS.md](../../AGENTS.md) and [ADR-002](../adr/ADR-002-cache-identity-and-code-provenance.md).
> AGENTS.md keeps the terse rules; this file holds the *why*, moved verbatim from the pre-restructure
> `CLAUDE.md`. (No digest literal is quoted here — that rule is itself one of the invariants below.)

## Work-unit error model

- **`map_work_units` always attempts EVERY unit.** `workers` is a speed knob and must never change
  *which* units ran — work units are consumer code with consumer side effects. Unit failures aggregate
  into `WorkUnitMapError` (an `OptimizationError` sibling of `Transient`/`Fatal`, deliberately outside
  the evaluation taxonomy so `BackendPool` cannot retry it) carrying every failure **and** the partial
  results; `on_error="collect"` returns them instead. A dead pool propagates `BrokenExecutor`
  unwrapped, because that voids the attempted-every-unit guarantee. Cost: a systematic failure now
  costs a full pass (the serial path no longer short-circuits).

## Cache identity is an exclusion set

- **Cache identity is a declared EXCLUSION set, never an inclusion list.** `ruthless._fingerprint` is
  the one hashing implementation (the *module* stays `_`-prefixed so it cannot shadow the re-exported
  function name; both functions are public — see below): type-tagged in both the **key** and value
  position, structural rather than concatenated, order-insensitive, and fail-closed on unknown types.
  `fingerprint_model(model, exclude=...)` covers every model field except the named exclusions, so a
  field added later is included automatically — the failure mode of forgetting becomes an unnecessary
  cache *miss* (recompute, safe), never a stale *hit* (wrong). Naming a non-existent field raises. Each
  exclusion carries a comment naming the test that makes it safe (see evolve's `_SEED_CACHE_EXCLUDE`).
  **`_tag`'s branch order is load-bearing** wherever one type subclasses another: `Enum` first (an
  `IntEnum`/`StrEnum` member is also an `int`/`str`), `bool` before `int`, `datetime` before `date`. A
  wrong order silently collides the subclass with its base — tests pin all three. Extending `_tag` to a
  new type means adding a tag, checking where it belongs in that order, *and* adding a golden case for
  it: the golden table proves every payload is pinned, but nothing proves every `_tag` branch has a
  payload, so an unpinned new branch stays green and unguarded until someone notices.
  **Digest bytes are a compatibility contract.** `fingerprint`/`fingerprint_model` are public since
  0.4.0 and consumers persist the digest as a cache key, so any change altering an already-supported
  payload's digest is BREAKING (minor slot, CHANGELOG must say it invalidates caches) — including a
  correctness fix. `tests/test_fingerprint_golden.py` pins one payload per `_tag` branch as literals;
  it is the single source of truth for pinned bytes, and **no `.md` file may quote a digest** — a
  digest in prose gets lifted back into the golden table on the assumption it was already checked.
  That rule is enforced, not merely written: `tests/test_docs_no_digest_literals.py` scans every `.md`
  and fails on any 16-hex literal outside its declared exclusion set (one entry — a *rejected*-algorithm
  value in the 2026-07-29 spec, inert because no shipped `_tag` can produce it; a stale entry fails too).
  The guarantee is over the logical VALUE — `Path(str)` parses per-platform, so construction is the
  caller's problem. `pydantic` is pinned `<3` because `fingerprint_model` digests `model_dump()`.

## Provenance never overclaims

- **Provenance never overclaims.** `ruthless._provenance.code_identity()` never reports a commit
  without a tree state, and never degrades to `"clean"` — a bare SHA from a dirty tree is
  verifiable-looking *false* provenance, worse than recording nothing. Keys are `ruthless_`-prefixed
  because they identify ruthless's tree, not the consumer's objective, and the enclosing repo must be
  proved to **track** this module (so a wheel in a consumer's venv reports `"unknown"` rather than the
  consumer's commit). Uses the `git` CLI opportunistically — absent git is a supported state, not an
  error.
