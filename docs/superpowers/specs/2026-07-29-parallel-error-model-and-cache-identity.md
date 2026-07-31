# Spec — work-unit map error model + cache-identity primitive

**Date:** 2026-07-29
**Status:** rev 3 — review rounds 1 and 2 incorporated; **approved to implement**
**Baseline:** `a9566ee`, version `0.2.1`, clean tree
**Origin:** a handoff document from a silly-kicks session
(`ruthless-efficiency-HANDOFF.md`) raising five items. This spec is the response: it accepts two,
accepts a third with inverted polarity, **rejects** one as specified while accepting its sub-claim in
a different form, and **corrects a factual error** in a fifth.

**Reviewer:** please read §0 first — it lists where this spec disagrees with the handoff, and where a
second verification pass changed the severity of what the handoff measured.

---

## 0. Summary of decisions, including the disagreements

| Handoff item | Verdict | Note |
|---|---|---|
| §1 `map_work_units` has no error model | **ACCEPT — severity upgraded** | Confirmed, then found to be worse than measured. See §1.1. |
| §2 extract a cache-fingerprint primitive to core | **ACCEPT in revised form** | The stated argument does not hold (§2.1). The primitive is still worth building, as a **private** core module, for a different reason. |
| §2's `f"{a}:{b}"` hash-hygiene sub-claim | **ACCEPT** | Valid but latent, not live. §2.2. |
| §3 declare the invalidation scope | **ACCEPT — polarity inverted** | Right instinct, wrong default. An inclusion list preserves the quiet failure; an exclusion set removes it. §3. |
| §4 run provenance on `Result` | **premise corrected; recommended as a separable follow-up** | `Result.provenance` already exists, is populated, and is rendered. The handoff's grep missed it. §4. |
| §5 do not upstream the batch-corpus harness | **AGREE** | Correct reading of two CLAUDE.md principles. No action. |

### 0.1 Where a second verification pass changed the picture

Three findings that came from re-measuring rather than from re-reading:

1. **§1 is worse than the handoff measured.** The handoff's `[0, 1, 2, 4, 5]` result is an artifact of
   its work units being instantaneous. With realistic (slow) units, *every* non-failing unit runs to
   completion and is discarded, and the caller additionally waits for the **entire** map before
   learning it failed. There is no fail-fast at all. Measured in §1.1.
2. **§2's load-bearing claim is wrong.** "The core already owns a caching port but no notion of cache
   identity" treats `CachedObjective` as a persistent cache. It is not — it is within-run invariant
   reuse, so it has no cache-identity question to answer. §2.1.
3. **§4's premise is wrong.** `Result.provenance` exists at `result.py:52`, is populated by all three
   strategies, and is rendered in both output formats. The gap is one missing *key*, not a missing
   mechanism. §4.

### 0.2 Where the long-term lens changed this spec's own first pass

An initial review recommended patching `_eval_fingerprint` in place and **not** creating a shared
primitive, on YAGNI / Rule-of-Three grounds. That is reversed here, for two reasons:

- A cache-validity fingerprint is a **correctness** primitive. A second, subtly-different
  implementation does not merely duplicate code — it produces a silent stale-cache hit, i.e. a wrong
  answer with no error. Best practice tolerates less duplication for correctness primitives than for
  ordinary code, because the cost of divergence is unbounded.
- The objection to extraction was really an objection to committing a **public** `1.0` API for one
  caller. That objection disappears once the module is private: `ruthless/_logging.py` and
  `ruthless/_io.py` are existing private core modules, both listed in `.importlinter`'s
  `core-isolation` contract. There is direct precedent for a private, stdlib-only core helper shared
  across strategies.

So: build the primitive properly, place it privately, make no public API commitment. Promoting
`_fingerprint` to a public `fingerprint` later is purely additive.

> The digest in §0.3 below is a historical illustration. `tests/test_fingerprint_golden.py` is the
> single source of truth for pinned bytes.

### 0.3 Review round 1 — what changed in rev 2

Reviewed by the originating silly-kicks session (`ruthless-spec-REVIEW.md`). It re-ran every
load-bearing measurement independently (§1.1 at 2.02s against 2.03s, identical discarded set, identical
unit-seconds) and accepted both corrections to its own handoff. Five items changed this spec:

| ID | Change | Status |
|---|---|---|
| **F1** | `_tag` type-tags mapping **values** but not mapping **keys** — a measured collision in the primitive §2 exists to build, of the exact class §2.2 is fixing. | **ACCEPTED**, verified independently, fixed in §2.3 |
| **F2** | §1.7's headline determinism test could only observe the *thread* path, leaving the process executor — the one with genuinely different cancellation semantics — unpinned. | **ACCEPTED**, fixed in §1.7 |
| **F3** | The `on_error="collect"` return type invites "never raises"; it can still raise on pool death. | **ACCEPTED**, fixed in §1.5 |
| **F4** | §3's exclusion comment says a truncated run "is never cached" — it *is* written, just never read back. | **ACCEPTED**, fixed in §3, plus the test the review recommends |
| §8.3 | The Rule of Three is not actually being broken: §3's exclusion contract is a *present* second responsibility, not an anticipated one. | **ADOPTED** as the primary argument in §2.2 |

F1 was verified here before acceptance, not taken on trust: the digest reproduces byte-for-byte
(`61d5e46087f14893` for both `{"cfg": {1: "x"}}` and `{"cfg": {"1": "x"}}`), and a fourth collision pair
the review did not list also holds (`{1.0: "x"}` vs `{"1.0": "x"}`).

One hypothesis raised during that verification was **discarded as wrong**: that untagged keys could also
make `_tag`'s `sorted()` crash on unorderable values. Measured — it does not. When two keys stringify
identically, tuple comparison falls through to the tagged values, whose *type tag* sits at position 0
and is always a `str`, so the comparison resolves there. F1 rests on the collision alone.

The review also answered all five §8 prompts; those answers are folded into §8 below.

### 0.4 Review round 2 — what changed in rev 3

Round 2 verdict: **ready to implement.** The reviewer re-ran rev 2's `_tag`/`_canon` verbatim against 22
cases (against this spec's claimed 14) — all pass — and confirmed `pool.py:81`'s `BaseException`-catch,
slot-return, bare-`raise` structure. Rev 2's two arguments *against* round-1 recommendations were both
accepted and the recommendations withdrawn: the abort-escape rejection (§1.4.1) and tag-keys-rather-than-
reject (§2.3.1). Three items landed:

| ID | Change | Status |
|---|---|---|
| **R1** | The F1 fix creates a **third** deliberate consequence — two dicts that compare *equal* now digest differently — and §2.3 listed only two, inviting a reader to treat the third as a bug. | **ACCEPTED**, verified, §2.3 |
| **R2** | §1.7's test 9 required breaking a process pool without saying how — the non-obvious part, and a likely place to stall or write something flaky. Verified recipe supplied. | **ACCEPTED**, verified with one correction, §1.7.2 |
| **R3** | §1.4.1's *"any early abort is nondeterministic"* is too strong: the `workers <= 1` serial branch is index-ordered, so an abort there *would* be deterministic, and a reader could counter "then allow it only for `workers <= 1`". | **ACCEPTED**, §1.4.1 |

Both were verified here rather than accepted. R1 reproduces exactly — `{"cfg": {True: "x"}} ==
{"cfg": {1: "x"}}` is `True` while the two digests differ, matching the review's reported prefixes
byte-for-byte. The values are not restated here — `tests/test_fingerprint_golden.py` is the single
source of truth for pinned bytes. R2's recipe works on this box (py3.10.19, win32).

**One correction to R2, and it matters for test 9.** The review reports five units collected before the
pool death (`[0, 1, 3, 4, 5]`); this box collected **two** (`[0, 1]`). The recipe is sound but **the
collected set is timing-dependent**, so test 9 must assert only on the exception type — an implementer who
copies `[0, 1, 3, 4, 5]` into an assertion writes a flaky test. Recorded in §1.7.2.

The reviewer also noted a property this spec does not claim but which holds: **unsupported mapping *keys*
are fail-closed too**, since the map branch routes keys through `_canon` → `_tag`. Verified
(`dict[object, int]` raises `TypeError`). Now claimed in §2.3 so a future refactor cannot quietly lose it.

### 0.5 Scope of this spec

**In, as one branch:** §1, §2 (revised), §3.
**Recommended follow-up, separate commit, reviewer's call:** §4.
**Explicitly out:** §5, and everything in §6 Non-goals.

---

## 1. `map_work_units` — deterministic attempted-set + a real error model

**Type:** defect. **Confidence:** high, measured twice. **File:** `ruthless/parallel.py` (42 lines).

Current failure behaviour is entirely the default semantics of `parallel.py:41-42`:

```python
with pool_cls(max_workers=workers) as pool:
    return list(pool.map(fn, items))
```

### 1.1 Measured behaviour — and why the handoff understated it

The handoff's reproduction is exact and reproduces deterministically. But its work units are
instantaneous, which masks the real behaviour. Re-run with units that take real time:

```
8 units, workers=4, unit 3 raises at t=0.01s, every other unit sleeps 1.0s

  exception surfaced after      : 2.03s          <- not 0.01s
  units completed & DISCARDED   : [0,1,2,4,5,6,7]  <- all of them, not [0,1,2,4,5]
  unit-seconds of work burned   : 7.0
  unit-seconds of work RETURNED : 0.0
```

Two mechanisms the handoff did not identify:

- **`Executor.map` submits every future eagerly.** `finally: future.cancel()` in its result-iterator
  only cancels futures that have not *started*. Under any non-trivial unit duration, every unit has
  started by the time the exception is consumed in input order.
- **`with pool_cls(...)` calls `shutdown(wait=True)` on `__exit__`.** So the exception cannot surface
  until every started unit has finished. **There is no fail-fast**, and the failure is reported *late*
  — 2.03s here, against a fault that occurred at 0.01s.

Net: for a helper whose documented purpose is expensive computation, one bad unit costs 100% of the
compute for 0% of the results, plus the full wall-clock latency.

A second measurement confirms the discarded set is not a fixed quirk — with the durations inverted
(unit 3 slow, others fast) the discarded set is again all seven. The handoff's partial set only
appears when units are effectively free.

### 1.2 Correction to the handoff's Hyrum's Law framing

The handoff calls `workers` changing failure semantics "a Hyrum's Law liability" on a public API. The
compatibility constraint is weaker than that implies:

- `map_work_units` is **absent** from `ruthless/__init__.py`'s `__all__` (lines 39-74). It is
  reachable only as `ruthless.parallel.map_work_units`.
- That file's own docstring (lines 3-8) states deep submodule paths "are implementation detail and may
  move before `1.0`".
- It has **zero** internal callers (`ruthless/` contains no call site; only tests and docs reference it).

The liability is real but the freedom to fix it properly is greater than the handoff assumed. This is
the moment to change the semantics — pre-`1.0`, no internal callers, not in the curated surface.

### 1.3 Untested failure path — confirmed

`tests/test_parallel.py` is 13 lines, two tests, both happy-path order preservation. No `raise`, no
`pytest.raises`. Whatever semantics we choose are currently unpinned.

### 1.4 The unavoidable trade-off, and the decision

A parallel map cannot have serial's failure semantics without giving up either parallelism or
fail-fast. Serial short-circuits at unit 3; a pool cannot un-run what already started. So either
`workers` stops mattering, or it stays a documented best-effort.

**Decision: `workers` stops mattering. Every unit is always attempted.**

Rationale (sharpened per review): `parallel.py:1-2` states *"A consumer's Objective may call this
internally"* — so work units are **consumer code carrying consumer side effects**. Under today's
semantics `workers=1` and `workers=4` execute *different sets of those side effects* on failure. That
is not a performance difference wearing the wrong label; it is a tuning parameter silently deciding
which of the caller's writes happened. Doing strictly more work on an already-exceptional path is a
small price for removing that.

Note also that the cost is borne *only* by the serial path — the parallel path already attempts
everything (§1.1), it just throws the results away. This makes the parallel path honest and the serial
path consistent with it.

#### 1.4.1 The cost this incurs, named

Serial execution today short-circuits, which is exactly what you want when **debugging a systematic
failure**. After this change, a developer whose units all fail for one shared reason waits for the
entire map instead of stopping at unit 0. On an expensive corpus that is a real regression in the debug
loop, and it must be documented in the `map_work_units` docstring: *"a systematic failure now costs a
full pass."*

**An abort-after-N-failures escape was considered and is deliberately NOT taken.** The reason is
stronger than preference: **an early abort in the pooled path has a nondeterministic attempted-set, so
it reintroduces the precise defect §1 exists to remove.** Under `as_completed`, completion order is not
index order, so "N *consecutive* failures" means N consecutive *completions* that failed — which depends
on scheduling. Defining it over index order instead would require waiting on earlier units before
evaluating the counter, which serialises the map. And even a scheduling-independent trigger ("abort once
≥N have failed in total") still leaves *which* units got skipped timing-dependent.

**And the obvious counter-proposal fails for the same reason as the original defect (R3).** The
`workers <= 1` branch is serial and index-ordered, so an abort *there* would be perfectly deterministic —
which invites "then allow `max_failures` only when `workers <= 1`". That is worse rather than better: it
would make `workers` decide which units were attempted, which is **exactly** the property §1.4 exists to
remove. An escape that is only available at one `workers` value is a `workers`-dependent behaviour
change wearing a different hat.

If a debug-loop pain point does materialise, the shape to add is an opt-in `max_failures: int | None =
None` whose docstring states plainly that setting it **forfeits the attempted-set guarantee** and is for
debug loops only — default `None` preserving the guarantee. Recorded here so the reasoning is not
re-derived; not built, because nothing needs it yet.

### 1.5 Design

`ruthless/parallel.py` gains a failure value type, an aggregate error, and an `on_error` policy.

```python
@dataclass(frozen=True)
class UnitFailure:
    """One work-unit that raised. `index` indexes into the caller's `items`."""

    index: int
    exception: BaseException

    def __str__(self) -> str:
        return f"unit {self.index}: {type(self.exception).__name__}: {self.exception}"


class WorkUnitMapError(OptimizationError):
    """One or more work-units raised. Carries EVERY failure AND the partial results.

    Deliberately NOT a Transient/FatalEvaluationError. A work-unit is a sub-step INSIDE one objective
    evaluation, not an evaluation verdict, so classifying it as fatal-or-transient would be a category
    error and would collide with the backend retry contract (a BackendPool must never retry on this).
    It subclasses OptimizationError so `except OptimizationError` still catches it."""

    def __init__(self, failures: Sequence[UnitFailure], results: Sequence[object | None], n_items: int) -> None:
        self.failures: list[UnitFailure] = list(failures)
        self.results: list[object | None] = list(results)
        self.n_items = n_items
        shown = "; ".join(str(f) for f in self.failures[:5])
        if len(self.failures) > 5:
            shown += f"; ... (+{len(self.failures) - 5} more)"
        super().__init__(f"{len(self.failures)}/{n_items} work-units failed: {shown}")
```

That `WorkUnitMapError` docstring paragraph is the "line in the docstring" the handoff's §1.4 asked
for — it records *why* this surface does not reuse the backend taxonomy, so the asymmetry reads as a
decision rather than an oversight.

The engine — attempts everything, never raises for a unit failure:

```python
def _run_all(
    fn: Callable[[T], R], items: Sequence[T], workers: int, executor: Literal["thread", "process"]
) -> tuple[list[R | None], list[UnitFailure]]:
    n = len(items)
    results: list[R | None] = [None] * n
    failures: list[UnitFailure] = []
    if workers <= 1 or n <= 1:
        for i, x in enumerate(items):
            try:
                results[i] = fn(x)
            except Exception as exc:  # noqa: BLE001 - per-unit isolation IS the contract here
                failures.append(UnitFailure(index=i, exception=exc))
        return results, failures
    pool_cls = ThreadPoolExecutor if executor == "thread" else ProcessPoolExecutor
    with pool_cls(max_workers=workers) as pool:
        index_of = {pool.submit(fn, x): i for i, x in enumerate(items)}
        for fut in as_completed(index_of):
            i = index_of[fut]
            try:
                results[i] = fut.result()
            except BrokenExecutor:
                raise  # pool-level death: the attempted-every-unit guarantee is void, do not collect
            except Exception as exc:  # noqa: BLE001
                failures.append(UnitFailure(index=i, exception=exc))
    failures.sort(key=lambda f: f.index)
    return results, failures
```

Three details that carry weight:

- **`failures.sort(key=...)` is required, not cosmetic.** `as_completed` yields in completion order, so
  without the sort the failure *list* would be nondeterministic even though the results list is not.
  Determinism is the whole point of §1.4.
- **`BrokenExecutor` must propagate, not be collected.** `BrokenProcessPool` subclasses
  `BrokenExecutor` subclasses `RuntimeError`, so a bare `except Exception` would swallow it and report
  a dead pool as N independent unit failures. When the pool dies, the attempted-every-unit guarantee
  is void and pretending otherwise is a lie.
- **`# noqa: BLE001` with justification.** Ruff selects `BLE` (`pyproject.toml:44`). Catching broad
  `Exception` per unit is precisely the intended contract, so the suppression is correct and gets a
  reason rather than a bare code.

The public surface, with overloads so pyright keeps the default return type exact:

```python
@overload
def map_work_units(
    fn: Callable[[T], R], items: Sequence[T], *, workers: int = ...,
    executor: Literal["thread", "process"] = ..., on_error: Literal["raise"] = ...,
) -> list[R]: ...
@overload
def map_work_units(
    fn: Callable[[T], R], items: Sequence[T], *, workers: int = ...,
    executor: Literal["thread", "process"] = ..., on_error: Literal["collect"],
) -> tuple[list[R | None], list[UnitFailure]]: ...
def map_work_units(fn, items, *, workers=4, executor="thread", on_error="raise"):
    results, failures = _run_all(fn, items, workers, executor)
    if on_error == "collect":
        return results, failures
    if failures:
        raise WorkUnitMapError(failures, results, len(items)) from failures[0].exception
    return results
```

`raise ... from failures[0].exception` chains the first original exception so tracebacks stay useful.

**The docstring MUST state that `on_error="collect"` can still raise (F3).** A caller choosing
`collect` is choosing it precisely to avoid exception handling, and will read
`tuple[list[R | None], list[UnitFailure]]` as "never raises". It can raise on pool death — the one
failure mode a `collect` caller is least prepared for. Required wording, on the `collect` branch:

> *"Raises only if the pool itself dies (`BrokenExecutor`) — that voids the attempted-every-unit
> guarantee, so it cannot be reported as a per-unit failure. Unit failures are returned, never raised."*

Correspondingly, the `WorkUnitMapError` docstring must note that it is **not** the only exception
`map_work_units` can raise: `BrokenExecutor` propagates unwrapped.

### 1.6 Behaviour delta — this is a breaking change, and must be logged as one

| | Before | After |
|---|---|---|
| Units attempted | depends on `workers` | **always all of them** |
| On failure, raises | the first unit exception (e.g. `ValueError`) | `WorkUnitMapError` |
| Completed results on failure | discarded, unrecoverable | on `exc.results`; or returned via `on_error="collect"` |
| Failures reported | first only | all, ordered by index |
| Latency to failure | full map duration | full map duration (unchanged) |

A caller doing `except ValueError:` around `map_work_units` breaks. Acceptable given §1.2 (not in
`__all__`, no internal callers, `0.x` API-unstable) — but it is a genuine break and belongs in
`CHANGELOG.md` under a **Changed / BREAKING** heading, not under Fixed.

### 1.7 Tests (TDD — write these red first)

In `tests/test_parallel.py`. The two existing order-preservation tests must keep passing **unchanged**.

1. `test_raise_path_aggregates_every_failure` — two failing units ⇒ `WorkUnitMapError` with both, correct indices.
2. `test_attempted_set_is_independent_of_workers` — **the core determinism test.** Same attempted-set at `workers=1` and `workers=4`. **Parametrised over BOTH executors** — see F2 below.
3. `test_raise_path_carries_partial_results` — `exc.results` holds successes in their slots, `None` in failed slots.
4. `test_collect_returns_aligned_results_and_failures`.
5. `test_collect_with_no_failures_returns_empty_failures`.
6. `test_failures_are_ordered_by_index` — pin the sort; use uneven unit durations so completion order differs from index order. Parametrised over both executors.
7. `test_original_exception_is_recoverable` — `exc.failures[0].exception` is the original `ValueError`.
8. `test_work_unit_map_error_is_an_optimization_error` — pin the taxonomy decision.
9. `test_collect_path_can_still_raise_on_pool_death` — pin F3's contract, not just its docstring.

#### 1.7.1 F2 — the determinism test must cover the process executor

An earlier draft told the test author to use `executor="thread"` for side-effect-based assertions,
because a module-level list cannot record completions across process boundaries. The review correctly
names the consequence that draft left unstated: **the headline guarantee of §1.4 would then be pinned
for threads only** — and the process path is the one with genuinely different cancellation semantics, so
it is precisely the one that can regress silently.

Asserting on returned values is not a substitute: the property is about which units were *attempted*,
and an attempted-then-discarded unit returns nothing.

**Fix:** the work unit writes a marker file into a `tmp_path` subdirectory instead of appending to a
list. That crosses the process boundary, needs no shared state, and lets tests 2 and 6 run under both
executors from one parametrised body:

```python
@pytest.mark.parametrize("executor", ["thread", "process"])
@pytest.mark.parametrize("workers", [1, 4])
def test_attempted_set_is_independent_of_workers(tmp_path, executor, workers):
    ...  # unit touches tmp_path / f"{i}.done"; assert the marker set is identical for every (executor, workers)
```

The work unit must be a module-level function (picklable) taking the marker directory as part of its
item, since a closure over `tmp_path` will not pickle for `ProcessPoolExecutor`.

#### 1.7.2 R2 — how to break a pool for test 9, verified

Test 9 needs a genuinely dead pool, which is the non-obvious part. Verified on this box (py3.10.19,
win32) through `_run_all`'s exact `submit` + `as_completed` + `fut.result()` structure:

```python
def _suicide(x: int) -> int:  # module-level: ProcessPoolExecutor requires picklable
    if x == 2:
        os._exit(1)           # hard-kill the worker without unwinding
    return x * 10
```

`os._exit` in a worker reliably surfaces as `BrokenProcessPool`, and `isinstance(exc, BrokenExecutor)` is
`True` — so it exercises the `except BrokenExecutor: raise` branch rather than a mocked stand-in.

**Assert on the exception type ONLY.** The round-2 review observed five units collected before the pool
died (`[0, 1, 3, 4, 5]`); this box collected **two** (`[0, 1]`). The recipe is sound but **how much work
completes first is timing-dependent**, so an implementer who turns the observed set into an assertion
writes a flaky test. The behaviour under test is "a dead pool propagates `BrokenExecutor` unwrapped rather
than being reported as N unit failures" — nothing about the collected set.

Test 9 must therefore assert: `BrokenExecutor` is raised, it is *not* a `WorkUnitMapError`, and it is
raised even under `on_error="collect"` (which is the whole point of F3).

---

## 2. A hardened cache-identity primitive — private core module

### 2.1 Why the handoff's argument is rejected

The handoff's "three caching surfaces, no shared primitive" conflates three unrelated mechanisms:

| Surface | What it actually is | Cache-identity question? |
|---|---|---|
| `CachedObjective` (`objective.py:21`) | **Within-run** invariant reuse. `prepare()` rebuilds the invariant from the live objective every run. Nothing is persisted. | **None.** Nothing outlives the run, so nothing can go stale. |
| `_eval_fingerprint` (`strategy.py:130-132`) | Cross-run validity of a persisted seed-result JSON. | Yes — the only one. |
| `StoreConfig(kind="sqlite")` (`config/common.py:118-120`) | Optuna's own RDB. Identity is study-name + path. | Owned by Optuna, not ruthless. |

So the load-bearing claim — "the core already owns a caching port but no notion of cache identity" —
does not hold. `CachedObjective` is not missing an identity primitive; it has no persistence and
therefore no identity question. And with exactly **one** fingerprint implementation in the repo, there
is no duplication to remove.

**The extraction is therefore not justified as de-duplication, and nothing should be added to
`CachedObjective`.**

### 2.2 Why the primitive is built anyway, for a different reason

`strategy.py:132`:

```python
return hashlib.sha256(f"{cfg.evaluation.epochs}:{cfg.evaluation.seed}".encode()).hexdigest()[:16]
```

Untagged string concatenation over a `:` separator. **Not a live defect** — both fields are
pydantic-validated `int` (`common.py:113-115`) and an `int` cannot contain `:`, so no collision is
reachable today. It is a latent one: the first `str`-typed component makes distinct input tuples
collide, and the symptom is a silent stale-cache hit, not an error.

Two things justify building a real primitive rather than patching the f-string. Per review §8.3, the
**second is the one that carries the decision** and is stated first accordingly:

- **§3 needs somewhere to live, today.** The exclusion-set contract (§3) is the actual deliverable. It
  cannot live in `evolve_/strategy.py` without making a strategy internal the home of a correctness
  primitive that a second strategy would then have to import across a boundary `.importlinter` forbids.
  So the primitive has an **immediate, concrete second responsibility on the day it lands.** The Rule of
  Three governs *speculative* extraction — pulling something out because it *might* be reused. That is
  not what is happening here, so **the Rule of Three is not actually being broken.**
- **Failure mode asymmetry** (supporting, not load-bearing). Every other correctness guard in this repo
  fails loudly (`classify_metric` raises; backends raise). A hash-collision cache hit fails *silently and
  wrongly*. This argument stands on its own but is not needed.

Placement, per §0.2: **`ruthless/_fingerprint.py`** — private, stdlib + pydantic only (both already core
deps), no `__all__` entry, no public API commitment.

### 2.3 Design

```python
def fingerprint(payload: Mapping[str, object], *, length: int = 16) -> str:
    """Deterministic, collision-resistant hex digest over a mapping of declared inputs."""
    return hashlib.sha256(_canon(dict(payload)).encode("utf-8")).hexdigest()[:length]
```

`_canon` (below) is the single canonicalisation path — used by `fingerprint`, by mapping keys, and by set
members, so no two positions can disagree about how a value serialises.

Four properties, each a direct answer to a way the f-string version could go wrong:

- **Type-tagged, in both the value AND the key position** — `1`, `"1"`, `1.0` and `True` yield different
  digests wherever they appear. See F1 below; the key half of this was a defect in rev 1.
- **Structural, not concatenated** — JSON nesting carries the boundaries, so no separator can collide.
- **Order-insensitive** — `sort_keys=True`, so key order cannot change the digest.
- **Fail-closed on unknown types** — raises `TypeError` rather than falling back to `str()`. A `str()`
  fallback is exactly how two distinct objects acquire one digest.

```python
def _tag(value: object) -> object:
    if isinstance(value, bool):        # MUST precede int - isinstance(True, int) is True
        return ["bool", value]
    if isinstance(value, int):
        return ["int", value]
    if isinstance(value, float):
        return ["float", repr(value)]  # repr round-trips; keeps nan/inf distinguishable
    if isinstance(value, str):
        return ["str", value]
    if value is None:
        return ["none", None]
    if isinstance(value, Mapping):
        # Keys are tagged through _tag too (F1). A bare str(k) collides {1: x} with {"1": x}.
        return ["map", sorted((_canon(k), _tag(v)) for k, v in value.items())]
    if isinstance(value, (list, tuple)):
        return ["list" if isinstance(value, list) else "tuple", [_tag(v) for v in value]]
    if isinstance(value, (set, frozenset)):
        return ["set", sorted(_canon(v) for v in value)]
    raise TypeError(f"fingerprint: unsupported type {type(value).__name__!r}; extend _tag deliberately")


def _canon(value: object) -> str:
    """Tagged value as a canonical string - used where a SORTABLE tagged form is needed."""
    return json.dumps(_tag(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
```

The `bool`-before-`int` ordering is load-bearing: `isinstance(True, int)` is `True`, so the natural
ordering would tag `True` as `["int", True]` and collide it with `1`.

> Digests in §2.3.1 below are historical illustrations. `tests/test_fingerprint_golden.py` is the single
> source of truth for pinned bytes.

#### 2.3.1 F1 — rev 1 tagged values but not keys. Measured collision.

Rev 1's mapping branch was `sorted((str(k), _tag(v)) for ...)` — `str(k)`, bare. Verified here against
rev 1's verbatim code:

```
{'cfg': {1:   'x'}}            -> 61d5e46087f14893
{'cfg': {'1': 'x'}}            -> 61d5e46087f14893   COLLIDE
{'p': {1: 0.5, 2: 0.7}}  vs  {'p': {'1': 0.5, '2': 0.7}}   COLLIDE
{'cfg': {1.0: 'x'}}      vs  {'cfg': {'1.0': 'x'}}         COLLIDE
value position (control): 1 / "1" / 1.0 / True  ->  all four distinct
```

**Reachability:** not reachable from the two specified callers today — `fingerprint` is typed
`Mapping[str, object]` and `fingerprint_model` receives `model_dump()` output. So its status is *exactly*
that of the `f"{a}:{b}"` bug §2.2 exists to fix: **latent, silent, and one `dict[int, float]`-typed
config field away from live.** Shipping a primitive built to eliminate untagged-string collisions while
containing one would be incoherent, so it closes in the same change.

**Why tag keys rather than reject non-`str` keys.** The review preferred rejecting them, on the grounds
that it matches "extend `_tag` deliberately". Tagging is chosen instead for one reason that outweighs
that: **rejecting closes the collision only by refusing the input, so the collision class silently
reopens the moment a future author extends `_tag` to accept non-`str` keys without remembering to tag
them.** Tagging is structurally safe; rejecting depends on a future author's care. Secondarily, a mapping
key has exactly one correct treatment — tag it — and fail-closed earns its keep where the correct
behaviour is *ambiguous* (a `datetime`: which precision? which timezone?), not where it is obvious.

`{True: 'x'}` and `{1: 'x'}` happen *not* to collide under rev 1, but only because `str(True)` is
`"True"`. The `bool`-before-`int` care that is principled in the value position was accidental in the key
position — which is the tell that the key position was never designed.

One hypothesis checked and **discarded**: that untagged keys could also crash `sorted()` on unorderable
values. Measured — they do not, because when two keys stringify alike the comparison falls through to the
tagged values, whose type tag sits at position 0 and is always a `str`. F1 rests on the collision alone.

**The rev-2 `_tag`/`_canon` sketch above is execution-verified, not merely plausible.** It was run against
14 cases before being written into this spec — all four F1 pairs, §2.2's separator pair, four
value-position pairs, list-vs-tuple, set membership, three order-insensitivity cases, and the
fail-closed `TypeError`. All 14 behave as specified. Note `_canon` is reused for the `set` branch, which
also upgrades rev 1's set handling from `json.dumps(_tag(v), sort_keys=True)` to the same canonical form,
so sets and mapping keys cannot disagree about how a value is serialised.

**Three** documented, deliberate consequences — all three err toward an unnecessary miss, never a stale
hit. Enumerated in full because listing a subset invites the next reader to file the omitted one as a bug:

1. `-0.0` and `0.0` get different digests despite comparing equal.
2. **Two mappings that compare equal can digest differently (R1).** `{"cfg": {True: "x"}} ==
   {"cfg": {1: "x"}}` is `True` in Python — `True == 1` and `hash(True) == hash(1)` — but the digests
   differ (measured; the values are not restated here — `tests/test_fingerprint_golden.py` is the
   single source of truth for pinned bytes). This is a direct consequence of tagging keys, i.e. of the
   F1 fix, and it is the same safe-direction trade as (1).
3. Extending `_tag` to a new type (`Path`, `datetime`, `Enum`) is an explicit change with a test rather
   than an accident.

One further property, **claimed here so a future refactor cannot quietly lose it**: unsupported mapping
*keys* are fail-closed too. Because the map branch routes keys through `_canon` → `_tag`, a
`dict[SomeObject, int]` raises the same `TypeError` as an unsupported *value*. This falls out of the F1
fix rather than having been designed, which is exactly why it needs writing down.

### 2.4 Migration

`_eval_fingerprint` **stays in `evolve_/strategy.py`** as a thin delegating wrapper. Two reasons: it
keeps `tests/strategies/evolve/test_evolve_strategy.py:134`'s import path working (that test calls
`strat._eval_fingerprint(cfg)` and is algorithm-agnostic, so it keeps passing), and the *policy* of
what evolve excludes is evolve's business, not the core's.

`.importlinter` must gain `ruthless._fingerprint` under `core-isolation` `source_modules`, alongside
`ruthless._io` and `ruthless._logging`. `evolve_/strategy.py` importing it is the allowed
strategy→core direction and violates no contract.

**One-time effect:** the digest *value* changes even though the *input set* does not, so existing
on-disk seed caches miss once and recompute. Benign, and in the fail-closed direction. Worth a
CHANGELOG line so it is not mistaken for a bug.

---

## 3. Invalidation scope as an exclusion set, not an inclusion list

`_eval_fingerprint`'s docstring (`strategy.py:131`) declares its scope in prose:

> `"""Deterministic hash of the eval params that affect seed results (epochs/seed; no dataset)."""`

The handoff is right that this should be a parameter rather than a comment. **It has the polarity
backwards.** Declaring an *inclusion* list preserves the exact quiet failure it sets out to fix: a new
`EvalConfig` field that does affect results is not in the list, the fingerprint does not change, and
stale results are reused as valid.

**Fingerprint every field, minus a named exclusion set.** Then a newly-added field is included *by
default*, so the worst case of forgetting to think about it is an unnecessary cache **miss** —
recompute, safe — instead of a stale **hit** — wrong. Same cost, opposite failure direction. And every
exclusion remains a visible, reviewable line in a diff, which was the handoff's real objective.

```python
def fingerprint_model(model: BaseModel, *, exclude: frozenset[str] = frozenset(), length: int = 16) -> str:
    """Fingerprint ALL of `model`'s fields except those named in `exclude`.

    Declare what determines the cached artifact's CONTENT, not what CONSUMES it. Anything recomputed
    downstream on every run is excluded by construction.

    Fail-closed: a field ADDED to the model later is INCLUDED unless someone explicitly excludes it, so
    forgetting to revisit this call costs a recompute, never a stale reuse.

    Raises ValueError if `exclude` names a field the model does not have - otherwise a renamed or
    deleted field leaves a silently-ineffective exclusion behind.

    LIMITATION, stated deliberately: this checks that exclusions EXIST, not that they are CORRECT. An
    author can exclude a field that does matter and get a fingerprint that never changes. This
    converts a silent omission into a visible, reviewable, wrong line - it does not prove the scope."""
    fields = set(type(model).model_fields)
    unknown = exclude - fields
    if unknown:
        raise ValueError(
            f"exclude names non-existent field(s) {sorted(unknown)} on {type(model).__name__}; "
            f"known fields: {sorted(fields)}"
        )
    payload = {k: v for k, v in model.model_dump().items() if k not in exclude}
    return fingerprint(payload, length=length)
```

The `unknown` check closes a gap the handoff did not raise: a *stale exclusion name*. Rename
`timeout_seconds` and an inclusion-list design fails silently; here it raises.

The `LIMITATION` paragraph is deliberate. The handoff was right that a declaration cannot be checked
for completeness, and right that the docstring must not overclaim. It says so in the docstring, where
the next author will actually read it.

Call site:

```python
# EvalConfig fields deliberately EXCLUDED from seed-cache identity, with the reason for each.
# Rule: declare what determines the cached artifact's CONTENT, not what CONSUMES it.
_SEED_CACHE_EXCLUDE = frozenset({
    # An infra budget, not a determinant of a seed's metrics. A truncated run maps to the worst-score
    # sentinel (combined_score=0) and is WRITTEN like any other result - _eval_one writes
    # unconditionally - but is never READ BACK, because _load_cached_seeds accepts only
    # combined_score > 0.0. That read filter is the ONLY thing making this exclusion safe; it is
    # pinned by test_a_zero_score_seed_result_is_never_cache_readable. Relax it and this exclusion
    # becomes silently unsafe.
    "timeout_seconds",
})


def _eval_fingerprint(cfg: EvolveConfig) -> str:
    """Deterministic identity of the eval params that determine seed-result CONTENT.

    Delegates to the shared core primitive, which covers EVERY EvalConfig field except
    `_SEED_CACHE_EXCLUDE`, so a new field is picked up automatically (fail-closed - see
    `ruthless._fingerprint.fingerprint_model`)."""
    return fingerprint_model(cfg.evaluation, exclude=_SEED_CACHE_EXCLUDE)
```

Note this preserves today's *effective* scope exactly — `EvalConfig` is `{epochs, timeout_seconds,
seed}`, so all-minus-`timeout_seconds` is `{epochs, seed}`, which is what the old f-string covered. The
change is in what happens to the *next* field, not to the current ones.

### 3.1 Tests

New `tests/test_fingerprint.py`:

1. `test_fingerprint_is_deterministic` — same payload, repeated calls, identical digest.
2. `test_type_tags_prevent_cross_type_collision` — `1` / `"1"` / `1.0` / `True` all differ.
3. **`test_nested_mapping_keys_are_type_tagged`** — the F1 regression test. (Not `..._KEYS_...` as round 1
   suggested: ruff selects `N` (`pyproject.toml:44`) and `N802` rejects uppercase in a function name, with
   no per-file ignore for tests. Same correction applies to §3.2's test name.) All four measured pairs:
   `{"cfg": {1: "x"}}` vs `{"cfg": {"1": "x"}}`; `{"p": {1: 0.5, 2: 0.7}}` vs `{"p": {"1": 0.5, "2": 0.7}}`;
   `{"cfg": {1.0: "x"}}` vs `{"cfg": {"1.0": "x"}}`; and `{"cfg": {True: "x"}}` vs `{"cfg": {1: "x"}}`
   (which passes accidentally in rev 1 and must pass *by construction* now).
4. `test_separator_collision_is_impossible` — the regression test for §2.2's latent bug:
   `{"a": "1:2", "b": "3"}` vs `{"a": "1", "b": "2:3"}` must differ. The old scheme collides them.
5. `test_key_order_does_not_change_digest`.
6. `test_unsupported_type_raises_type_error` — fail-closed, no `str()` fallback.
7. `test_nested_containers_are_supported`.
8. `test_fingerprint_model_rejects_unknown_exclusion` — the stale-exclusion guard.
9. `test_excluded_field_does_not_change_digest`.
10. `test_included_field_changes_digest`.
11. **`test_new_model_field_changes_digest`** — the §3 contract. Two throwaway pydantic models
    differing by one added field must fingerprint differently. This is the test that would have caught
    the quiet failure.

Extend `tests/strategies/evolve/test_evolve_strategy.py`:

12. `test_eval_fingerprint_tracks_epochs_and_seed_but_not_timeout` — pin evolve's declared scope.
13. **`test_a_zero_score_seed_result_is_never_cache_readable`** — see §3.2.

### 3.2 F4 — the one unguarded link in the `timeout_seconds` argument

Review §8.4 tried to break the exclusion and could not, tracing all four links: `timeout_seconds` reaches
only `EvolveEvaluator(timeout=...)` (`strategy.py:113`), `create_backend(..., timeout=...)` (`:281`,
`:285`) and OpenEvolve's own evaluator config (`:217`) — never a consumer objective's params; a
backend-enforced timeout raises `TransientEvaluationError`; `evaluator.py:139` maps that to the
worst-score sentinel (`combined_score=0`, `evaluator.py:9-11`); and `_load_cached_seeds` accepts only
`combined_score > 0.0` (`strategy.py:148`). Sound.

But it is a four-link chain across three files and **not one link is pinned by a test.** §3's fail-closed
design protects against a new *field*; nothing protects against the *reasoning behind an existing
exclusion* going stale. Relax `> 0.0` to `>= 0.0`, or add a `partial=True` acceptance path, and the
exclusion becomes unsafe **silently** — the comment still reads as valid and `fingerprint_model`'s
stale-exclusion guard still passes, because the field still exists.

```python
def test_a_zero_score_seed_result_is_never_cache_readable(tmp_path):
    """Load-bearing for _SEED_CACHE_EXCLUDE's `timeout_seconds` entry: a truncated run maps to the
    worst-score sentinel (combined_score=0), is WRITTEN to the seed-results dir like any other result,
    and this read filter is the ONLY thing that stops it being reused. Relax it and the timeout
    exclusion becomes silently unsafe."""
```

This converts a prose dependency into a gate — the move this spec makes everywhere else. The exclusion
comment in §3 now cross-references this test by name, so the two cannot drift apart unnoticed.

---

## 4. Run provenance — premise corrected, recommended as a separate commit

### 4.1 The handoff's premise is wrong

> "Neither carries any record of the code version that produced it. Grepping for `git` across
> `ruthless/` returns only substring matches […] there is no provenance capture anywhere."

There is. `Result.provenance: dict[str, Any]` exists at `result.py:52`, is populated by **all three**
strategies (`random_/strategy.py:70`, `optuna_/strategy.py:122`, `evolve_/strategy.py:385`), and is
rendered in **both** output formats (`report.py:29` JSON, `report.py:48` Markdown). The grep for `git`
missed it because the field is not named after git.

This narrows the item substantially: the gap is **one missing key in an existing, populated, rendered
dict** — not a new mechanism. It also undercuts the "arguably consumer territory" hedge, since
`provenance` is built inside each strategy's `run()` and `Result` is treat-as-immutable once returned,
so a consumer cannot cleanly add to it.

### 4.2 Why it is still recommended, and still separable

Recommended because the direction of Hyrum's Law favours doing it early: adding a key to a rendered
dict is the safe, additive change, but every artifact produced *before* it lands is permanently
unattributable. Deferring does not reduce the cost; it enlarges the un-attributed back-catalogue.

Separable because it introduces `subprocess` and a git dependency into a core that currently depends
only on pydantic + numpy + pyyaml, and a new failure surface inside `run()`. That deserves its own
commit and its own review, not a rider on §1-§3.

### 4.3 Design, if taken

`ruthless/_provenance.py` (private core; add to `.importlinter` `core-isolation`):

```python
def code_identity(*, repo_root: Path | None = None) -> dict[str, Any]:
    """{"ruthless_version": ..., "ruthless_git_commit": <sha>|None,
        "ruthless_git_state": "clean"|"dirty"|"unknown"}"""
```

Two refinements made while planning, both about not overclaiming:

- **The keys are `ruthless_`-prefixed.** A bare `git_commit` on a `Result` reads as "the code that
  produced this run", which a reader would take to include *their objective*. It cannot: this captures
  ruthless's own tree only. The prefix makes the scope self-evident at the point of reading, which is the
  same principle as never emitting a SHA without a state.
- **The repo is resolved from `Path(__file__)`, not the CWD — and the discovered repo must be proved to
  own this module.** `repo_root` exists so tests can point it at a `tmp_path` fixture instead of
  monkeypatching the working directory.

  **Corrected during plan review (P1) — the first version of this bullet was measured false.** It claimed
  "a pip-installed ruthless has no repo and correctly reports `unknown`". It does not: a wheel installed
  into a project-local venv sits at `<consumer-repo>/.venv/Lib/site-packages/ruthless/`, which is *inside
  the consumer's repo*, so `git rev-parse HEAD` from there returns **the consumer's commit** — measured,
  and being gitignored makes no difference, because git walks up for `.git` and never consults ignore
  rules. A project-local venv is the default for uv, Poetry and `python -m venv`, so that is the normal
  case. Worse, the `ruthless_` prefix makes the resulting SHA *specifically* false rather than merely
  vague — precisely the verifiable-looking false provenance this section exists to prevent.

  The fix is a containment check (`_repo_tracks_module`), applied only when `repo_root` was not supplied:
  **ask git whether the enclosing repo tracks this module as source** (`git ls-files --error-unmatch`). A
  source checkout and `pip install -e` both pass; a wheel inside a consumer repo is rejected and reports
  `"unknown"` with `ruthless_version` as the identity.

  Plan review round 1 proposed comparing `--show-toplevel` against `<toplevel>/ruthless/<module>` instead.
  That works today but encodes an unstated assumption — the package sits at the repo root — so a move to a
  `src/` layout would make a *legitimate* checkout fail the check and silently degrade provenance to
  `"unknown"` everywhere. Round 2 flagged that as a documented-around limitation; asking git removes it.
  Measured across five layouts: `ls-files` is correct on all five, path comparison is wrong on `src/`. See
  the plan's Task 7 for the code, the measurement table, and the five regression tests.

The trap the handoff flags is real and its warning should be honoured literally: `git rev-parse HEAD`
returns the same SHA from a dirty tree, so **a bare SHA is verifiable-looking false provenance —
strictly worse than recording nothing.** Therefore:

- `git_commit` is **never** emitted without an accompanying `git_state`.
- Dirtiness via `git status --porcelain` (non-empty ⇒ `"dirty"`). Not `git diff --quiet`, which misses
  untracked files.
- No git binary / not a repo / non-zero exit / timeout ⇒ `git_commit=None, git_state="unknown"`.
  `"unknown"` is as untrustworthy as `"dirty"`; it must never degrade to `"clean"`.
- `shutil.which("git")` + `subprocess.run(..., capture_output=True, timeout=5, check=False)`. Ruff
  selects `S`, so `S603`/`S607` need either a resolved absolute path or a justified `# noqa`.
- Captured at **run** time in each strategy (`provenance={..., **code_identity()}`), not at render
  time — `render_json` may be called later, from a different tree.

Tests must cover all three `git_state` values, including a non-repo temp dir asserting
`"unknown"` and never `"clean"`.

**Rendered visibility (review §8.5).** The distinction between `"dirty"` and `"unknown"` has to survive
into the *output*, not just live internally — a reader seeing `git_commit: null, git_state: "unknown"`
learns something true; a reader seeing a SHA with no state learns something false. `report.py:29` (JSON)
is fine, since it serialises the dict. `report.py:48` renders provenance as a bare `dict` repr
(`f"**Provenance:** \`{result.provenance}\`"`), which will grow into an unreadable single line as keys are
added and could bury `git_state`. Recommend rendering provenance as a small key/value list in the
Markdown path — with the Hyrum's Law caveat that the Markdown summary is an observable output format, so
that reformat belongs in the same §4 commit and gets its own CHANGELOG line.

---

## 5. Not upstreaming the batch-corpus harness — agreed

The handoff's §5 declines to upstream a batch-corpus driver, citing:

> *"Each strategy owns its loop. The core imposes no template-method driver."*
> *"Persistence/resume is strategy-internal."*

Both quotes are accurate to `CLAUDE.md`, and the conclusion follows. Such a harness is a
template-method driver that owns persistence, and a corpus scan is not a candidate evaluation — so
neither `parallel.map_work_units` nor `ComputeBackend.evaluate` is a fit either. **No action.** Noted
here so a future reader sees it was considered and declined on principle, not overlooked.

---

## 6. Non-goals

Stated explicitly so review can hold the diff to them:

- **No public fingerprint API.** `_fingerprint` is private, absent from `__all__`. Promotion is a later,
  additive decision that should wait for a second real caller.
- **No change to `CachedObjective` or `assert_cache_equivalence`.** Per §2.1 they have no
  cache-identity question. Adding a fingerprint there would be speculative generality.
- **No change to `StoreConfig` / Optuna resume.** Study identity is Optuna's.
- **No template-method driver, no batch-corpus harness, no persistence in core.** Per §5.
- **No new runtime dependency.** §1-§3 are stdlib + already-present pydantic.
- **No change to `Result`/`report.py` in §1-§3.** Only §4 touches those, in its own commit.
- **No new provenance mechanism.** §4, if taken, adds keys to the existing dict.

## 7. Acceptance criteria

All five gate commands green (per `CLAUDE.md`, Shift Left):

```bash
uv run ruff check ruthless tests
uv run ruff format --check ruthless tests
uv run pyright
uv run lint-imports          # 3 contracts, with _fingerprint added to core-isolation
uv run pytest -v
```

Plus:

- The 158-test baseline still passes; the two existing `test_parallel.py` tests pass **unmodified**.
- `tests/strategies/evolve/test_evolve_strategy.py:134` still passes unmodified.
- The three tests that pin the round-1 findings are present and were **red before the fix**: F1's
  `test_nested_mapping_KEYS_are_type_tagged` (§3.1 #3), F2's determinism test parametrised over **both**
  executors (§1.7.1), and F3's `test_collect_path_can_still_raise_on_pool_death` (§1.7 #9).
- §3.2's `test_a_zero_score_seed_result_is_never_cache_readable` exists and the `_SEED_CACHE_EXCLUDE`
  comment names it, so the exclusion and the test that justifies it cannot drift apart silently.
- `lint-imports` still reports 3 contracts kept, with `ruthless._fingerprint` (and `ruthless._provenance`
  if §4 lands) listed under `core-isolation`.
- `CHANGELOG.md` `[Unreleased]`: `map_work_units` under **Changed (BREAKING)** with the `except ValueError`
  → `except WorkUnitMapError` migration note; the one-time seed-cache invalidation under **Changed**.
- `/final-review` run before commit, per project convention. C4 diagram regenerated if the module
  inventory changed (it does — `_fingerprint` is a new core component).
- One feature branch, TDD red→green per change, no commit without explicit approval.

## 8. Reviewer prompts — answered in round 1

All five were answered. Resolutions, and what each changed:

| Prompt | Resolution | Effect on the spec |
|---|---|---|
| **§8.1** "always attempt every unit" — right, given the serial path does more work? | **Yes**, with a sharper argument: work units are consumer code with consumer side effects, so `workers` currently decides which of the caller's *writes* happened. | Argument adopted in §1.4. The unnamed cost — losing serial short-circuit hurts the debug loop — is now named in §1.4.1, with the abort escape rejected on the grounds that any early abort is nondeterministic by construction. |
| **§8.2** Is `WorkUnitMapError(OptimizationError)` the right slot? | **Yes, and verifiable rather than aesthetic:** `pool.py:75` retries `TransientEvaluationError` specifically and `pool.py:81` catches `BaseException` only to return the slot before re-raising. A sibling class is *structurally* un-retryable. | Confirmed independently. §1.5 now also states that `BrokenExecutor` propagates unwrapped (F3). |
| **§8.3** Is breaking the Rule of Three fair? | **The Rule of Three is not being broken.** It governs *speculative* extraction; §3's exclusion contract is a concrete second responsibility on day one. | §2.2 reordered to lead with this; the correctness-primitive argument demoted to supporting. |
| **§8.4** Is `timeout_seconds` genuinely excludable? "Try to break it." | **Could not be broken** — all four links traced and sound. But no link is pinned by a test, and the comment misdescribed *where* the safety lives. | F4: comment corrected (written unconditionally, never *read back*), plus the read-filter test in §3.2. |
| **§8.5** Take §4 now or defer? | **Now, own commit**, on §4.2's asymmetry argument. | §4.3 gains the rendered-visibility requirement for `git_state`. |

### 8.1 The one open question — resolved in round 2

**Question:** §4's Markdown provenance reformat. `report.py:48` renders the provenance dict as a bare
one-line repr. Adding `git_commit`/`git_state` makes it unreadable, but reformatting changes an observable
output format (Hyrum's Law).

**Resolved: reformat.** The Hyrum's Law concern is already answered by the repo's own documentation —
`render_summary_md`'s docstring at `report.py:40` states *"For the full machine-readable surface use
`render_json`."* The module has **already declared** which surface is machine-readable and which is a human
summary, so a consumer parsing the Markdown is doing so against an explicit instruction. That is not the
situation Hyrum's Law describes: the contract was stated up front, and `render_json` (`report.py:29`) is
unchanged and serialises the dict faithfully.

Two constraints on the reformat:

- **`git_state` gets its own line**, never folded into a growing repr. That is the entire point of §4.3's
  never-a-SHA-without-a-state rule — a one-line repr that runs past terminal width buries precisely the
  field that must not be buried.
- **It still takes a CHANGELOG line**, in the §4 commit. Not because a machine consumer breaks, but
  because a human diffing two runs' summaries will notice, and an unexplained format change is a small
  trust cost for no reason.

Residual risk, stated rather than closed: neither this session nor the reviewer has visibility into
ruthless's downstream consumers, so "someone parses the Markdown anyway" cannot be ruled out. Given the
docstring's explicit instruction and an unchanged `render_json`, this is as strong a position as the
decision admits.

**No open questions remain.** Rev 3 is approved to implement; see the companion plan,
`docs/superpowers/plans/2026-07-29-parallel-error-model-and-cache-identity-plan.md`.
