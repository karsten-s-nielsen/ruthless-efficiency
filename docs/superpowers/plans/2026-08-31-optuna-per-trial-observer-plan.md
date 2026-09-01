# OptunaStrategy Per-Trial Observer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, neutral per-trial `Observer` hook to `OptunaStrategy.run` so consumers migrating raw-Optuna workflows regain a live per-trial callback (progress bars, metric sinks), without leaking Optuna or any sink into the pure core.

**Architecture:** Two additive, stdlib-only core types — `ProgressEvent` (frozen value type in `ruthless/result.py`) and `Observer` (a single-`__call__` `Protocol` in `ruthless/strategy.py`). `OptunaStrategy.run` gains a keyword-only `observer=None`; when given, a strategy-local wrapper translates each Optuna `FrozenTrial` into a `ProgressEvent` and fires the observer via `study.optimize(callbacks=[...])`, isolating observer faults so a telemetry sink can never abort the search. The port `SearchStrategy.run` is deliberately unchanged (Optuna-only wiring — a port-level hook random/evolve merely ignored would be a silent no-op).

**Tech Stack:** Python ≥3.10, pydantic v2 (`<3`), numpy (`<3`), optuna (`>=4.0`, `[optuna]` extra), pytest + hypothesis, ruff, pyright (basic), import-linter, hatchling.

**Spec:** `docs/superpowers/specs/2026-08-31-optuna-per-trial-observer-design.md` — spec review round 2 = APPROVE, then revised to **rev 2** for the §1.1 positional-only `Observer` correction made in lockstep with this plan's OBS-PLAN-01 fix (verified with pyright basic, 0 errors). Read it alongside this plan; every task argues from it.

## Global Constraints

Exact values copied from the spec / repo conventions. Every task implicitly includes these.

- **No per-task commits. One commit at the very end, on Karsten's explicit approval.** This plan does NOT use the "commit after each task" cadence (a user-level standing rule overrides any skill default). Each task ends at "tests green". The single feature commit — bundling the spec, this plan, all code, tests, and release bookkeeping — happens only in Task 6, after all five quality gates + `/final-review` pass, and only after Karsten says yes to the shown diff.
- **TDD, red → green per change.** Write the failing test first, run it to see it fail for the expected reason, implement the minimum, run it green.
- **Neutral core, no sink.** `ProgressEvent`/`Observer` import nothing outside the stdlib + existing core value types. `state` is a neutral lowercase `str` (`"complete"`), never Optuna's `TrialState`. `import ruthless` must still pull no optuna.
- **`ProgressEvent.number` is the STUDY-GLOBAL trial number** (`ft.number`) — it matches `Candidate.id` (`t{number}`) and `Result.history`, and does NOT reset on resume. Never document or treat it as a per-run ordinal.
- **Import-linter unchanged.** Both types live in modules already listed under the `core-isolation` contract (`ruthless.result`, `ruthless.strategy`); no `.importlinter` edit. `strategies/optuna_` may import from core (`ruthless.strategy`, `ruthless.result`) — that is strategy→core, allowed.
- **Lint rules that bite here:** ruff `select = [E, W, F, I, N, UP, B, S, BLE, RUF]`; `per-file-ignores` for `tests/**` is `["S101"]` ONLY — so **test function names must be lowercase** (`N802` is live), no lambda assignment (`E731`), no mid-file/module imports after code (`E402`), and a blind `except Exception` needs `# noqa: BLE001` with an inline reason. Import order is enforced (`I`).
- **pyright runs over `ruthless` AND `tests`** in `basic` mode — a typed assignment in a test is a real static check.
- **Version bump is the single line in `ruthless/_version.py`** and lands in the SAME (final) commit as the work. Target `0.5.0` — minor, additive, **not cache-invalidating** (fingerprint/digest path untouched).
- **Run gates with all extras installed**, matching CI: prefix pytest/pyright with `uv run --all-extras …` so optuna/evolve/backends imports resolve (the optuna tests call `import optuna` inside `run()`).

---

### Task 1: Core value type — `ProgressEvent`

**Files:**
- Modify: `ruthless/result.py` (add `ProgressEvent` after the `Evaluation` dataclass)
- Test: `tests/test_result.py`

**Interfaces:**
- Consumes: `Candidate`, `Metrics` (already defined in `ruthless/result.py`)
- Produces: `ProgressEvent(number: int, candidate: Candidate, metrics: Metrics, state: str)` — a frozen dataclass.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_result.py` — add `import dataclasses` in the stdlib group (it must sort BEFORE `import pytest` for ruff `I`), extend the existing `ruthless.result` import, and append the tests. The resulting header is:

```python
import dataclasses

import pytest

from ruthless.result import Candidate, Evaluation, ProgressEvent, Result


def test_progress_event_holds_its_fields():
    c = Candidate(id="t0", params={"x": 1.0})
    ev = ProgressEvent(number=0, candidate=c, metrics={"loss": 2.0, "aux": 1.0}, state="complete")
    assert ev.number == 0
    assert ev.candidate is c
    assert ev.metrics == {"loss": 2.0, "aux": 1.0}
    assert ev.state == "complete"


def test_progress_event_is_frozen():
    ev = ProgressEvent(number=1, candidate=Candidate(id="t1", params={}), metrics={}, state="complete")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.number = 99  # type: ignore[misc]
```

(`pytest` is already imported at the top of `tests/test_result.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --all-extras pytest tests/test_result.py::test_progress_event_holds_its_fields -v`
Expected: FAIL — `ImportError: cannot import name 'ProgressEvent' from 'ruthless.result'`.

- [ ] **Step 3: Write minimal implementation**

In `ruthless/result.py`, add immediately after the `Evaluation` dataclass (it uses `Candidate` and `Metrics`, both defined above it):

```python
@dataclass(frozen=True)
class ProgressEvent:
    """One observation of a completed candidate evaluation, handed to an Observer. Neutral across
    strategies: it names no strategy-specific concept. ``number`` is the STUDY-GLOBAL trial number — it
    matches ``Candidate.id`` (``t{number}``) and the returned ``Result.history``, and does NOT reset on
    resume (a resumed run observes continued numbers such as 20..49, never a fresh 0..29). ``metrics``
    carries every recorded metric (the scored one plus any auxiliaries), so a sink need not know which
    key the strategy optimises. ``state`` is a neutral lowercase string (e.g. "complete"), never a
    backend's own state enum."""

    number: int
    candidate: Candidate
    metrics: Metrics
    state: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --all-extras pytest tests/test_result.py -v`
Expected: PASS (both new tests + the existing ones).

---

### Task 2: Core port — `Observer`

**Files:**
- Modify: `ruthless/strategy.py` (add `Observer` Protocol; extend the `ruthless.result` import)
- Test: `tests/test_strategy_port.py`

**Interfaces:**
- Consumes: `ProgressEvent` (from Task 1)
- Produces: `Observer` — a `Protocol` with `def __call__(self, event: ProgressEvent, /) -> None`. The `event` parameter is **positional-only** (`/`) so ANY one-argument callable conforms regardless of its own parameter name — `def f(event)`, `def f(e)`, `lambda e: …`, and bound methods like `list.append`. (A *named* `event` parameter would, under pyright basic, reject `list.append`/`lambda e` — verified. The `/` is load-bearing.) Deliberately NOT `runtime_checkable` (an isinstance check would be a trivially-true, misleading guard).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_strategy_port.py` — extend imports and append:

```python
# extend the existing imports:
from ruthless.result import Candidate, ProgressEvent, Result
from ruthless.strategy import Direction, Observer, SearchStrategy


def test_plain_callable_satisfies_observer():
    seen_numbers: list[int] = []

    def obs(e: ProgressEvent) -> None:  # param NAMED 'e', not 'event' — guards the positional-only '/'
        seen_numbers.append(e.number)

    typed: Observer = obs  # conforms ONLY because Observer.__call__ is positional-only (pyright guard)
    ev = ProgressEvent(number=3, candidate=Candidate(id="t3", params={}), metrics={}, state="complete")
    typed(ev)
    assert seen_numbers == [3]

    # a bound method also conforms (positional-only) — a second pyright guard for the '/'
    collected: list[ProgressEvent] = []
    appender: Observer = collected.append
    appender(ev)
    assert collected == [ev]
```

**Why the param is named `e` (not `event`) and why `collected.append` is here:** both are pyright guards for the positional-only `/`. If a future edit removes the `/` from `Observer.__call__`, `typed: Observer = obs` fails (`Parameter name mismatch e vs event`) AND `appender: Observer = collected.append` fails (`append` is positional-only and cannot accept `event=`), so the type gate over `tests/` catches the regression. A test using `def obs(event)` would NOT catch it.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --all-extras pytest tests/test_strategy_port.py::test_plain_callable_satisfies_observer -v`
Expected: FAIL — `ImportError: cannot import name 'Observer' from 'ruthless.strategy'`.

- [ ] **Step 3: Write minimal implementation**

In `ruthless/strategy.py`: extend the result import and add the `Observer` protocol. The current import line is `from ruthless.result import Result`; change it to:

```python
from ruthless.result import ProgressEvent, Result
```

Then add, after the `SearchStrategy` protocol (keep `Observer` NON-`runtime_checkable` — do not decorate it; keep the `/` — it is load-bearing):

```python
class Observer(Protocol):
    """A per-candidate progress sink handed to a strategy's ``run``. Called once per completed
    evaluation, in evaluation order, with a :class:`~ruthless.result.ProgressEvent`. ``event`` is
    POSITIONAL-ONLY (the ``/``) so ANY one-argument callable conforms regardless of its own parameter
    name — a function, a ``lambda``, or a bound method such as ``list.append``. Dropping the ``/``
    would silently break that: under pyright basic a protocol whose parameter is named ``event`` is
    only satisfied by callables whose own parameter is named ``event`` (so ``list.append`` and
    ``lambda e: ...`` would stop conforming). Implementations MUST NOT assume they see every candidate
    a run produced — on a resumed study they observe only the candidates evaluated in that call (see
    ``OptunaStrategy.run``). An Observer that raises must not be able to abort the search: the strategy
    isolates it (logs and continues).

    Intentionally NOT ``runtime_checkable``: an Observer is never isinstance-guarded, and a
    ``__call__``-only runtime check would be true for any callable — a misleading guard."""

    def __call__(self, event: ProgressEvent, /) -> None: ...
```

(`Protocol` is already imported at the top of `strategy.py`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --all-extras pytest tests/test_strategy_port.py -v`
Expected: PASS.

---

### Task 3: Public API surface + core-stays-sink-free

**Files:**
- Modify: `ruthless/__init__.py` (import both names; add to `__all__`)
- Test: `tests/test_public_api.py` (add both to `_EXPECTED_PUBLIC`; add the sink-free subprocess test)

**Interfaces:**
- Consumes: `ProgressEvent` (Task 1), `Observer` (Task 2)
- Produces: `from ruthless import Observer, ProgressEvent` works; both are in `ruthless.__all__`.

- [ ] **Step 1: Write the failing test**

In `tests/test_public_api.py`, add `"Observer"` and `"ProgressEvent"` to the `_EXPECTED_PUBLIC` set (place `"Observer"` in the ports group, `"ProgressEvent"` in the value-types group), and append the sink-free test:

```python
def test_core_observer_types_pull_no_optuna() -> None:
    # Constructing/using the new core observer types must not import optuna: they are pure core. Checked
    # in a clean subprocess so an extra imported by another test cannot mask a regression. (mlflow is
    # never a ruthless dependency, so the meaningful guard is optuna-absence.)
    code = (
        "import sys; from ruthless import ProgressEvent, Observer, Candidate; "
        "ProgressEvent(number=0, candidate=Candidate(id='t0', params={}), metrics={}, state='complete'); "
        "assert 'optuna' not in sys.modules, 'core observer types must not import optuna'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603 - fixed argv, no shell
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --all-extras pytest tests/test_public_api.py -v`
Expected: FAIL — `test_all_is_declared_and_complete` and `test_every_public_name_is_importable_from_the_top_level` fail (the names are in `_EXPECTED_PUBLIC` but not yet exported), and/or the new test fails on `ImportError`.

- [ ] **Step 3: Write minimal implementation**

In `ruthless/__init__.py`:

Change the result import to include `ProgressEvent`:

```python
from ruthless.result import Candidate, Evaluation, Metrics, ProgressEvent, Result
```

Change the strategy import to include `Observer`:

```python
from ruthless.strategy import Direction, Observer, SearchStrategy
```

Add the two names to `__all__`, keeping it alphabetical: insert `"Observer"` between `"Objective"` and `"OptimizationError"`, and `"ProgressEvent"` between `"OptunaConfig"` and `"RandomConfig"`:

```python
    # ports
    "Objective",
    "Observer",
    ...
    "OptunaConfig",
    "ProgressEvent",
    "RandomConfig",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --all-extras pytest tests/test_public_api.py -v`
Expected: PASS (all four existing tests + the new sink-free test).

---

### Task 4: Optuna observer wiring (translation + fault isolation + resume contract)

**Files:**
- Modify: `ruthless/strategies/optuna_/strategy.py` (imports; a `_to_event` helper; `run` signature + docstring + callback wiring)
- Test: `tests/strategies/optuna_/test_optuna_strategy.py` (unit behaviours) and `tests/e2e/test_optuna_resume_gate.py` (resume/boundary)

**Interfaces:**
- Consumes: `ProgressEvent` (Task 1), `Observer` (Task 2), and the existing `Candidate`, `OptunaStrategy`, `InProcessBackend`, `FatalEvaluationError`.
- Produces: `OptunaStrategy.run(self, objective, *, backend, observer: Observer | None = None) -> Result` — fires `observer` once per completed trial via `study.optimize(callbacks=[...])`.

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/strategies/optuna_/test_optuna_strategy.py`. The file already has `Quadratic`, `_cfg`, and imports `OptunaStrategy`, `InProcessBackend`, `OptunaConfig`, `Candidate`. Replace the file's import block with the following complete, isort-ordered block (merges `ProgressEvent` into the existing `ruthless.result` line — do NOT add a second `from ruthless.result` line, ruff `I` will reject it; `_Cached` is structural so `CachedObjective` is NOT imported), then add the tests below:

```python
import logging
import math

import pytest

from ruthless.backend import InProcessBackend
from ruthless.config import OptunaConfig
from ruthless.errors import FatalEvaluationError
from ruthless.result import Candidate, ProgressEvent
from ruthless.strategies.optuna_.strategy import OptunaStrategy
from ruthless.strategy import SearchStrategy


class QuadraticWithAux:
    def evaluate(self, candidate):
        x = candidate.params["x"]
        return {"loss": (x - 3.0) ** 2, "aux": 1.0}


class _Cached:
    patch_params = frozenset({"x"})

    def evaluate(self, candidate):
        return {"loss": (candidate.params["x"] - 3.0) ** 2}

    def prepare(self):
        return {"base": 3.0}

    def evaluate_patch(self, invariant, candidate):
        return {"loss": (candidate.params["x"] - invariant["base"]) ** 2}


def test_observer_fires_once_per_completed_trial():
    events: list[ProgressEvent] = []
    r = OptunaStrategy(_cfg(n=8), seed=42).run(Quadratic(), backend=InProcessBackend(), observer=events.append)
    assert [e.number for e in events] == list(range(8))       # one per trial, study-global numbers, in order
    assert all(e.state == "complete" for e in events)
    assert all("x" in e.candidate.params for e in events)
    assert len(r.history) == 8


def test_observer_event_carries_all_metrics_not_only_scored():
    events: list[ProgressEvent] = []
    OptunaStrategy(_cfg(n=4), seed=1).run(QuadraticWithAux(), backend=InProcessBackend(), observer=events.append)
    assert all("loss" in e.metrics and "aux" in e.metrics for e in events)
    assert all(e.metrics["aux"] == 1.0 for e in events)


def test_observer_none_runs_normally():
    r = OptunaStrategy(_cfg(n=6), seed=99).run(Quadratic(), backend=InProcessBackend(), observer=None)
    assert len(r.history) == 6 and r.best is not None


def test_observer_fires_for_warm_start_trial():
    events: list[ProgressEvent] = []
    OptunaStrategy(_cfg(n=5, warm_start={"x": 7.5}), seed=1).run(
        Quadratic(), backend=InProcessBackend(), observer=events.append
    )
    assert events[0].number == 0 and events[0].candidate.params["x"] == 7.5


class _FatalOnSecondEval:
    def __init__(self):
        self.calls = 0

    def evaluate(self, candidate):
        self.calls += 1
        x = candidate.params["x"]
        return {"loss": math.inf if self.calls == 2 else (x - 3.0) ** 2}


def test_fatal_metric_neither_records_nor_observes_and_propagates():
    events: list[ProgressEvent] = []
    with pytest.raises(FatalEvaluationError):
        OptunaStrategy(_cfg(n=5), seed=3).run(
            _FatalOnSecondEval(), backend=InProcessBackend(), observer=events.append
        )
    # only the first (completed) trial fired; the aborting trial fired nothing
    assert [e.number for e in events] == [0]
    assert all(e.state == "complete" for e in events)


def test_observer_exception_is_isolated(caplog):
    def boom(event):
        raise ValueError("observer boom")

    with caplog.at_level(logging.WARNING, logger="ruthless.strategies.optuna"):
        r = OptunaStrategy(_cfg(n=5), seed=2).run(Quadratic(), backend=InProcessBackend(), observer=boom)
    assert len(r.history) == 5 and r.best is not None            # search completed despite the raising sink
    assert sum(1 for rec in caplog.records if rec.msg == "observer_failed") == 5


def test_observer_isolated_when_it_raises_on_one_trial_only(caplog):
    seen: list[int] = []

    def flaky(event):
        seen.append(event.number)
        if event.number == 1:
            raise ValueError("boom on trial 1")

    with caplog.at_level(logging.WARNING, logger="ruthless.strategies.optuna"):
        r = OptunaStrategy(_cfg(n=5), seed=8).run(Quadratic(), backend=InProcessBackend(), observer=flaky)
    assert r.diagnostics["n_trials"] == 5 and len(r.history) == 5   # study completed all trials
    assert seen == [0, 1, 2, 3, 4]                                  # every trial still observed
    assert sum(1 for rec in caplog.records if rec.msg == "observer_failed") == 1  # exactly one logged


def test_observer_fires_on_cached_objective_fast_path():
    events: list[ProgressEvent] = []
    OptunaStrategy(_cfg(n=6), seed=5).run(_Cached(), backend=InProcessBackend(), observer=events.append)
    assert [e.number for e in events] == list(range(6))
    assert all("loss" in e.metrics for e in events)


def test_optuna_strategy_still_conforms_to_search_strategy():
    strat: SearchStrategy = OptunaStrategy(_cfg(n=2))  # widened signature must stay a SearchStrategy (type guard)
    assert isinstance(strat, SearchStrategy)
```

- [ ] **Step 2: Write the failing resume/boundary tests**

Append to `tests/e2e/test_optuna_resume_gate.py` (it already defines `_Bowl`, `_cfg(n, path)`, and imports `OptunaStrategy`, `InProcessBackend`):

```python
def test_observer_resume_fires_only_new_continued_numbers(tmp_path):
    db = str(tmp_path / "obs.db")
    first: list = []
    OptunaStrategy(_cfg(2, db), seed=123).run(_Bowl(), backend=InProcessBackend(), observer=first.append)
    assert [e.number for e in first] == [0, 1]
    second: list = []
    OptunaStrategy(_cfg(4, db), seed=123).run(_Bowl(), backend=InProcessBackend(), observer=second.append)
    # the resumed run fires ONLY the two new trials, with CONTINUED store-global numbers — not 0,1
    assert [e.number for e in second] == [2, 3]


def test_observer_resume_with_no_remaining_trials_fires_zero_events(tmp_path):
    db = str(tmp_path / "done.db")
    OptunaStrategy(_cfg(3, db), seed=123).run(_Bowl(), backend=InProcessBackend())  # fill to n_trials
    events: list = []
    r = OptunaStrategy(_cfg(3, db), seed=123).run(_Bowl(), backend=InProcessBackend(), observer=events.append)
    assert events == []              # remaining == 0 → study.optimize not called → no events
    assert len(r.history) == 3       # Result is still reconstructed from the store
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run --all-extras pytest tests/strategies/optuna_/test_optuna_strategy.py tests/e2e/test_optuna_resume_gate.py -v`
Expected: every new test that calls `run(..., observer=...)` — including the one passing `observer=None` — FAILS with `TypeError: run() got an unexpected keyword argument 'observer'`. The ONE exception is `test_optuna_strategy_still_conforms_to_search_strategy`, which PASSES at red: it never passes an observer; it is a pyright/isinstance conformance guard that must stay green before AND after the change (adding an *optional* parameter is a compatible widening; `isinstance` is name-only), not a runtime red→green test. (The pre-existing tests in both files still PASS.)

- [ ] **Step 4: Implement the observer wiring**

In `ruthless/strategies/optuna_/strategy.py`:

**(a) Imports.** Add `ProgressEvent` to the result import and add the strategy import (keep isort order — `ruthless.strategy` sorts after `ruthless.result`):

```python
from ruthless.result import Candidate, Evaluation, ProgressEvent, Result
from ruthless.strategy import Observer
```

**(b) Translator.** Add a module-level helper after `_suggest`:

```python
def _to_event(ft: Any) -> ProgressEvent:
    """Translate an Optuna FrozenTrial into a neutral ProgressEvent. ``number`` is Optuna's
    study-global trial number (matches Candidate.id and does NOT reset on resume); ``metrics`` mirrors
    ``_to_eval`` (every recorded user_attr, scored + auxiliary); ``state`` is a neutral lowercase
    string, never Optuna's TrialState."""
    return ProgressEvent(
        number=ft.number,
        candidate=Candidate(id=f"t{ft.number}", params=dict(ft.params)),
        metrics=dict(ft.user_attrs),
        state=ft.state.name.lower(),
    )
```

**(c) Signature + docstring.** Change the `run` signature and add a docstring (the current `run` has none):

```python
    def run(self, objective: Objective, *, backend: ComputeBackend, observer: Observer | None = None) -> Result:
        """Drive the study and return a Result spanning the whole store.

        Args:
            objective: The objective to optimise (or a CachedObjective for the fast patch path).
            backend: Compute backend used for the full-evaluate path.
            observer: Optional neutral per-trial sink — any callable ``(ProgressEvent) -> None``. Fires
                ONCE per completed trial, in trial order, after the trial is stored. Contract:

                * Live hook, not a replay. On a resumed study the observer sees only the trials run in
                  THIS call; ``ProgressEvent.number`` is the study-global trial number and does NOT
                  reset on resume. The whole-store view is ``Result.history``. A per-run progress
                  fraction must count events, not divide ``number`` by the budget.
                * Fault-isolated. An observer that raises is logged at warning and the search continues.
                * Fatal metrics are not observed. A non-finite scored metric raises
                  ``FatalEvaluationError``, aborts the study, and fires no event for that trial.
                * Fires identically for the full-evaluate and CachedObjective fast paths.
        """
        import optuna
```

(Keep the existing body — `from optuna.samplers import ...`, `from optuna.trial import TrialState`, etc. — immediately after `import optuna`.)

**(d) Wire the callback.** Replace the current tail:

```python
        remaining = max(0, cfg.n_trials - n_existing)
        if remaining:
            study.optimize(_objective, n_trials=remaining)
```

with:

```python
        # An observer (if given) is wired as an Optuna callback: it fires once per completed trial, in
        # trial order. The wrapper isolates observer faults — a telemetry sink must never abort the
        # search (a raw callback exception propagates out of study.optimize). callbacks=None (Optuna's
        # default) reproduces the pre-observer behaviour exactly.
        callbacks: list[Any] | None = None
        if observer is not None:
            obs = observer  # non-None binding for the closure (narrowing does not survive into it)

            def _observer_callback(study: Any, ft: Any) -> None:
                try:
                    obs(_to_event(ft))
                except Exception:  # noqa: BLE001 — a telemetry sink must never abort the search
                    _log.warning("observer_failed", extra={"trial": ft.number}, exc_info=True)

            callbacks = [_observer_callback]

        remaining = max(0, cfg.n_trials - n_existing)
        if remaining:
            study.optimize(_objective, n_trials=remaining, callbacks=callbacks)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --all-extras pytest tests/strategies/optuna_/test_optuna_strategy.py tests/e2e/test_optuna_resume_gate.py -v`
Expected: PASS (all new + all pre-existing tests in both files).

- [ ] **Step 6: Confirm the static conformance guard holds**

Run: `uv run --all-extras pyright ruthless/strategies/optuna_/strategy.py tests/strategies/optuna_/test_optuna_strategy.py`
Expected: 0 errors — in particular, `strat: SearchStrategy = OptunaStrategy(...)` type-checks, proving the added optional `observer` parameter keeps `OptunaStrategy` structurally a `SearchStrategy`.

---

### Task 5: Release bookkeeping (version + CHANGELOG + CLAUDE.md)

**Files:**
- Modify: `ruthless/_version.py` (bump the single version line)
- Modify: `CHANGELOG.md` (new `0.5.0` section above `[0.4.0]`)
- Modify: `CLAUDE.md` ("Ships at" line + a Phase-2 conventions bullet)

**Interfaces:** none (documentation + metadata only).

- [ ] **Step 1: Bump the version**

In `ruthless/_version.py`, change the single line:

```python
__version__ = "0.5.0"
```

- [ ] **Step 2: Add the CHANGELOG entry**

In `CHANGELOG.md`, insert this section immediately above `## [0.4.0] - 2026-07-30`:

```markdown
## [0.5.0] - 2026-08-31

Minor rather than patch: the public API gains two names (`Observer`, `ProgressEvent`) and
`OptunaStrategy.run` gains an optional `observer` keyword. **This release does not invalidate existing
caches** — the fingerprint/digest path is untouched.

### Added
- **A neutral per-trial observer for `OptunaStrategy`.** `OptunaStrategy.run(..., observer=None)` accepts
  an optional `Observer` — any callable `(ProgressEvent) -> None`. It fires once per completed trial, in
  trial order, with a `ProgressEvent(number, candidate, metrics, state)`, giving consumers migrating
  raw-Optuna workflows back the per-trial callback hook (progress bars, live metric sinks) that
  `study.optimize(callbacks=...)` provided. The MLflow/logging sink itself stays consumer-side.
- **`Observer` (port) and `ProgressEvent` (value type) are public core types** (`from ruthless import
  Observer, ProgressEvent`). Both are strategy-agnostic and stdlib-only: `import ruthless` still pulls no
  optuna, and `ProgressEvent.state` is a neutral string (`"complete"`), never Optuna's `TrialState`, so
  the core stays isolated. The types are designed so any strategy can adopt the hook later without a
  breaking change; today only `OptunaStrategy` wires it (a port-level `observer` that random/evolve
  merely ignored would be a silent no-op).

### Semantics
- The observer is a **live** per-trial hook: on a resumed study it sees only the trials run in that call,
  and `ProgressEvent.number` is the study-global trial number (it does not reset on resume). The
  whole-store view remains `Result.history`.
- An observer that raises is isolated: the failure is logged at `warning` and the search continues — a
  telemetry sink can never abort the optimization. A fatal (non-finite scored) metric still aborts the
  study and fires no event for the aborted trial.
```

- [ ] **Step 3: Update CLAUDE.md**

In `CLAUDE.md`, first paragraph, change `Ships at \`0.4.0\`` to `Ships at \`0.5.0\``.

Then, in the **"Key Phase-2 conventions"** section, add this bullet after the `OptunaStrategy resume (C3)` bullet:

```markdown
- **OptunaStrategy observer (0.5.0):** `run(..., observer=None)` accepts a neutral `Observer`
  (`(ProgressEvent) -> None`; both are public core types). It fires once per completed trial via
  `study.optimize(callbacks=...)`. `ProgressEvent.number` is the study-global trial number (does NOT
  reset on resume); a raising observer is logged-and-isolated (never aborts the search); the core
  imports no sink (`state` is a neutral `str`, not Optuna's `TrialState`). Optuna-only by design — a
  port-level hook random/evolve merely ignored would be a silent no-op.
```

- [ ] **Step 4: Sanity-check the version is readable**

Run: `uv run --all-extras python -c "import ruthless; print(ruthless.__version__)"`
Expected: prints `0.5.0`.

---

### Task 6: Full quality gate + `/final-review` + commit gate

**Files:** none new. This task runs the gates, generates/updates the C4 diagram via `/final-review`, and stops at the commit approval gate.

**Interfaces:** none.

- [ ] **Step 1: Run the five-gate local quality run (mirrors CI)**

Run each; all must pass:

```bash
uv run --all-extras ruff check ruthless tests
uv run --all-extras ruff format --check ruthless tests
uv run --all-extras pyright
uv run --all-extras lint-imports
uv run --all-extras pytest -v
```

Expected: ruff clean; format clean; pyright 0 errors; **all 3 import-linter contracts pass** (`core-isolation`, `strategy-isolation`, `backends-isolation`); the FULL suite green (the ~282 baseline plus the new observer tests). If `ruff format --check` flags anything, run `uv run --all-extras ruff format ruthless tests` and re-run the gates.

- [ ] **Step 2: Run `/final-review`**

Invoke the `/final-review` command (the project's mandatory pre-commit gate). It reviews all code + docs for consistency and completeness and generates/updates the C4 diagram at `docs/c4/architecture.html`. Address anything it surfaces (loudly — do not grade an issue down to avoid the work); re-run Step 1's gates after any fix.

- [ ] **Step 3: Present the commit for explicit approval — DO NOT COMMIT YET**

Show Karsten the exact commit contents and wait for an explicit yes. Gather the diff/file list:

```bash
git status
git add -A && git --no-pager diff --staged --stat
git --no-pager diff --staged
```

The staged set should be exactly: `ruthless/result.py`, `ruthless/strategy.py`, `ruthless/strategies/optuna_/strategy.py`, `ruthless/__init__.py`, `ruthless/_version.py`, `CHANGELOG.md`, `CLAUDE.md`, the test files, the spec, this plan, and any `docs/c4/architecture.html` regenerated by `/final-review`. Confirm nothing unexpected is staged.

**STOP here.** Per the standing commit rule, do not run `git commit` until Karsten explicitly approves this specific commit.

- [ ] **Step 4: On explicit approval — one commit, then PR/tag/publish**

Only after Karsten says yes:

```bash
git commit -m "$(cat <<'EOF'
feat(optuna): neutral per-trial Observer for OptunaStrategy (release 0.5.0)

Add an optional Observer hook to OptunaStrategy.run: a strategy-agnostic
ProgressEvent value type + Observer port in the core, wired for Optuna via
study.optimize callbacks with fault isolation. Optuna-only by design; core
stays sink-free. Bumps 0.4.0 -> 0.5.0 (additive, non-cache-invalidating).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TJwiPmeZAKC75AthBxDzX2
EOF
)"
```

Then push the branch, open the PR (bundling spec + plan + code), and after merge tag `v0.5.0` for the OIDC publish — **each of push / PR / tag on the normal flow; the commit was the gated step.**

---

## Self-Review

**1. Spec coverage** (each spec section → task):

- §1.1 `Observer` port → Task 2. §1.2 `ProgressEvent` (fields, `number` global, `state` str) → Task 1 (+ Task 4 docstring). §1.3 placement / no `.importlinter` edit → Tasks 1–2 (modules already covered) + Task 6 `lint-imports`. §1.4 strategy-agnostic types → Tasks 1–2 (neutral types), argued in CHANGELOG/CLAUDE.md (Task 5).
- §2.1 signature → Task 4(c). §2.2 `_to_event` → Task 4(b). §2.3 wiring → Task 4(d). §2.4 fault isolation → Task 4(d) + tests 7/12. §2.5 Optuna-only/port unchanged → Task 4 (no `strategy.py` port change) + test 9.
- §3 semantics contract → Task 4 run docstring + tests 1–8; resume (§3.2) → Task 4 resume tests.
- §4 tests 1–13 → Task 1 (event), Task 2 (observer), Task 3 (#10 public, #11 sink-free), Task 4 (#1–#9, #12 unit; #4, #13 resume). Baseline note (~282) → Task 6 Step 1.
- §5 public API / version / CHANGELOG / CLAUDE.md → Task 3 + Task 5; flow/commit-on-approval → Task 6.
- §6 non-goals → respected (no lifecycle, no sink, no random/evolve wiring, no config/CLI, no Result/report change). §7 rejected alternatives → not implemented, by construction.
- Appendix A (verbatim request) → already in the spec; no task needed.

No spec requirement is left without a task.

**2. Placeholder scan:** none — every code and test step contains the actual content; no "TBD"/"add error handling"/"similar to Task N".

**3. Type consistency:** `ProgressEvent(number, candidate, metrics, state)` is identical everywhere (Tasks 1, 2, 3, 4, tests). `Observer` = `(ProgressEvent) -> None` in Tasks 2, 4. `run(self, objective, *, backend, observer=None)` matches between Task 4 signature, all Task 4 tests, and the resume tests. `_to_event`/`_observer_callback` names are used only within Task 4. Logger key `"observer_failed"` matches between Task 4(d) and tests 7/12. `state == "complete"` matches Task 4(b) (`ft.state.name.lower()`) and tests 1/6.
