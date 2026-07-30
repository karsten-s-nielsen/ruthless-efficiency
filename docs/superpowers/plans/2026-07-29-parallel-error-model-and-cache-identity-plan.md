# Work-Unit Map Error Model + Cache-Identity Primitive — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-07-29-parallel-error-model-and-cache-identity.md` (rev 3, approved
after two review rounds). Read §1, §2, §3 of the spec before Task 1 — this plan implements it and does not
restate its reasoning.

**Goal:** Give `map_work_units` a deterministic attempted-set and a real error model, and replace evolve's
hand-rolled cache fingerprint with a hardened private core primitive whose invalidation scope is a declared
exclusion set rather than a comment.

**Architecture:** **One feature branch, one commit, one PR** bundling the spec, this plan, and all code
(project convention — never docs alone, and the commit lands only after TDD and the full gate pass). The
work has three parts, executed in order as a TDD sequence but **not** committed separately. Part 1 rewrites
`ruthless/parallel.py`'s failure path (breaking: raises `WorkUnitMapError` instead of the first unit
exception). Part 2 adds `ruthless/_fingerprint.py` — a private, stdlib+pydantic core module in the same slot
as `_logging.py` and `_io.py` — and migrates `evolve_`'s `_eval_fingerprint` onto it. Part 3 adds
`ruthless/_provenance.py` and wires code identity into the existing `Result.provenance` dict.

**Scope note:** the spec (§4.2) and both review rounds recommended taking Part 3 **now** rather than
deferring, but as its own commit. The "own commit" half is overridden by the single-commit convention; the
"take it now" half stands, so Part 3 is in scope. Dropping it is a clean cut — delete Tasks 7 and 8 and
their two CHANGELOG entries; nothing in Parts 1-2 depends on them.

**Tech Stack:** Python 3.10, pydantic v2, pytest, ruff, pyright (basic), import-linter, hatchling.

## Global Constraints

- **No new runtime dependency.** Commits A and B are stdlib + already-present pydantic only.
- **Line length 120**, ruff `target-version = "py310"` (`pyproject.toml:40-41`).
- **Ruff selects `["E","W","F","I","N","UP","B","S","BLE","RUF"]`** (`pyproject.toml:44`). Consequences that
  bite in this plan: `BLE001` flags `except Exception` (needs a justified `noqa`); **`N802` flags any
  uppercase in a function name — including test names**; only `S101` is ignored for tests
  (`pyproject.toml:47`).
- **pyright `typeCheckingMode = "basic"`, include `["ruthless", "tests"]`** (`pyproject.toml:49-51`). Tests
  are type-checked too.
- **Every new private core module must be added to `.importlinter`'s `core-isolation` `source_modules`**,
  alongside `ruthless._io` / `ruthless._logging`. `lint-imports` must report **3 contracts kept**.
- **Baseline is 158 tests.** The two existing `tests/test_parallel.py` tests and
  `tests/strategies/evolve/test_evolve_strategy.py:134` must pass **unmodified**.
- **Library never configures root logging** — use `ruthless._logging.get_logger(name)` if logging is needed.
- **ONE commit for the whole branch.** Do not commit at the end of a part. Every task ends at a green
  checkpoint; the single commit happens in Task 9, after `/final-review`. Docs are never committed alone —
  the spec, this plan, and all code land together.
- **No commit without explicit user approval** (project convention). `/final-review` is the mandatory
  pre-commit gate. **No git worktrees** — feature branch in this repo.
- **Create the branch before Task 1:** `git switch -c feat/parallel-error-model-cache-identity`. `main` is
  the default branch and must not be committed to directly.
- **The five-command gate must be green before any commit:**
  ```bash
  uv run ruff check ruthless tests
  uv run ruff format --check ruthless tests
  uv run pyright
  uv run lint-imports
  uv run pytest -v
  ```

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `ruthless/parallel.py` | Rewrite (42 → ~130 lines) | `UnitFailure`, `WorkUnitMapError`, `_run_all`, `map_work_units` with `on_error` |
| `tests/test_parallel.py` | Extend (13 → ~150 lines) | §1's 9 tests; the 2 existing tests stay byte-identical |
| `ruthless/_fingerprint.py` | Create | `_tag`, `_canon`, `fingerprint`, `fingerprint_model` — private core |
| `tests/test_fingerprint.py` | Create | §3.1's 11 tests |
| `ruthless/strategies/evolve_/strategy.py` | Modify (`:18`, `:130-132`) | `_SEED_CACHE_EXCLUDE` + `_eval_fingerprint` delegates; drop `hashlib` import |
| `tests/strategies/evolve/test_evolve_strategy.py` | Extend | §3.1 #12, §3.2's read-filter test |
| `.importlinter` | Modify (`:9-25`) | Add `ruthless._fingerprint` (and `ruthless._provenance` in Commit C) |
| `CHANGELOG.md` | Modify (`:7`) | New `## [Unreleased]` section — none exists today |
| `ruthless/_provenance.py` | Create (Commit C) | `code_identity()` — git SHA + state, fail-safe |
| `tests/test_provenance.py` | Create (Commit C) | clean / dirty / unknown |
| `ruthless/strategies/{random_,optuna_,evolve_}/strategy.py` | Modify (Commit C) | merge `code_identity()` into `provenance` |
| `ruthless/report.py` | Modify (`:48`, Commit C) | provenance as key/value lines, not a bare repr |

---

# PART 1 — §1 work-unit map error model *(no commit at the end)*

## Task 1: Failure value type and error taxonomy

**Files:**
- Modify: `ruthless/parallel.py` (add to the existing 42-line module)
- Test: `tests/test_parallel.py`

**Interfaces:**
- Consumes: `ruthless.errors.OptimizationError` (`errors.py:14`)
- Produces:
  - `UnitFailure` — frozen dataclass, fields `index: int`, `exception: BaseException`
  - `WorkUnitMapError(OptimizationError)` — `__init__(failures: Sequence[UnitFailure], results: Sequence[object | None], n_items: int)`; attributes `.failures: list[UnitFailure]`, `.results: list[object | None]`, `.n_items: int`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_parallel.py`:

```python
def test_work_unit_map_error_is_an_optimization_error():
    """Pins spec §8.2: WorkUnitMapError sits under OptimizationError but is deliberately OUTSIDE the
    Transient/Fatal evaluation taxonomy, so BackendPool (which retries TransientEvaluationError
    specifically, pool.py:75) can never retry it."""
    assert issubclass(WorkUnitMapError, OptimizationError)
    assert not issubclass(WorkUnitMapError, TransientEvaluationError)
    assert not issubclass(WorkUnitMapError, FatalEvaluationError)


def test_work_unit_map_error_message_and_attributes():
    failures = [UnitFailure(index=1, exception=ValueError("bad")), UnitFailure(index=3, exception=KeyError("k"))]
    exc = WorkUnitMapError(failures, [10, None, 30, None], 4)
    assert exc.failures == failures
    assert exc.results == [10, None, 30, None]
    assert exc.n_items == 4
    assert "2/4 work-units failed" in str(exc)
    assert "unit 1: ValueError: bad" in str(exc)


def test_work_unit_map_error_truncates_a_long_failure_list():
    failures = [UnitFailure(index=i, exception=ValueError(f"e{i}")) for i in range(8)]
    exc = WorkUnitMapError(failures, [None] * 8, 8)
    assert "(+3 more)" in str(exc)
    assert len(exc.failures) == 8  # truncation is display-only, never data loss
```

Add to the imports at the top of `tests/test_parallel.py` (leave the existing
`from ruthless.parallel import map_work_units` line intact — ruff `I` will order these):

```python
from ruthless.errors import FatalEvaluationError, OptimizationError, TransientEvaluationError
from ruthless.parallel import UnitFailure, WorkUnitMapError, map_work_units
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parallel.py -v`
Expected: FAIL at collection — `ImportError: cannot import name 'UnitFailure' from 'ruthless.parallel'`

- [ ] **Step 3: Write minimal implementation**

In `ruthless/parallel.py`, extend the imports and add the two types **above** `map_work_units`:

```python
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal, TypeVar

from ruthless.errors import OptimizationError

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True)
class UnitFailure:
    """One work-unit that raised. ``index`` indexes into the caller's ``items``."""

    index: int
    exception: BaseException

    def __str__(self) -> str:
        return f"unit {self.index}: {type(self.exception).__name__}: {self.exception}"


class WorkUnitMapError(OptimizationError):
    """One or more work-units raised. Carries EVERY failure AND the partial results.

    Deliberately NOT a Transient/FatalEvaluationError. A work-unit is a sub-step INSIDE one objective
    evaluation, not an evaluation verdict, so classifying it as fatal-or-transient would be a category
    error and would collide with the backend retry contract (`BackendPool` retries
    `TransientEvaluationError` specifically, so a sibling class is structurally un-retryable). It
    subclasses `OptimizationError` so ``except OptimizationError`` still catches it.

    NOTE: this is not the only exception `map_work_units` can raise — a dead pool propagates
    `concurrent.futures.BrokenExecutor` unwrapped, because that voids the attempted-every-unit
    guarantee and so cannot honestly be reported as a per-unit failure."""

    def __init__(self, failures: Sequence[UnitFailure], results: Sequence[object | None], n_items: int) -> None:
        self.failures: list[UnitFailure] = list(failures)
        self.results: list[object | None] = list(results)
        self.n_items = n_items
        shown = "; ".join(str(f) for f in self.failures[:5])
        if len(self.failures) > 5:
            shown += f"; ... (+{len(self.failures) - 5} more)"
        super().__init__(f"{len(self.failures)}/{n_items} work-units failed: {shown}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_parallel.py -v`
Expected: PASS — 5 tests (3 new + the 2 pre-existing order-preservation tests, unmodified)

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check ruthless tests && uv run ruff format ruthless tests && uv run pyright`
Expected: all clean. If `ruff format` rewrites anything, re-run `pytest`.

---

## Task 2: `_run_all` — attempt every unit, deterministically

**Files:**
- Modify: `ruthless/parallel.py`
- Test: `tests/test_parallel.py`

**Interfaces:**
- Consumes: `UnitFailure` (Task 1)
- Produces: `_run_all(fn: Callable[[T], R], items: Sequence[T], workers: int, executor: Literal["thread", "process"]) -> tuple[list[R | None], list[UnitFailure]]` — positional args, never raises for a unit failure, `failures` sorted by `index`

- [ ] **Step 1: Write the failing tests**

**Put the five imports below at the TOP of `tests/test_parallel.py`** (ruff `I` will order them) and append
only the functions — ruff selects `E`, and `E402 Module level import not at top of file` fails the gate if
they land after a definition:

```python
import concurrent.futures
import os
from pathlib import Path

import pytest

from ruthless.parallel import _run_all
```

Then append the rest. `_touch_marker` and `_suicide` **must be module-level** — a `ProcessPoolExecutor`
pickles the callable, and a closure over `tmp_path` will not pickle.

```python
def _touch_marker(item: tuple[str, int]) -> int:
    """Record 'this unit ran' in a way that crosses the process boundary (spec §1.7.1)."""
    marker_dir, i = item
    Path(marker_dir, f"{i}.done").write_text("")
    if i == 3:
        raise ValueError(f"unit {i} is bad")
    return i * 10


def _suicide(x: int) -> int:
    """Hard-kill the worker to produce a genuinely dead pool (spec §1.7.2, verified py3.10/win32)."""
    if x == 2:
        os._exit(1)
    return x * 10


@pytest.mark.parametrize("executor", ["thread", "process"])
@pytest.mark.parametrize("workers", [1, 4])
def test_attempted_set_is_independent_of_workers(tmp_path, executor, workers):
    """THE core determinism test (spec §1.4). Every unit is attempted at every `workers`, under BOTH
    executors — so `workers` can no longer decide which of the caller's side effects happened."""
    marker_dir = tmp_path / f"{executor}-{workers}"
    marker_dir.mkdir()
    items = [(str(marker_dir), i) for i in range(8)]
    results, failures = _run_all(_touch_marker, items, workers, executor)
    assert sorted(int(p.stem) for p in marker_dir.glob("*.done")) == list(range(8))
    assert [f.index for f in failures] == [3]
    assert results == [0, 10, 20, None, 40, 50, 60, 70]


def test_failures_are_ordered_by_index(tmp_path):
    """as_completed yields in COMPLETION order, so without the sort the failure list would be
    nondeterministic even though `results` is not."""

    def flaky(i: int) -> int:
        if i in (0, 5):
            raise ValueError(f"bad {i}")
        return i

    _, failures = _run_all(flaky, list(range(8)), 4, "thread")
    assert [f.index for f in failures] == [0, 5]


def test_run_all_does_not_raise_for_unit_failures():
    def always_bad(i: int) -> int:
        raise RuntimeError(f"bad {i}")

    results, failures = _run_all(always_bad, [1, 2, 3], 2, "thread")
    assert results == [None, None, None]
    assert len(failures) == 3
    assert all(isinstance(f.exception, RuntimeError) for f in failures)


def test_broken_pool_propagates_instead_of_becoming_unit_failures():
    """A dead pool voids the attempted-every-unit guarantee, so it must NOT be reported as N
    independent unit failures. Assert on the EXCEPTION TYPE ONLY — how much work completed before the
    pool died is timing-dependent (spec §1.7.2)."""
    with pytest.raises(concurrent.futures.BrokenExecutor):
        _run_all(_suicide, list(range(6)), 4, "process")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_parallel.py -v`
Expected: FAIL at collection — `ImportError: cannot import name '_run_all'`

- [ ] **Step 3: Write minimal implementation**

Add to `ruthless/parallel.py` imports: `from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, ThreadPoolExecutor, as_completed`.
Add `_run_all` above `map_work_units`:

```python
def _run_all(
    fn: Callable[[T], R], items: Sequence[T], workers: int, executor: Literal["thread", "process"]
) -> tuple[list[R | None], list[UnitFailure]]:
    """Attempt EVERY unit. Never raises for a unit failure; `failures` is sorted by index.

    Attempting everything unconditionally is what makes `workers` stop affecting which units ran — see
    the module docstring and spec §1.4. `BrokenExecutor` is the one exception that propagates."""
    n = len(items)
    results: list[R | None] = [None] * n
    failures: list[UnitFailure] = []
    if workers <= 1 or n <= 1:
        for i, x in enumerate(items):
            try:
                results[i] = fn(x)
            except Exception as exc:  # noqa: BLE001 - per-unit isolation IS this function's contract
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
            except Exception as exc:  # noqa: BLE001 - as above
                failures.append(UnitFailure(index=i, exception=exc))
    failures.sort(key=lambda f: f.index)  # as_completed order is nondeterministic; index order is not
    return results, failures
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_parallel.py -v`
Expected: PASS — 12 tests. The `process` parametrisations are slower (pool spin-up); that is expected.

If `test_broken_pool_propagates_instead_of_becoming_unit_failures` reports a `RuntimeError` that is not
a `BrokenExecutor`, do **not** loosen the assertion — re-verify with
`python -c "import concurrent.futures as cf; print(cf.BrokenExecutor.__mro__)"` and check that `_suicide`
is module-level and reachable by import.

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check ruthless tests && uv run ruff format ruthless tests && uv run pyright`
Expected: clean. The two `noqa: BLE001` comments are required and carry a reason — do not remove them.

---

## Task 3: Public `map_work_units` with `on_error`, docstrings, CHANGELOG

**Files:**
- Modify: `ruthless/parallel.py` (replace the body of `map_work_units`, lines 17-42 of the original)
- Modify: `CHANGELOG.md` (insert a new `## [Unreleased]` above `## [0.2.1]` at line 8)
- Test: `tests/test_parallel.py`

**Interfaces:**
- Consumes: `_run_all` (Task 2), `UnitFailure` + `WorkUnitMapError` (Task 1)
- Produces: `map_work_units(fn, items, *, workers=4, executor="thread", on_error="raise")` — two `@overload`s; `on_error="raise"` → `list[R]`, `on_error="collect"` → `tuple[list[R | None], list[UnitFailure]]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_parallel.py`:

```python
def _flaky(i: int) -> int:
    if i == 3:
        raise ValueError(f"unit {i} is bad")
    return i * 10


def test_raise_path_aggregates_every_failure():
    def two_bad(i: int) -> int:
        if i in (1, 4):
            raise ValueError(f"bad {i}")
        return i

    with pytest.raises(WorkUnitMapError) as ei:
        map_work_units(two_bad, list(range(6)), workers=4)
    assert [f.index for f in ei.value.failures] == [1, 4]
    assert "2/6 work-units failed" in str(ei.value)


def test_raise_path_carries_partial_results():
    """Before this change every completed result was discarded and unrecoverable (spec §1.1)."""
    with pytest.raises(WorkUnitMapError) as ei:
        map_work_units(_flaky, list(range(6)), workers=4)
    assert ei.value.results == [0, 10, 20, None, 40, 50]


def test_original_exception_is_recoverable():
    with pytest.raises(WorkUnitMapError) as ei:
        map_work_units(_flaky, list(range(6)), workers=4)
    original = ei.value.failures[0].exception
    assert isinstance(original, ValueError) and "unit 3 is bad" in str(original)
    assert ei.value.__cause__ is original  # chained, so the traceback stays useful


def test_collect_returns_aligned_results_and_failures():
    results, failures = map_work_units(_flaky, list(range(6)), workers=4, on_error="collect")
    assert results == [0, 10, 20, None, 40, 50]
    assert [f.index for f in failures] == [3]


def test_collect_with_no_failures_returns_empty_failures():
    results, failures = map_work_units(_square, [1, 2, 3], workers=2, on_error="collect")
    assert results == [1, 4, 9]
    assert failures == []


def test_collect_path_can_still_raise_on_pool_death():
    """F3: the `collect` return type invites 'never raises'. A dead pool still propagates, and that is
    the failure mode a collect caller is least prepared for. Exception TYPE only — see §1.7.2."""
    with pytest.raises(concurrent.futures.BrokenExecutor) as ei:
        map_work_units(_suicide, list(range(6)), workers=4, executor="process", on_error="collect")
    assert not isinstance(ei.value, WorkUnitMapError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_parallel.py -v`
Expected: the 6 new tests FAIL — `TypeError: map_work_units() got an unexpected keyword argument 'on_error'`, and the raise-path tests fail with a bare `ValueError` rather than `WorkUnitMapError`.

- [ ] **Step 3: Write minimal implementation**

Add `cast` and `overload` to the `typing` import. Replace the whole existing `map_work_units` definition:

```python
@overload
def map_work_units(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    workers: int = ...,
    executor: Literal["thread", "process"] = ...,
    on_error: Literal["raise"] = ...,
) -> list[R]: ...
@overload
def map_work_units(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    workers: int = ...,
    executor: Literal["thread", "process"] = ...,
    on_error: Literal["collect"],
) -> tuple[list[R | None], list[UnitFailure]]: ...
def map_work_units(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    workers: int = 4,
    executor: Literal["thread", "process"] = "thread",
    on_error: Literal["raise", "collect"] = "raise",
) -> list[R] | tuple[list[R | None], list[UnitFailure]]:
    """Map ``fn`` over ``items`` in parallel, preserving input order.

    EVERY unit is always attempted, at every ``workers`` value and under both executors. That is
    deliberate: work units are consumer code carrying consumer side effects, so a ``workers`` value that
    changed *which* units ran would let a performance knob decide which of the caller's writes happened.

    Cost of that guarantee: a systematic failure now costs a full pass. The serial path used to
    short-circuit at the first bad unit, which is what you want when debugging a shared root cause; it no
    longer does.

    GIL caveat: the default ``executor="thread"`` only scales for work that releases the GIL
    (numpy/pandas/IO). For CPU-bound pure-Python work-units, pass ``executor="process"`` (note the
    usual process-pool constraints — ``fn`` and ``items`` must be picklable).

    Args:
        fn: Callable applied to each item.
        items: Input sequence.
        workers: Max parallel workers (``<= 1`` runs serially). Affects speed only, never which units run.
        executor: ``"thread"`` (default, GIL-bound) or ``"process"`` (CPU-bound).
        on_error: ``"raise"`` (default) returns ``list[R]`` and raises `WorkUnitMapError` if any unit
            failed — the error carries every failure AND the partial results. ``"collect"`` returns
            ``(results, failures)`` with ``None`` in each failed slot; it raises only if the pool itself
            dies (`concurrent.futures.BrokenExecutor`), because that voids the attempted-every-unit
            guarantee and so cannot be reported as a per-unit failure. Unit failures are returned, never
            raised.

    Raises:
        WorkUnitMapError: ``on_error="raise"`` and at least one unit failed.
        concurrent.futures.BrokenExecutor: the pool died (either ``on_error`` value)."""
    results, failures = _run_all(fn, items, workers, executor)
    if on_error == "collect":
        return results, failures
    if failures:
        raise WorkUnitMapError(failures, results, len(items)) from failures[0].exception
    return cast("list[R]", results)
```

Also update the **module** docstring's last paragraph to name the new contract:

```python
"""Optional intra-objective parallel map over work-units. NOT the candidate-dispatch path (that is
the backend). A consumer's Objective may call this internally.

GIL caveat: the default "thread" executor only scales for work that releases the GIL
(numpy/pandas/IO). For CPU-bound pure-Python work-units, pass executor="process".

Failure contract: every unit is ALWAYS attempted, so `workers` never changes which units ran. Unit
failures are aggregated into a `WorkUnitMapError` (default) or returned via `on_error="collect"`; a
dead pool propagates `BrokenExecutor` unwrapped."""
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -v`
Expected: PASS — **baseline + 16 = 174 tests**. (`test_parallel.py`'s *file* total is 18, but 2 of those are
the pre-existing tests already inside the 158 baseline — do not add 18 to 158.) Confirm the two original
`test_parallel.py` tests are byte-identical to `git show HEAD:tests/test_parallel.py` for those lines.

- [ ] **Step 5: Add the CHANGELOG entry**

Insert above `## [0.2.1] - 2026-05-30` in `CHANGELOG.md` (no `[Unreleased]` section exists yet — create it):

```markdown
## [Unreleased]

### Changed (BREAKING)
- `ruthless.parallel.map_work_units` now has a real error model. Previously it raised the first unit
  exception by input order, **discarded every completed result**, and the set of units actually attempted
  depended on `workers` — a documented performance knob silently deciding which of the caller's side
  effects happened. Under a parallel executor it also could not fail fast at all: `shutdown(wait=True)`
  meant the exception surfaced only after the whole map finished (measured: a fault at 0.01s surfaced at
  2.03s with 7 of 8 units run and all results thrown away).
  - Every unit is now **always attempted**, at every `workers` value and under both executors.
  - Unit failures aggregate into a new `WorkUnitMapError` (a sibling of `TransientEvaluationError` /
    `FatalEvaluationError` under `OptimizationError`, so `BackendPool` can never retry it) carrying
    every `UnitFailure` **and** the partial results.
  - New `on_error="collect"` returns `(results, failures)` instead of raising, with `None` in each
    failed slot. A dead pool still propagates `concurrent.futures.BrokenExecutor` unwrapped.
  - **Migration:** replace `except ValueError` (or whatever your unit raised) around `map_work_units`
    with `from ruthless.parallel import WorkUnitMapError` / `except WorkUnitMapError` and read
    `exc.failures[i].exception`, or switch to `on_error="collect"`. Note a systematic failure now costs a
    full pass rather than short-circuiting.
```

**Deliberate decision, flagged for review:** `UnitFailure` and `WorkUnitMapError` are **not** added to
`ruthless.__all__`. `map_work_units` itself is not exported (spec §1.2), so a consumer already imports from
`ruthless.parallel`; exporting only the error types would be incoherent. Adding them would also fail
`tests/test_public_api.py::test_all_is_declared_and_complete`, which pins the surface exactly — so if a
reviewer wants them public, `_EXPECTED_PUBLIC` must be updated in the same change and `map_work_units`
should probably be promoted with them.

- [ ] **Step 6: Run the full gate**

```bash
uv run ruff check ruthless tests
uv run ruff format --check ruthless tests
uv run pyright
uv run lint-imports
uv run pytest -v
```
Expected: all five green, `lint-imports` reports 3 contracts kept.

**Checkpoint — do NOT commit.** Part 1 is complete and green. Leave the changes staged-or-unstaged in the
working tree and continue to Task 4; the single commit happens in Task 9.

---

# PART 2 — §2 + §3 fingerprint primitive and evolve migration *(no commit at the end)*

## Task 4: `ruthless/_fingerprint.py` — `_tag`, `_canon`, `fingerprint`

**Files:**
- Create: `ruthless/_fingerprint.py`
- Modify: `.importlinter` (add one line to `core-isolation` `source_modules`, lines 9-25)
- Test: Create `tests/test_fingerprint.py`

**Interfaces:**
- Consumes: nothing (stdlib only in this task)
- Produces:
  - `fingerprint(payload: Mapping[str, object], *, length: int = 16) -> str`
  - `_tag(value: object) -> object` and `_canon(value: object) -> str` (module-private; tested via `fingerprint`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fingerprint.py`. **Note the lowercase test names** — ruff `N802` rejects uppercase in
function names and tests get no exemption.

```python
"""Tests for the private core cache-identity primitive (spec §2.3, §3).

Every collision pair here was measured against the pre-fix implementation; they are regression tests,
not hypotheticals."""

import pytest

from ruthless._fingerprint import fingerprint


def test_fingerprint_is_deterministic():
    payload = {"epochs": 5, "seed": 42}
    assert fingerprint(payload) == fingerprint(payload) == fingerprint(dict(payload))


def test_fingerprint_length_is_configurable():
    assert len(fingerprint({"a": 1})) == 16
    assert len(fingerprint({"a": 1}, length=8)) == 8


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ({"k": 1}, {"k": "1"}),
        ({"k": 1}, {"k": 1.0}),
        ({"k": 1}, {"k": True}),
        ({"k": None}, {"k": "None"}),
    ],
)
def test_type_tags_prevent_cross_type_collision(a, b):
    assert fingerprint(a) != fingerprint(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ({"cfg": {1: "x"}}, {"cfg": {"1": "x"}}),
        ({"p": {1: 0.5, 2: 0.7}}, {"p": {"1": 0.5, "2": 0.7}}),
        ({"cfg": {1.0: "x"}}, {"cfg": {"1.0": "x"}}),
        ({"cfg": {True: "x"}}, {"cfg": {1: "x"}}),
    ],
)
def test_nested_mapping_keys_are_type_tagged(a, b):
    """F1 regression. The pre-fix code used a bare `str(k)`, which collided all four of these. The
    last pair passed pre-fix only by the accident that `str(True) == "True"` — it must now hold by
    construction."""
    assert fingerprint(a) != fingerprint(b)


def test_separator_collision_is_impossible():
    """The §2.2 regression: the old `f"{a}:{b}"` scheme collided these two."""
    assert fingerprint({"a": "1:2", "b": "3"}) != fingerprint({"a": "1", "b": "2:3"})


def test_key_order_does_not_change_digest():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    assert fingerprint({"c": {"a": 1, "b": 2}}) == fingerprint({"c": {"b": 2, "a": 1}})


def test_nested_containers_are_supported():
    assert fingerprint({"k": [1, 2]}) != fingerprint({"k": (1, 2)})
    assert fingerprint({"k": {1, 2}}) != fingerprint({"k": {1, 3}})
    assert fingerprint({"k": {2, 1}}) == fingerprint({"k": {1, 2}})  # sets are order-insensitive
    assert fingerprint({"k": {}}) != fingerprint({"k": []})


def test_unsupported_value_raises_type_error():
    """Fail-closed. A `str()` fallback is exactly how two distinct objects acquire one digest."""
    with pytest.raises(TypeError, match="unsupported type 'object'"):
        fingerprint({"k": object()})


def test_unsupported_key_raises_type_error():
    """Falls out of routing keys through _canon -> _tag. Claimed so a refactor cannot lose it."""
    with pytest.raises(TypeError, match="unsupported type 'object'"):
        fingerprint({"k": {object(): 1}})


def test_equal_but_distinct_digest_cases_are_deliberate():
    """Spec §2.3 consequences 1 and 2: these pairs compare EQUAL in Python but digest differently. That
    is the safe direction — an unnecessary cache MISS, never a stale HIT."""
    assert {"k": -0.0} == {"k": 0.0}
    assert fingerprint({"k": -0.0}) != fingerprint({"k": 0.0})
    assert {"cfg": {True: "x"}} == {"cfg": {1: "x"}}
    assert fingerprint({"cfg": {True: "x"}}) != fingerprint({"cfg": {1: "x"}})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_fingerprint.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'ruthless._fingerprint'`

- [ ] **Step 3: Write minimal implementation**

Create `ruthless/_fingerprint.py`:

```python
"""Private core cache-identity primitive: a deterministic, collision-resistant digest over declared
inputs, plus a model-scoped wrapper whose invalidation scope is a declared EXCLUSION set.

Private (`_`-prefixed, absent from `ruthless.__all__`) for the same reason as `_logging` and `_io`: it is
shared across the core and the strategies without committing a `1.0` public surface. Promotion to a
public `fingerprint` module stays purely additive if a second real caller appears.

Existing callers: `strategies/evolve_/strategy.py` (seed-result cache identity)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


def _tag(value: object) -> object:
    """Type-tagged, JSON-serialisable form of `value`. Structural, so no separator can collide."""
    if isinstance(value, bool):  # MUST precede int - isinstance(True, int) is True
        return ["bool", value]
    if isinstance(value, int):
        return ["int", value]
    if isinstance(value, float):
        return ["float", repr(value)]  # repr round-trips; keeps nan/inf/-0.0 distinguishable
    if isinstance(value, str):
        return ["str", value]
    if value is None:
        return ["none", None]
    if isinstance(value, Mapping):
        # Keys go through _canon too: a bare str(k) collides {1: x} with {"1": x}.
        return ["map", sorted((_canon(k), _tag(v)) for k, v in value.items())]
    if isinstance(value, (list, tuple)):
        return ["list" if isinstance(value, list) else "tuple", [_tag(v) for v in value]]
    if isinstance(value, (set, frozenset)):
        return ["set", sorted(_canon(v) for v in value)]
    raise TypeError(f"fingerprint: unsupported type {type(value).__name__!r}; extend _tag deliberately")


def _canon(value: object) -> str:
    """The single canonicalisation path - used by `fingerprint`, by mapping keys, and by set members, so
    no two positions can disagree about how a value serialises."""
    return json.dumps(_tag(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(payload: Mapping[str, object], *, length: int = 16) -> str:
    """Deterministic, collision-resistant hex digest over a mapping of declared inputs.

    Type-tagged in both the value and the key position; structural rather than concatenated;
    order-insensitive; and fail-closed on an unsupported type (raising rather than falling back to
    `str()`, which is exactly how two distinct objects acquire one digest).

    Three deliberate consequences, all erring toward an unnecessary cache MISS rather than a stale HIT:
    `-0.0` and `0.0` digest differently despite comparing equal; two mappings that compare equal can
    digest differently (`{True: "x"} == {1: "x"}` in Python, but the keys tag differently); and
    extending `_tag` to a new type is an explicit change with a test rather than an accident."""
    return hashlib.sha256(_canon(dict(payload)).encode("utf-8")).hexdigest()[:length]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_fingerprint.py -v`
Expected: PASS — **16 tests** (8 plain + two 4-case parametrisations).

- [ ] **Step 5: Register the module with import-linter**

In `.importlinter`, add `ruthless._fingerprint` to `core-isolation`'s `source_modules`, keeping the list
alphabetical-ish as it already is — insert immediately after line 9's `ruthless._io`... actually **before**
it, since `_fingerprint` sorts first:

```ini
source_modules =
    ruthless._fingerprint
    ruthless._io
    ruthless._logging
    ruthless.errors
```

- [ ] **Step 6: Run the gate**

Run: `uv run ruff check ruthless tests && uv run ruff format --check ruthless tests && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: all green; `lint-imports` reports **3 contracts kept** and now lists `ruthless._fingerprint`.

---

## Task 5: `fingerprint_model` — exclusion-set invalidation scope

**Files:**
- Modify: `ruthless/_fingerprint.py`
- Test: `tests/test_fingerprint.py`

**Interfaces:**
- Consumes: `fingerprint` (Task 4), `pydantic.BaseModel`
- Produces: `fingerprint_model(model: BaseModel, *, exclude: frozenset[str] = frozenset(), length: int = 16) -> str`; raises `ValueError` if `exclude` names a field the model lacks

- [ ] **Step 1: Write the failing tests**

**Add these two imports at the TOP of `tests/test_fingerprint.py`** (not before the class — `E402`):

```python
from pydantic import BaseModel

from ruthless._fingerprint import fingerprint_model
```

Then append the rest:

```python
class _Cfg(BaseModel):
    epochs: int = 5
    timeout_seconds: int = 900
    seed: int = 42


class _CfgPlusOne(BaseModel):
    """_Cfg with ONE field added - the scenario §3's fail-closed design exists for."""

    epochs: int = 5
    timeout_seconds: int = 900
    seed: int = 42
    learning_rate: float = 0.01


def test_fingerprint_model_is_deterministic():
    assert fingerprint_model(_Cfg()) == fingerprint_model(_Cfg())


def test_included_field_changes_digest():
    assert fingerprint_model(_Cfg(epochs=5)) != fingerprint_model(_Cfg(epochs=6))
    assert fingerprint_model(_Cfg(seed=1)) != fingerprint_model(_Cfg(seed=2))


def test_excluded_field_does_not_change_digest():
    ex = frozenset({"timeout_seconds"})
    assert fingerprint_model(_Cfg(timeout_seconds=1), exclude=ex) == fingerprint_model(
        _Cfg(timeout_seconds=999), exclude=ex
    )


def test_excluding_a_field_changes_the_digest_of_the_same_model():
    """Sanity: the exclusion is actually applied, not silently ignored."""
    assert fingerprint_model(_Cfg()) != fingerprint_model(_Cfg(), exclude=frozenset({"timeout_seconds"}))


def test_new_model_field_changes_digest():
    """THE §3 contract. A field added later is INCLUDED by default, so the worst case of forgetting to
    revisit an exclusion list is an unnecessary recompute (safe), never a stale reuse (wrong)."""
    assert fingerprint_model(_Cfg()) != fingerprint_model(_CfgPlusOne())


def test_fingerprint_model_rejects_unknown_exclusion():
    """Closes the stale-exclusion-NAME gap: rename or delete a field and an inclusion-list design fails
    silently, whereas this raises."""
    with pytest.raises(ValueError, match=r"non-existent field\(s\) \['timeout'\]"):
        fingerprint_model(_Cfg(), exclude=frozenset({"timeout"}))


def test_fingerprint_model_reports_known_fields_in_the_error():
    with pytest.raises(ValueError, match="known fields:"):
        fingerprint_model(_Cfg(), exclude=frozenset({"nope"}))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_fingerprint.py -v`
Expected: FAIL — `ImportError: cannot import name 'fingerprint_model'`

- [ ] **Step 3: Write minimal implementation**

Append to `ruthless/_fingerprint.py` (and add `from pydantic import BaseModel` to the imports):

```python
def fingerprint_model(model: BaseModel, *, exclude: frozenset[str] = frozenset(), length: int = 16) -> str:
    """Fingerprint ALL of `model`'s fields except those named in `exclude`.

    Declare what determines the cached artifact's CONTENT, not what CONSUMES it. Anything recomputed
    downstream on every run is excluded by construction.

    Fail-closed: a field ADDED to the model later is INCLUDED unless someone explicitly excludes it, so
    forgetting to revisit this call costs a recompute, never a stale reuse. An inclusion list would have
    the opposite (silent, wrong) failure direction.

    Raises ValueError if `exclude` names a field the model does not have - otherwise a renamed or deleted
    field leaves a silently-ineffective exclusion behind.

    LIMITATION, stated deliberately: this checks that exclusions EXIST, not that they are CORRECT. An
    author can exclude a field that does matter and get a fingerprint that never changes. This converts a
    silent omission into a visible, reviewable, wrong line - it does not prove the scope. Pin the
    reasoning behind each exclusion with a test and cross-reference it from the exclusion comment."""
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_fingerprint.py -v`
Expected: PASS — **23 tests** (16 from Task 4 + 7 here).

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check ruthless tests && uv run ruff format ruthless tests && uv run pyright`
Expected: clean.

---

## Task 6: Migrate evolve's `_eval_fingerprint`, pin the exclusion's reasoning

**Files:**
- Modify: `ruthless/strategies/evolve_/strategy.py` — imports (`:18` drop `hashlib`, add `_fingerprint`), replace `_eval_fingerprint` (`:130-132`)
- Modify: `CHANGELOG.md` (add to `[Unreleased]`)
- Test: `tests/strategies/evolve/test_evolve_strategy.py`

**Interfaces:**
- Consumes: `fingerprint_model` (Task 5)
- Produces: `_eval_fingerprint(cfg: EvolveConfig) -> str` — same signature as today, so
  `test_evolve_strategy.py:134` keeps working; `_SEED_CACHE_EXCLUDE: frozenset[str]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/strategies/evolve/test_evolve_strategy.py` (add `from ruthless.wire import worst_score_metrics` to the imports):

```python
def test_eval_fingerprint_tracks_epochs_and_seed_but_not_timeout(seed_dir):
    """Pins evolve's DECLARED cache-identity scope (spec §3)."""
    base = strat._eval_fingerprint(_cfg(seed_dir))
    assert strat._eval_fingerprint(_cfg(seed_dir, evaluation={"epochs": 99, "seed": 7})) != base
    assert strat._eval_fingerprint(_cfg(seed_dir, evaluation={"epochs": 3, "seed": 99})) != base
    # timeout_seconds is an infra budget, not a determinant of a seed's metrics -> excluded.
    assert strat._eval_fingerprint(_cfg(seed_dir, evaluation={"epochs": 3, "seed": 7, "timeout_seconds": 1})) == base


def test_a_zero_score_seed_result_is_never_cache_readable(seed_dir, tmp_path):
    """Load-bearing for _SEED_CACHE_EXCLUDE's `timeout_seconds` entry (spec §3.2). A truncated run maps
    to the worst-score sentinel (combined_score=0), is WRITTEN to the seed-results dir like any other
    result (_eval_one writes unconditionally), and this read filter is the ONLY thing that stops it being
    reused. Relax it and the timeout exclusion becomes silently unsafe."""
    cfg = _cfg(seed_dir)
    fp = strat._eval_fingerprint(cfg)
    results_dir = tmp_path / "seed_results"
    results_dir.mkdir(parents=True)
    (results_dir / "seed0.json").write_text(
        json.dumps({"program": "seed0.py", "fingerprint": fp, "metrics": worst_score_metrics()})
    )
    cached = strat._load_cached_seeds(results_dir, [seed_dir / "seed0.py"], fp)
    assert cached == {}, "a combined_score=0 sentinel must never be readable from the seed cache"


def test_a_positive_score_seed_result_is_cache_readable(seed_dir, tmp_path):
    """The control for the test above: the filter rejects sentinels, not everything."""
    cfg = _cfg(seed_dir)
    fp = strat._eval_fingerprint(cfg)
    results_dir = tmp_path / "seed_results"
    results_dir.mkdir(parents=True)
    (results_dir / "seed0.json").write_text(
        json.dumps({"program": "seed0.py", "fingerprint": fp, "metrics": {"combined_score": 0.5}})
    )
    assert strat._load_cached_seeds(results_dir, [seed_dir / "seed0.py"], fp) == {
        "seed0": {"combined_score": 0.5}
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/strategies/evolve/test_evolve_strategy.py -v`
Expected: `test_eval_fingerprint_tracks_epochs_and_seed_but_not_timeout` **passes already** (today's
f-string covers epochs+seed and ignores timeout) — that is fine and expected; it is a
regression guard for the migration, not a red test. The two `_load_cached_seeds` tests are new
behaviour-pinning tests and should also pass immediately. **This task's red signal comes in Step 4**:
after the swap, the digest value changes, and any test asserting a hardcoded digest would break. There
are none, which is what makes the migration safe.

**Why that is not a coverage gap.** The §3 fail-closed contract *does* have a red phase — it is
`test_new_model_field_changes_digest` in Task 5, which cannot pass before `fingerprint_model` exists. Task 6
is a pure delegation swap, and its guard
(`test_eval_fingerprint_tracks_epochs_and_seed_but_not_timeout`) is red for the failure that actually
threatens it: a botched migration passing the wrong `exclude`, or `exclude=frozenset()`. So the coverage sits
in the task where the behaviour is introduced, and Task 6's guard covers the mistake Task 6 can make.

- [ ] **Step 3: Write the implementation**

In `ruthless/strategies/evolve_/strategy.py`: remove `import hashlib` (line 18 — verify with
`uv run ruff check` that nothing else uses it) and add to the `ruthless` imports:

```python
from ruthless._fingerprint import fingerprint_model
```

Replace lines 130-132 entirely:

```python
# EvalConfig fields deliberately EXCLUDED from seed-cache identity, with the reason for each.
# Rule: declare what determines the cached artifact's CONTENT, not what CONSUMES it.
_SEED_CACHE_EXCLUDE = frozenset(
    {
        # An infra budget, not a determinant of a seed's metrics. A truncated run maps to the worst-score
        # sentinel (combined_score=0) and is WRITTEN like any other result - _eval_one writes
        # unconditionally - but is never READ BACK, because _load_cached_seeds accepts only
        # combined_score > 0.0. That read filter is the ONLY thing making this exclusion safe; it is
        # pinned by test_a_zero_score_seed_result_is_never_cache_readable. Relax it and this exclusion
        # becomes silently unsafe.
        "timeout_seconds",
    }
)


def _eval_fingerprint(cfg: EvolveConfig) -> str:
    """Deterministic identity of the eval params that determine seed-result CONTENT.

    Delegates to the shared core primitive, which covers EVERY EvalConfig field except
    `_SEED_CACHE_EXCLUDE`, so a new field is picked up automatically (fail-closed - see
    `ruthless._fingerprint.fingerprint_model`). The policy of WHAT evolve excludes stays here; the
    hashing lives in core."""
    return fingerprint_model(cfg.evaluation, exclude=_SEED_CACHE_EXCLUDE)
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -v`
Expected: PASS — **200 tests** (158 baseline + 16 from Part 1 + 23 fingerprint + 3 evolve).
`test_run_seed_cache_resume_skips_cached` must still pass: it derives its fingerprint from
`strat._eval_fingerprint(cfg)` rather than hardcoding one, so the changed digest value is transparent to it.
Nothing in `tests/` hardcodes a 16-hex digest, so the digest change breaks no assertion.

**Running-total reference** (parametrised cases counted as instances — if a run disagrees, recount before
assuming something is missing): baseline **158** → after Task 3 **174** → after Task 5 **197** → after
Task 6 **200** → after Task 7 **211** → after Task 8 **215**.

*(Updated during execution: Task 8 gained `test_summary_md_handles_empty_provenance` to cover the
`or ["- (none)"]` branch, so 214 → 215. Recorded here per the instruction below rather than left stale.)*

These totals are derived from the test listings in this plan. If you add a test while executing, update both
the per-task expected count **and** this table — a stale count is worse than no count, because it looks
authoritative.

- [ ] **Step 5: Add the CHANGELOG entry**

Add to the existing `## [Unreleased]` section in `CHANGELOG.md`:

```markdown
### Added
- Private core cache-identity primitive (`ruthless._fingerprint`): a type-tagged, structural,
  order-insensitive, fail-closed digest over declared inputs, plus `fingerprint_model(model, exclude=...)`
  whose invalidation scope is a declared EXCLUSION set. A field added to a model later is included by
  default, so the failure mode of forgetting to revisit an exclusion is an unnecessary cache miss
  (recompute) rather than a stale hit (wrong). Naming a non-existent field in `exclude` raises, closing
  the renamed-field gap. Private and absent from `ruthless.__all__` — no public API commitment.

### Changed
- `EvolveStrategy`'s seed-result cache fingerprint now delegates to `ruthless._fingerprint`. The set of
  inputs it covers is unchanged (`epochs` + `seed`; `timeout_seconds` remains excluded, and that
  exclusion's load-bearing read filter is now pinned by a test), but the **digest value changes**, so
  existing on-disk seed caches miss once and recompute. Benign, and in the fail-closed direction. The old
  hand-rolled `sha256(f"{epochs}:{seed}")` used untagged string concatenation over a `:` separator, which
  was collision-free only because both fields are ints.
```

- [ ] **Step 6: Run the gate**

```bash
uv run ruff check ruthless tests
uv run ruff format --check ruthless tests
uv run pyright
uv run lint-imports
uv run pytest -v
```
Expected: all five green. `lint-imports` must still report **3 contracts kept** —
`evolve_/strategy.py` importing `ruthless._fingerprint` is the allowed strategy→core direction.

**Checkpoint — do NOT commit.** Continue to Task 7.

---

# PART 3 — §4 run provenance *(no commit at the end)*

Spec §4 introduces `subprocess` and a git dependency into a core that today depends only on pydantic +
numpy + pyyaml, plus a new failure surface inside `run()`. The spec and both reviews concluded it should
be taken now rather than deferred (§4.2: the change is additive and cheap, but every artifact produced
before it lands is permanently unattributable, so deferring grows the un-attributed back-catalogue rather
than preserving optionality).

It was originally scoped as its own commit with a review gate before starting. Under the single-commit
convention that gate is gone, so **the scope decision is made up front instead**: Part 3 is in. If it should
be dropped, cut Tasks 7 and 8 plus their two CHANGELOG entries — Parts 1-2 have no dependency on them.

## Task 7: `ruthless/_provenance.py` — `code_identity()`

**Files:**
- Create: `ruthless/_provenance.py`
- Modify: `.importlinter` (add `ruthless._provenance`)
- Test: Create `tests/test_provenance.py`

**Interfaces:**
- Consumes: `ruthless.__version__`
- Produces: `code_identity(*, repo_root: Path | None = None) -> dict[str, Any]` returning keys
  `ruthless_version: str`, `ruthless_git_commit: str | None`, `ruthless_git_state: Literal["clean","dirty","unknown"]`;
  and `_repo_tracks_module(module_file: Path) -> bool`

> **P1 — read this before writing any code.** An earlier draft of this task resolved the repo from
> `Path(__file__)` and claimed *"a pip-installed ruthless has no repo and correctly reports unknown"*. **That
> is false for the most common install layout, and it was measured false.** A wheel installed into a
> project-local venv sits at `<consumer-repo>/.venv/Lib/site-packages/ruthless/`, which is **inside the
> consumer's git repo** — so `git rev-parse HEAD` from there succeeds and returns *the consumer's commit*:
>
> ```
> consumer repo HEAD                : dc8d75e9436072aa511a3cf5b2ca451c2f490275
> HEAD as seen from installed pkg   : dc8d75e9436072aa511a3cf5b2ca451c2f490275   <- identical
> --show-toplevel from installed pkg: .../consumer-repo
> is the venv gitignored?           : .gitignore:1:.venv/    <- yes, and it makes no difference
> ```
>
> Being gitignored does not help: git walks up looking for `.git` and never consults ignore rules to decide
> whether it is in a repo. A project-local venv is the default for uv, Poetry and `python -m venv`, so this
> is the normal case, not an edge case.
>
> This is **worse** than a CWD-based lookup, because the `ruthless_` key prefix actively asserts the SHA
> describes ruthless's tree — an unprefixed key would merely be vague; this one is specifically false. It is
> precisely the failure the module's own header paragraph exists to prevent.
>
> **Fix: ask git whether the enclosing repo TRACKS this module as source** — `git ls-files --error-unmatch
> <module>` — and apply the check only when `repo_root` was not supplied (so an explicit `repo_root=` stays a
> trusted test seam). A wheel install then reports `"unknown"` with `ruthless_version` as the identity, which
> is the correct outcome and only actually happens once this check is in place.
>
> **Why `ls-files` and not a path comparison.** Plan review round 1 proposed comparing the discovered
> `--show-toplevel` against `<toplevel>/ruthless/_provenance.py`. That works for today's layout but encodes
> an unstated assumption — that the package sits at the repo root — so a move to a `src/` layout would make a
> *legitimate* checkout fail the check. Measured across five layouts:
>
> | layout | want | `ls-files` | path comparison |
> |---|---|---|---|
> | flat source checkout | accept | ✅ | ✅ |
> | `src/` layout checkout | accept | ✅ | ❌ **wrong** |
> | wheel in a consumer venv (P1) | reject | ✅ | ✅ |
> | consumer repo with a decoy top-level `ruthless/` | reject | ✅ | ✅ |
> | no repo at all | reject | ✅ | ✅ |
>
> `ls-files` also needs only **one** git call instead of two (it subsumes "is there a repo"), and it gets two
> edge cases right for the right reason rather than by accident:
>
> - **A consumer who vendors ruthless's source into their own tracked tree gets their SHA** — correct, because
>   their repo genuinely *is* the source of the code being run.
> - **An untracked module in a real checkout reports `"unknown"`** (verified). Semantically right: a file that
>   is not tracked at `HEAD` is not described by `HEAD`'s SHA.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_provenance.py`:

```python
"""Tests for code-identity capture (spec §4.3).

The load-bearing property is NEGATIVE: a bare SHA from a dirty or unknown tree is verifiable-looking
FALSE provenance, which is strictly worse than recording nothing. So `ruthless_git_state` must never
degrade to "clean", and `ruthless_git_commit` must never appear without a state."""

import subprocess

import pytest

from ruthless._provenance import code_identity


def _git(*args: str, cwd) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def clean_repo(tmp_path):
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "t@example.com", cwd=tmp_path)
    _git("config", "user.name", "T", cwd=tmp_path)
    (tmp_path / "f.txt").write_text("hello")
    _git("add", "f.txt", cwd=tmp_path)
    _git("commit", "-m", "init", cwd=tmp_path)
    return tmp_path


def test_clean_repo_reports_clean_and_a_sha(clean_repo):
    ident = code_identity(repo_root=clean_repo)
    assert ident["ruthless_git_state"] == "clean"
    assert isinstance(ident["ruthless_git_commit"], str)
    assert len(ident["ruthless_git_commit"]) == 40


def test_modified_tracked_file_reports_dirty(clean_repo):
    (clean_repo / "f.txt").write_text("changed")
    assert code_identity(repo_root=clean_repo)["ruthless_git_state"] == "dirty"


def test_untracked_file_reports_dirty(clean_repo):
    """`git status --porcelain`, not `git diff --quiet` - the latter misses untracked files."""
    (clean_repo / "new.txt").write_text("x")
    assert code_identity(repo_root=clean_repo)["ruthless_git_state"] == "dirty"


def test_non_repo_reports_unknown_and_never_clean(tmp_path):
    ident = code_identity(repo_root=tmp_path)
    assert ident["ruthless_git_state"] == "unknown"
    assert ident["ruthless_git_commit"] is None


def test_version_is_always_present(tmp_path):
    from ruthless import __version__

    assert code_identity(repo_root=tmp_path)["ruthless_version"] == __version__


def test_a_sha_never_appears_without_a_state(clean_repo, tmp_path):
    for root in (clean_repo, tmp_path):
        ident = code_identity(repo_root=root)
        assert "ruthless_git_state" in ident
        if ident["ruthless_git_commit"] is not None:
            assert ident["ruthless_git_state"] in {"clean", "dirty"}


# --- P1 regression: the failing configuration is "installed INSIDE a repo that is not ruthless's" ---


def _repo_with_module(root, module_rel: str, *, track: bool, gitignore: str = "") -> Path:
    """Build a git repo at `root` containing `module_rel`, tracked or not. Returns the module path."""
    module = root / module_rel
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text("# _provenance\n")
    _git("init", cwd=root)
    _git("config", "user.email", "t@example.com", cwd=root)
    _git("config", "user.name", "T", cwd=root)
    if gitignore:
        (root / ".gitignore").write_text(gitignore)
        _git("add", ".gitignore", cwd=root)
    (root / "README.md").write_text("x\n")
    _git("add", "README.md", cwd=root)
    if track:
        _git("add", "-f", module_rel, cwd=root)
    _git("commit", "-m", "init", cwd=root)
    return module.resolve()


def test_repo_tracks_module_accepts_a_flat_source_checkout(tmp_path):
    module = _repo_with_module(tmp_path, "ruthless/_provenance.py", track=True)
    assert _repo_tracks_module(module) is True


def test_repo_tracks_module_accepts_a_src_layout_checkout(tmp_path):
    """Layout-agnostic by construction. A path comparison against a hardcoded `ruthless/<name>` would
    reject this LEGITIMATE checkout and silently degrade provenance to 'unknown' everywhere."""
    module = _repo_with_module(tmp_path, "src/ruthless/_provenance.py", track=True)
    assert _repo_tracks_module(module) is True


def test_repo_tracks_module_rejects_an_untracked_copy_inside_another_repo(tmp_path):
    """THE measured P1 layout: a wheel in a project-local venv sits inside the CONSUMER's repo, so a bare
    `git rev-parse` succeeds there and returns THEIR commit. Gitignoring the venv does not help."""
    module = _repo_with_module(
        tmp_path, ".venv/Lib/site-packages/ruthless/_provenance.py", track=False, gitignore=".venv/\n"
    )
    assert _repo_tracks_module(module) is False


def test_repo_tracks_module_rejects_a_non_repo(tmp_path):
    module = tmp_path / "ruthless" / "_provenance.py"
    module.parent.mkdir(parents=True)
    module.write_text("")
    assert _repo_tracks_module(module.resolve()) is False


def test_code_identity_reports_unknown_when_the_module_is_not_tracked(clean_repo, monkeypatch):
    """Integration guard for P1, through the real auto-discovery path. Point `_MODULE` at an 'installed'
    copy inside `clean_repo` — a repo with a perfectly good HEAD — and assert the no-argument call refuses
    to claim that repo's commit as ruthless's. Also covers the case a failed git lookup takes."""
    installed = clean_repo / ".venv" / "Lib" / "site-packages" / "ruthless" / "_provenance.py"
    installed.parent.mkdir(parents=True)
    installed.write_text("")
    monkeypatch.setattr(_provenance, "_MODULE", installed.resolve())
    ident = code_identity()
    assert ident["ruthless_git_commit"] is None
    assert ident["ruthless_git_state"] == "unknown"
    assert ident["ruthless_version"]  # version is the identity in this case
```

Extend this file's imports (at the **top**, per P2) with:

```python
from pathlib import Path

from ruthless import _provenance
from ruthless._provenance import _repo_tracks_module, code_identity
```

Also change the existing `_git` helper to return nothing but accept `-f` (it already does — it just forwards
`*args`), and note that `_repo_with_module` reuses it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_provenance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ruthless._provenance'`

- [ ] **Step 3: Write minimal implementation**

Create `ruthless/_provenance.py`:

```python
"""Private core code-identity capture for `Result.provenance`.

THE TRAP THIS EXISTS TO AVOID: `git rev-parse HEAD` returns the same SHA whether or not the working tree
is modified, so a bare SHA stamped on an artifact built from a dirty tree is verifiable-looking FALSE
provenance - strictly worse than recording nothing. Therefore a commit is NEVER reported without a state,
and a missing/failing git NEVER degrades to "clean".

Scope: this identifies RUTHLESS's own tree, not the consumer's objective code - hence the `ruthless_`
key prefix, so a reader cannot mistake it for full run provenance.

The repo is resolved from this file's location AND the enclosing repo must be proved to TRACK this module
as source (`_repo_tracks_module`). The containment check is not belt-and-braces, it is
load-bearing: a wheel installed into a project-local venv lives at
`<consumer-repo>/.venv/Lib/site-packages/ruthless/`, which is INSIDE the consumer's repo, so a bare
`git rev-parse HEAD` from here returns THEIR commit (measured). Being gitignored does not help - git walks
up for `.git` and never consults ignore rules. Without the check, this module would stamp a consumer's SHA
under a key whose prefix asserts it is ruthless's: exactly the verifiable-looking false provenance the
paragraph above exists to prevent.

Expected and correct: a wheel install reports "unknown", with `ruthless_version` carrying the identity. A
source checkout and a `pip install -e` both report a real SHA + state."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from ruthless._logging import get_logger

_log = get_logger("provenance")
_TIMEOUT_S = 5

_MODULE = Path(__file__).resolve()


def _repo_tracks_module(module_file: Path) -> bool:
    """True only if the enclosing git repo TRACKS `module_file` as source.

    Separates "ruthless's own checkout" (including `pip install -e`, where `__file__` still points at the
    source) from "somebody's venv that happens to sit inside their repo". See the module docstring for the
    measured failure this prevents.

    Asking git rather than comparing paths keeps this layout-agnostic - a `src/` layout would break a
    path comparison against a hardcoded package-relative path, in a LEGITIMATE checkout. It also subsumes
    the "is there a repo at all" question, so one git call answers both."""
    return _run_git(["ls-files", "--error-unmatch", str(module_file)], module_file.parent) is not None


def _run_git(args: list[str], repo_root: Path) -> str | None:
    """Stdout of `git <args>` in `repo_root`, or None on ANY failure (absent git, non-repo, timeout)."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        proc = subprocess.run(  # noqa: S603 - `git` resolved via shutil.which; args are literals
            [git, *args], cwd=repo_root, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def code_identity(*, repo_root: Path | None = None) -> dict[str, Any]:
    """Ruthless's own code identity, for merging into `Result.provenance`.

    Returns `ruthless_version`, `ruthless_git_commit` (40-char SHA or None) and `ruthless_git_state`
    ("clean" | "dirty" | "unknown"). "unknown" means the tree could not be established and is as
    untrustworthy as "dirty" - it never means clean."""
    from ruthless import __version__

    ident: dict[str, Any] = {
        "ruthless_version": __version__,
        "ruthless_git_commit": None,
        "ruthless_git_state": "unknown",
    }
    root = repo_root if repo_root is not None else _MODULE.parent
    # An explicit repo_root is a trusted test seam; auto-discovery is not, so it must prove the repo it
    # landed in actually holds ruthless's SOURCE and is not a consumer repo containing an installed copy.
    if repo_root is None and not _repo_tracks_module(_MODULE):
        return ident
    sha = _run_git(["rev-parse", "HEAD"], root)
    if sha is None:
        return ident
    status = _run_git(["status", "--porcelain"], root)  # --porcelain, so untracked files count as dirty
    if status is None:
        _log.warning("provenance_state_unknown", extra={"repo_root": str(root)})
        return ident
    ident["ruthless_git_commit"] = sha.strip()
    ident["ruthless_git_state"] = "dirty" if status.strip() else "clean"
    return ident
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_provenance.py -v`
Expected: PASS — **11 tests** (6 state/version tests + 5 containment tests). **If you added or removed a test
in Step 1, recount this number** — an expected count is a second edit that is easy to miss, and a stale one
sends the next reader hunting for tests that never existed.

Note the six original tests all pass `repo_root=` explicitly, so they exercise the trusted seam and are
unaffected by the containment check. The five new ones cover auto-discovery, which is the path that had the
defect.

If `test_repo_tracks_module_rejects_a_non_repo` ever fails because `tmp_path` sits inside an outer git repo,
that is a real environment difference, not a test bug: on this box `tmp_path` is under
`C:\Users\...\AppData\Local\Temp`, which is not a repo. Do not loosen the assertion — the correct fix is to
make the fixture path genuinely repo-free.

- [ ] **Step 5: Register with import-linter, then run the gate**

Add `ruthless._provenance` to `.importlinter`'s `core-isolation` `source_modules`, then:
```bash
uv run ruff check ruthless tests && uv run ruff format --check ruthless tests && uv run pyright && uv run lint-imports && uv run pytest -q
```

---

## Task 8: Wire provenance into the strategies and the Markdown report

**Files:**
- Modify: `ruthless/strategies/random_/strategy.py:70`
- Modify: `ruthless/strategies/optuna_/strategy.py:122-126`
- Modify: `ruthless/strategies/evolve_/strategy.py:385-389`
- Modify: `ruthless/report.py:48`
- Modify: `CHANGELOG.md`
- Test: `tests/test_report.py` (extend), `tests/strategies/*` (extend)

**Interfaces:**
- Consumes: `code_identity()` (Task 7)
- Produces: every `Result.provenance` carries the three `ruthless_*` keys; `render_summary_md` renders
  provenance as one `- key: value` line per entry

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_report.py`:

```python
def test_summary_md_renders_provenance_one_key_per_line():
    """spec §8.1: a growing one-line dict repr buries `ruthless_git_state`, which is precisely the field
    that must not be buried (a SHA with no state is false provenance). Hyrum's Law is satisfied because
    report.py's own docstring already directs machine consumers to render_json."""
    result = Result(
        best=None,
        history=[],
        provenance={"strategy": "random", "ruthless_git_commit": "a" * 40, "ruthless_git_state": "dirty"},
    )
    md = render_summary_md(result)
    assert "- ruthless_git_state: dirty" in md
    assert f"- ruthless_git_commit: {'a' * 40}" in md
    assert "{'strategy'" not in md  # no bare dict repr


def test_render_json_still_serialises_provenance_as_a_dict():
    """The machine-readable surface is UNCHANGED - that is what makes the Markdown reformat safe."""
    result = Result(best=None, history=[], provenance={"strategy": "random", "ruthless_git_state": "clean"})
    assert json.loads(render_json(result))["provenance"] == {
        "strategy": "random",
        "ruthless_git_state": "clean",
    }
```

Append to `tests/test_random_strategy.py` (note: this file is at the **top level** of `tests/`, not under
`tests/strategies/` — reuse its existing `_cfg` helper and `Quadratic` objective):

```python
def test_result_provenance_carries_code_identity():
    """Captured at RUN time, not render time: render_json may be called later from a different tree."""
    r = RandomSearchStrategy(_cfg(5), seed=42).run(Quadratic(), backend=InProcessBackend())
    assert r.provenance["ruthless_version"]
    assert r.provenance["ruthless_git_state"] in {"clean", "dirty", "unknown"}
    assert r.provenance["strategy"] == "random"  # pre-existing keys survive the spread
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_report.py tests/test_random_strategy.py tests/strategies -v`

`tests/test_random_strategy.py` **must** be named explicitly: `tests/strategies/` contains only `evolve/`
and `optuna_/`, so omitting it silently skips the new strategy test and the red phase never happens.

Expected: FAIL — `KeyError: 'ruthless_version'` from the strategy test, and the Markdown assertions fail
against the bare repr.

- [ ] **Step 3: Write the implementation**

In each of the three strategies, add the import `from ruthless._provenance import code_identity` and spread
it into the existing provenance dict. For `random_/strategy.py:70`:

```python
provenance={"strategy": "random", "seed": self._seed, "direction": cfg.direction.value, **code_identity()},
```

Apply the same `**code_identity()` spread to `optuna_/strategy.py:122` and `evolve_/strategy.py:385`,
keeping each existing key. In `ruthless/report.py`, replace line 48:

```python
    lines += [f"**Trials:** {len(result.history)}", "", "**Provenance:**"]
    lines += [f"- {k}: {v}" for k, v in result.provenance.items()] or ["- (none)"]
```

and extend `render_summary_md`'s docstring to say provenance is rendered one key per line.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -v`
Expected: PASS. Two pre-existing tests were checked against this reformat and both survive it:

- `tests/test_report.py:24` asserts `md.startswith("# ")` and `"random" in md`. Under the reformat
  provenance renders as `- strategy: random`, so `"random" in md` still holds. **Do not modify this test.**
- `tests/test_public_api.py:12-54` pins `ruthless.__all__` exactly. `_provenance` is private and
  `code_identity` is not exported, so the pinned set is unchanged. **Do not add either to `__all__`** —
  that would fail `test_all_is_declared_and_complete`.

Before declaring done, still run `grep -rn "Provenance" tests/` in case a test added between planning and
execution asserts on the old one-line form.

- [ ] **Step 5: Add the CHANGELOG entry, then run the gate**

```markdown
### Added
- `Result.provenance` now carries ruthless's own code identity: `ruthless_version`,
  `ruthless_git_commit` and `ruthless_git_state` (`"clean"` | `"dirty"` | `"unknown"`), captured at run
  time. A commit is never reported without a state, and an absent/failing git reports `"unknown"` rather
  than degrading to `"clean"` — a bare SHA from a dirty tree is verifiable-looking false provenance,
  which is worse than recording nothing. Keys are `ruthless_`-prefixed because this identifies ruthless's
  tree, not the consumer's objective code.

### Changed
- `render_summary_md` renders provenance as one `- key: value` line per entry instead of a single-line
  dict repr, so `ruthless_git_state` stays visible as the dict grows. The machine-readable surface
  (`render_json`) is unchanged; the docstring at `report.py:40` already directs machine consumers there.
```

Then run all five gate commands.

**Checkpoint — do NOT commit.** All three parts are complete. Continue to Task 9.

---

## Task 9: Final review, the single commit, and the PR

- [ ] **Step 1: Run `/final-review`**

The mandatory pre-commit gate (project convention). It also regenerates the C4 diagram at
`docs/c4/architecture.html` — required here, because the core component inventory changed
(`_fingerprint`, and `_provenance` if Commit C landed). Check `docs/c4/architecture.dsl:37`, which
currently describes `parallel` as *"map_work_units — intra-objective thread/process map"*; that
description should mention the failure contract.

- [ ] **Step 2: Confirm the full gate one last time**

```bash
uv run ruff check ruthless tests
uv run ruff format --check ruthless tests
uv run pyright
uv run lint-imports
uv run pytest -v
```

- [ ] **Step 3: Verify the untouchables are untouched**

```bash
git diff main -- tests/test_parallel.py | grep -E "^-" | grep -v "^---"
```
Expected: **no deletions** of the two original order-preservation tests. Also confirm
`test_evolve_strategy.py`'s `test_run_seed_cache_resume_skips_cached` and `tests/test_report.py`'s two tests
are unmodified, and that `ruthless/__init__.py` is untouched (`__all__` must not gain the new names — see
Task 3).

- [ ] **Step 4: Stage everything — code, tests, spec, plan, CHANGELOG, C4**

```bash
git add ruthless tests .importlinter CHANGELOG.md docs
git status --short   # review the full list before committing; nothing unexpected should appear
```

- [ ] **Step 5: The single commit (only after explicit user approval)**

Use a heredoc via the **Bash** tool, not PowerShell — a PowerShell `@'...'@` here-string corrupts multiline
commit text on this box.

```bash
git commit -F - <<'MSG'
feat(parallel,core)!: work-unit error model + cache-identity primitive

Three related changes to surfaces that were inconsistent with the repo's own
stated principles, found while surveying ruthless from a consumer repo.

1. map_work_units had no error model — the only execution surface in the repo
   without one. It raised the first unit exception by input order, discarded
   EVERY completed result, and the set of units actually attempted depended on
   `workers`, a documented performance knob. Under a parallel executor it also
   could not fail fast at all: shutdown(wait=True) meant a fault at 0.01s
   surfaced at 2.03s with 7 of 8 units run and all results thrown away. Every
   unit is now always attempted, failures aggregate into WorkUnitMapError with
   the partial results attached, and on_error="collect" returns them instead.

2. New private core primitive ruthless/_fingerprint.py: type-tagged in both the
   value and the key position, structural rather than concatenated,
   order-insensitive, fail-closed on unsupported types. Replaces evolve's
   hand-rolled sha256(f"{epochs}:{seed}"), whose untagged concatenation was
   collision-free only because both fields happen to be ints.

3. fingerprint_model() makes a cache's invalidation scope a declared EXCLUSION
   set rather than a comment, so a field added to the model later is included by
   default — the failure mode of forgetting becomes an unnecessary recompute,
   not a silent stale hit. Result.provenance now also carries ruthless's own
   code identity, never a SHA without a tree state.

BREAKING: map_work_units raises WorkUnitMapError, not the first unit exception.
Migration in CHANGELOG. Existing evolve seed caches miss once and recompute
(same input set, new digest value) — benign, fail-closed direction.

Spec:   docs/superpowers/specs/2026-07-29-parallel-error-model-and-cache-identity.md
Plan:   docs/superpowers/plans/2026-07-29-parallel-error-model-and-cache-identity-plan.md
Review: two rounds with a second session; F1 (untagged mapping keys) was a
        measured collision in the primitive this change adds, caught in review
        and closed before landing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSMU6x3y9fALYqtZeY897v
MSG
```

- [ ] **Step 6: Push and open the PR (push/PR are not approval-gated; the commit is)**

```bash
git push -u origin feat/parallel-error-model-cache-identity
gh pr create --title "feat(parallel,core)!: work-unit error model + cache-identity primitive" --body-file - <<'BODY'
...
BODY
```

The PR body should carry: the measured §1.1 evidence table (2.03s / 7 units burned / 0 returned), the
BREAKING migration line, the one-time seed-cache invalidation note, and links to the spec and plan. Squash
merge only (repo convention).

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1.5 `UnitFailure` / `WorkUnitMapError` + taxonomy | Task 1 |
| §1.4 attempt-every-unit; §1.5 `_run_all`, `failures.sort`, `BrokenExecutor` | Task 2 |
| §1.5 overloads + `on_error`; §1.4.1 documented cost; F3 wording; §1.6 CHANGELOG BREAKING | Task 3 |
| §1.7 tests 1-9; §1.7.1 F2 both executors via markers; §1.7.2 F4 `os._exit`, type-only assert | Tasks 1-3 |
| §2.3 `fingerprint`/`_tag`/`_canon`; §2.3.1 F1 keys; three consequences; fail-closed keys | Task 4 |
| §2.4 `.importlinter` registration | Tasks 4, 7 |
| §3 `fingerprint_model` exclusion set + unknown-exclusion guard + LIMITATION docstring | Task 5 |
| §2.4 / §3 evolve migration, F4 comment wording, digest-change CHANGELOG | Task 6 |
| §3.1 tests 1-13; §3.2 read-filter test | Tasks 4-6 |
| §4.3 `code_identity`, never-SHA-without-state, `--porcelain`, unknown≠clean, run-time capture | Task 7 |
| §4.3 strategy wiring + §8.1 Markdown reformat | Task 8 |
| §7 acceptance criteria, `/final-review`, C4 regen, the single commit + PR | Task 9 |
| §5, §6 non-goals | No task — deliberately out of scope |

**Commit structure:** the spec and both reviews assumed three commits (§1 / §2+§3 / §4). Superseded by the
single-branch/single-commit/single-PR convention: the three parts remain as an ordered TDD sequence with a
green checkpoint each, but only Task 9 commits. Nothing about the code changes — only where the commit
boundaries fall — so the spec was left describing the parts and this plan owns the commit structure.

**Placeholder scan:** every code step contains runnable code; no "add error handling", no "similar to
Task N", no TBD.

**Type consistency:** `_run_all` returns `tuple[list[R | None], list[UnitFailure]]` in Task 2 and is
consumed with exactly that shape in Task 3. `fingerprint(payload, *, length)` (Task 4) is called by
`fingerprint_model` (Task 5) with `length=length`. `fingerprint_model(model, *, exclude, length)` (Task 5)
is called as `fingerprint_model(cfg.evaluation, exclude=_SEED_CACHE_EXCLUDE)` (Task 6). `code_identity(*,
repo_root)` (Task 7) is called argument-free in Task 8 and with `repo_root=` only in tests. Test names are
all lowercase (`N802`).

**Plan review round 1 — all four findings fixed:**

| ID | Finding | Fix |
|---|---|---|
| **P1** (blocker) | `Path(__file__)` repo discovery reports the **consumer's** commit as `ruthless_git_commit` when ruthless is wheel-installed into a project-local venv — measured, and invisible to Task 7's tests as originally written. | `_repo_owns_module` containment check gated on `repo_root is None`, plus 4 regression tests including the previously-untested "installed inside a foreign repo" layout. Spec §4.3 corrected too. |
| **P2** | Tasks 2 and 5 said "append" for blocks opening with imports → `E402` fails the gate. | Both now say to put the imports at the **top** and append only the rest. |
| **P3** | Task 8 Step 2's pytest command omitted `tests/test_random_strategy.py`, so the new strategy test was never collected and its red phase silently did not happen. | Command corrected, with the reason inline. |
| **P4** | Expected test counts overcounted (176/18/25/204 → actually 174/16/23/200); the first double-counted the 2 pre-existing `test_parallel.py` tests. | Recounted, with a running-total reference table in Task 6. |

P1 was verified here before accepting it — a synthetic consumer repo with a project-local venv reproduces
it exactly (identical SHA from the installed package dir, venv gitignored and irrelevant). It was my error:
the CWD→`Path(__file__)` change was introduced *during planning* and documented as a correctness improvement
without ever being run against the layout it claimed to handle.

**Plan review round 2 — four findings, resolved by one design change plus a recount:**

| ID | Finding | Resolution |
|---|---|---|
| **R1** | Task 7 Step 4 still said "6 tests" after the section gained four. | Recounted to **11** (the design change below makes it 5 new, not 4), running-total table updated, and both places now carry an explicit "recount if you add a test" instruction. |
| **R2** | The `startswith("<")` guard was unreachable (`_run_git` returns `None` on every failure), and its test pinned a sentinel convention nothing produces — while the genuinely valuable test (a *failed* git lookup → `unknown`) was missing. | **Dissolved.** The sentinel leaked from my verification probe into the production design; it is gone. R2's valuable test now exists as `test_code_identity_reports_unknown_when_the_module_is_not_tracked`. |
| **R3** | `_PKG_RELATIVE` derived only the immediate parent, encoding an unstated "package sits at the repo root" assumption; a `src/` layout would fail-closed in a *legitimate* checkout. | **Fixed rather than documented around** — see below. |
| **R4** | The `_PKG_RELATIVE` monkeypatch in the integration test was a no-op that read as load-bearing. | **Dissolved** — `_PKG_RELATIVE` no longer exists. |

**The design change:** `_repo_owns_module` (path comparison) → **`_repo_tracks_module`** (`git ls-files
--error-unmatch`). Round 1 proposed the path comparison and round 2 verified it works for today's layout;
R3 correctly identified that it only *documents* the `src/` limitation. Asking git whether it tracks the file
removes the limitation instead. Measured across five layouts before adopting: `ls-files` is correct on all
five, path comparison is wrong on one (`src/`). It also needs one git call instead of two, and handles
vendored-source and untracked-module cases correctly for principled reasons rather than by accident.
Details and the measurement table are in Task 7's opening blockquote.

**Known deviations from the spec, both deliberate and flagged for review:**

1. **§3.1 test 3's name** is `test_nested_mapping_keys_are_type_tagged`, not `..._KEYS_...` — ruff `N802`
   rejects uppercase in function names and tests get no per-file ignore. Same for §3.2's test.
2. **§4.3's provenance keys are `ruthless_`-prefixed** and the repo is resolved from `Path(__file__)`
   rather than the CWD, with a `repo_root` parameter for testability. Rationale is in the spec's §4.3;
   raised here because it changes the key names a consumer would read.
