# ADR-002: Cache identity and code provenance in the pure core

- **Status:** Accepted — amended in `0.4.0` (decision 1 and the consequences it carries)
- **Date:** 2026-07-30
- **Component:** `ruthless/_fingerprint.py`, `ruthless/_provenance.py`, `ruthless/_version.py`
  (call sites: `ruthless/__init__.py` (public re-export, 0.4.0),
  `ruthless/strategies/evolve_/strategy.py`, all three strategies' `Result.provenance`)

## Context

Two surfaces in this repo answered "is this artifact still valid?" and "what produced this artifact?"
inconsistently with the repo's own principles.

**Cache identity.** `EvolveStrategy` decided whether a persisted seed result could be reused via a
private, hand-rolled digest:

```python
return hashlib.sha256(f"{cfg.evaluation.epochs}:{cfg.evaluation.seed}".encode()).hexdigest()[:16]
```

Untagged string concatenation over a `:` separator, collision-free only because both fields happen to be
pydantic-validated `int`s. Its invalidation scope — *"epochs/seed; no dataset"* — lived in a docstring
parenthetical. Nothing enforced it, and nothing prompted a re-read when `EvalConfig` grew a field. That
failure is quiet in the worst way: a new field that *does* affect results leaves the fingerprint
unchanged, and stale results are reused as valid. Every other correctness guard in this repo fails
loudly (`classify_metric` raises; backends raise); a hash-collision cache hit fails silently and wrongly.

**Code provenance.** `Result.provenance` existed and was rendered in both output formats, but carried no
record of the code that produced the run. The obvious fix carries a trap that has already caused a real
false-provenance incident in a consumer repo: `git rev-parse HEAD` returns the same SHA whether or not
the working tree is modified, so a bare SHA on an artifact built from a dirty tree is
*verifiable-looking false provenance* — strictly worse than recording nothing.

## Decision

**1. One hashing implementation in the core — private first, public since 0.4.0.**
`ruthless/_fingerprint.py` is type-tagged in both the **key** and the value position, structural rather
than concatenated, order-insensitive, and fail-closed on unknown types (raising rather than falling
back to `str()`, which is exactly how two distinct objects acquire one digest).

*As originally decided (0.3.x):* it was `_`-prefixed and absent from `__all__`, following `_logging.py`
/ `_io.py` — shared across core and strategies with no `1.0` API commitment, pending a second real
caller.

*Superseded in 0.4.0:* that trigger fired, so `fingerprint` and `fingerprint_model` are now re-exported
from `ruthless` and listed in `__all__`. The **module** stays `_`-prefixed, because a public
`ruthless/fingerprint.py` would shadow the re-exported function name (`import ruthless.fingerprint`
rebinds the package attribute from the function to the module).

**Digest stability is now a compatibility contract.** The digest is a persisted cache key in consumer
storage, so any change altering an existing payload's digest is breaking, not additive — regardless of
motive, including a correctness fix. It takes the minor slot under `0.x` and its CHANGELOG entry must
say it invalidates existing caches. There is no carve-out: a carve-out is the loophole every future
digest change would be argued into, and it buys the consumer nothing, since an orphaned cache is
equally silent whether the digest moved for a good reason or a careless one. The enforcement is
`tests/test_fingerprint_golden.py`, and the point of pinning bytes rather than relations is to
manufacture a reviewable moment: changing a digest means editing that table.

The guarantee is over the logical value. `Path(str)` parses per-platform, so construction is the
caller's responsibility; digesting identically everywhere is ours. `pydantic` is pinned `<3` because
`fingerprint_model` digests `model_dump()` output, which places pydantic's serialisation inside the
digest's blast radius — the same reasoning that already pins `numpy<3` for the determinism gate.

This is not speculative extraction. The exclusion contract below has to live somewhere, and it cannot
live in a strategy internal without a second strategy having to import across a boundary
`.importlinter` forbids — so the primitive has a concrete second responsibility on the day it lands.

**2. Invalidation scope is a declared EXCLUSION set, never an inclusion list.**
`fingerprint_model(model, exclude=...)` covers every model field except the named exclusions. A field
added later is therefore included automatically, so the failure mode of forgetting to revisit an
exclusion is an unnecessary cache **miss** (recompute — safe) rather than a stale **hit** (wrong).
Naming a field the model does not have raises, closing the renamed-field gap. Each exclusion carries a
comment stating its reason **and naming the test that makes it safe** — see `_SEED_CACHE_EXCLUDE`, whose
`timeout_seconds` entry is load-bearing only because `_load_cached_seeds` filters on
`combined_score > 0.0`, now pinned by `test_a_zero_score_seed_result_is_never_cache_readable`.

**3. Provenance never overclaims.** `code_identity()` never reports a commit without a tree state, and
an absent or failing `git` reports `"unknown"` rather than degrading to `"clean"`. Dirtiness uses
`git status --porcelain`, not `git diff --quiet`, so untracked files count. Keys are `ruthless_`-prefixed
because they identify *ruthless's* tree, not the consumer's objective code. Capture happens at **run**
time, not render time, since `render_json` may be called later from a different tree.

**4. Provenance proves the repo owns the module.** Auto-discovery requires
`git ls-files --error-unmatch` to confirm the enclosing repo *tracks* this module as source. Without
this, a wheel installed into a project-local venv — `<consumer-repo>/.venv/Lib/site-packages/ruthless/`,
the default layout for uv, Poetry and `python -m venv` — sits inside the consumer's repo, so
`git rev-parse HEAD` succeeds there and returns **their** commit. Measured; gitignoring the venv does not
help, because git walks up for `.git` and never consults ignore rules.

**5. `__version__` moved to `ruthless/_version.py`**, re-exported from the package root.
`ruthless/__init__.py` is the curated public API and imports a strategy, so any core module reading the
version from it transitively imports `ruthless.strategies` and breaks the `core-isolation` contract.

**6. The version is single-sourced from that module.** `pyproject.toml` declares `dynamic = ["version"]`
with `[tool.hatch.version] path = "ruthless/_version.py"`. It previously carried its own literal, so the
packaging version and `__version__` were two independent values with nothing enforcing agreement — and
decision 3 above makes that drift consequential rather than cosmetic, because `ruthless_version` is now
stamped into every result artifact. Deleting the duplication is preferred over a test that detects it:
a test can only fail after someone has already shipped the inconsistency to a reader.

## Consequences

- **Every exclusion must name the test that justifies it.** §3's design protects against a new *field*;
  nothing protects against the *reasoning behind an existing exclusion* going stale. The cross-reference
  is the compensating control, and it is a review obligation, not an automated one.
- **`fingerprint_model` checks that exclusions EXIST, not that they are CORRECT.** An author can exclude
  a field that does matter and get a fingerprint that never changes. This converts a silent omission into
  a visible, reviewable, wrong line — it does not prove the scope. Stated in the docstring so the next
  author writing an exclusion meets it.
- **Three deliberate false-negatives**, all erring toward an unnecessary miss rather than a stale hit:
  `-0.0` and `0.0` digest differently despite comparing equal; two mappings that compare equal can digest
  differently (`{True: "x"} == {1: "x"}` in Python, but the keys tag differently); and extending `_tag` to
  a new type (`Path`, `datetime`, `Enum`) is an explicit change with a test rather than an accident.
- **The evolve seed cache invalidated once.** Same input set, new digest value, so existing on-disk caches
  miss and recompute. Benign, and in the fail-closed direction.
- **(0.4.0) A second review obligation, of exactly the same kind as the first.** The golden table proves
  every *payload* is pinned; nothing proves every `_tag` *branch* has a payload. A new branch can land
  with no case and the table stays green while the new type goes unguarded indefinitely. Extending `_tag`
  must add a golden case in the same commit, and a reviewer must check that it did.
- **(0.4.0) The pin propagates to consumers.** `pydantic<3` is no longer only ruthless's business: it
  constrains the resolution of every project that installs ruthless. Accepted deliberately — an
  unannounced pydantic major moving `model_dump()` output would move consumer cache keys with nothing in
  ruthless changing, which is precisely the failure the contract exists to make impossible. Lifting the
  pin means first proving the digest is unmoved, on the same evidence standard as a `_tag` change.
- **(0.4.0) The contract had already been broken once, unknowingly — which is why it is now written.**
  Executing the golden table against the published wheels established that `0.3.1` was *not* purely
  additive as its entry claimed. `0.3.0` had no `enum` branch, so `IntEnum` and `str`-subclassing `Enum`
  members fell through to the `int`/`str` branches: they did not raise, they digested successfully, and
  identically to the bare value they wrap. `0.3.1`'s new `enum` branch moved both. Two payload shapes
  were therefore cache-invalidating in a release published as a patch. The `0.3.1` entry carries a
  correction; the episode is the evidence for the no-carve-out rule, since the original claim was made in
  good faith and was still wrong.
- **(0.4.0) Release procedure gained a hard rule**, on top of the version bump below: a change that moves
  any already-supported payload's digest takes the **minor** slot and its CHANGELOG entry must state that
  it invalidates existing caches. Editing `tests/test_fingerprint_golden.py` is the friction that forces
  the question to be asked out loud.
- **(0.4.0) Prose may not quote a digest**, enforced by `tests/test_docs_no_digest_literals.py` rather
  than by convention. A digest in a document drifts silently — nothing re-runs a spec — and invites a
  later reader to lift it back into the golden table on the assumption it had already been checked, which
  would pin a documented value instead of the algorithm's output. Defence-in-depth around the table's
  status as single source of truth, with a declared exclusion set for values that are evidence inside a
  completed decision record. It is a strong guard, not a total one: it recognises the default 16-char
  digest, so other lengths and a few unusual spellings fall outside it, and its docstring says so.
- **(0.4.0) Cross-platform CI is now load-bearing, not hygiene.** `core-lean-windows` exists because
  consumers of the digest span Windows and Linux while CI ran only on Linux, so a platform-dependent
  digest could not be observed here at all. The guarantee it protects is over the **logical value**:
  `Path(str)` parses per-platform, so a caller spanning platforms must normalise before fingerprinting —
  constructing the value is the caller's responsibility, digesting it identically everywhere is ours.
- **A wheel install reports `ruthless_git_state: "unknown"`**, with `ruthless_version` carrying the
  identity. This is the correct outcome, not a degradation — but it will surprise someone.
- **The core now shells out to `git`**, opportunistically. It adds no Python dependency and absent git is
  a supported state, but it is the first external-tool call in the pure core.
- **Release procedure changed:** bump `ruthless/_version.py` only — `pyproject.toml` follows via
  hatchling. The remaining hand-edits are the `CLAUDE.md` "Ships at" line and the CHANGELOG section
  header. A broken `[tool.hatch.version] path` fails CI at `uv pip install -e`, which both CI jobs run,
  so it cannot lie dormant until release.
- **Rejected — a path-comparison containment check** (`<toplevel>/ruthless/_provenance.py == __file__`).
  It works for today's layout but encodes an unstated assumption that the package sits at the repo root,
  so a move to a `src/` layout would make a *legitimate* checkout fail and silently degrade provenance to
  `"unknown"` everywhere. Measured across five layouts: `ls-files` is correct on all five, path comparison
  is wrong on `src/`.
- **Rejected — adding cache identity to `CachedObjective`.** That port is within-run invariant reuse with
  nothing persisted, so it has no cache-identity question to answer.
