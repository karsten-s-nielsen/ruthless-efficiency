# Ruthless Efficiency — Phase 1A (Core + Bootstrap) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** rev 2 — incorporates the Plan-1A review (C-A/C-B/C-C, H-A–H-D, M-A–M-E, minors). Tasks are in strict dependency order: each is independently green (red→green holds per task) for subagent-driven execution.

**Goal:** Bootstrap the standalone `ruthless-efficiency` library with its pure hexagonal core (ports, value types, config, errors, in-process backend, guards, parallel utility, reporting, observability) plus a minimal built-in `RandomSearchStrategy`, validated by a dependency-free determinism+convergence gate.

**Architecture:** Hexagonal. `ruthless/` core modules define ports (`Objective`, `SearchStrategy`, `ComputeBackend`) + value types (`Candidate`, `Metrics`, `Result`) and depend only on `pydantic`+`numpy`(+`pyyaml`). Strategies/backends are sub-packages that depend on core, never the reverse (import-linter enforced). `RandomSearchStrategy` is the first `SearchStrategy` caller; `EvolveStrategy`/`OptunaStrategy` arrive in later plans.

**Tech Stack:** Python ≥3.10, pydantic v2, numpy, pyyaml, pytest + hypothesis, ruff, pyright, import-linter, hatchling. Repo exists at `D:\Development\karstenskyt__ruthless-efficiency` (`assets/` + hero image present).

**Spec:** `docs/superpowers/specs/2026-05-28-optimization-engine-carveout-design.md` (rev 3).

**Working directory:** all paths are relative to the new repo root unless prefixed `[lakehouse]`. No worktrees (project convention) — feature branch in the new repo.

**Standing constraints:** No commit without explicit user approval (the "Commit" steps are PAUSE points). Ships as **0.1.0** — ports are not yet validated by evolve/optuna/silly-kicks; the API is explicitly unstable (`0.x`).

**Out of scope (later plans, by design):** `EvolveStrategy` (a *hybrid* — our orchestration over OpenEvolve's loop, spec C-A), `BackendPool` + SSH/HF-Jobs/Docker backends, per-candidate **timeout enforcement** + **transient-retry contract** (the port carries `timeout` now per H-C/M-E, but only remote backends in 1B implement it), `shared.wheel`→`remote_package` sever, AST sandbox (`[evolve]`), lakehouse-evolve migration (Plan 1B); `OptunaStrategy`, `CachedObjective` + `assert_cache_equivalence`, group-scoring `scoring.py`, TC3 migration (Phase 2).

---

## File Structure

```
ruthless/
  __init__.py            # version + public re-exports
  errors.py              # OptimizationError; FatalEvaluationError / TransientEvaluationError; classify_metric()
  result.py              # Candidate (hashable), Metrics (alias), Evaluation, Result
  objective.py           # Objective Protocol  (CachedObjective → Phase 2)
  backend.py             # ComputeBackend Protocol (evaluate has `timeout`) + InProcessBackend
  strategy.py            # Direction + SearchStrategy Protocol
  guards.py              # penalty_metrics()  (valid-but-penalized score; NOT an error)
  parallel.py            # map_work_units(fn, items, *, workers, executor)  — intra-objective utility (GIL note)
  _logging.py            # get_logger() → logging.getLogger("ruthless.<name>")
  config.py              # layered Pydantic: RuthlessConfig + discriminated strategy union + param-space union
  report.py              # render_json(result), render_summary_md(result)
  cli.py                 # `ruthless` entry: load config → build strategy → run → report (import-string loader)
  strategies/
    __init__.py
    random_/__init__.py
    random_/strategy.py  # RandomSearchStrategy.run(objective, *, backend) -> Result
tests/
  test_errors.py test_result.py test_objective.py test_backend.py test_strategy_port.py
  test_guards.py test_parallel.py test_logging.py test_config.py test_random_strategy.py
  test_report.py test_cli.py  fixtures/__init__.py fixtures/objectives.py
  e2e/test_determinism_convergence_gate.py
pyproject.toml  .importlinter  .gitignore  README.md  .github/workflows/ci.yml
```

**Dependency order (task order below follows this):** errors → result → objective → backend → strategy → guards → parallel → logging → config → random → report → cli → gate → ci. No task imports a module created in a later task (review C-B).

---

## Task 1: Repo bootstrap — packaging, tooling, skeleton

**Files:** Create `pyproject.toml`, `.importlinter`, `.gitignore`, `ruthless/__init__.py`, `ruthless/strategies/__init__.py`, `ruthless/strategies/random_/__init__.py`

- [ ] **Step 1: `pyproject.toml`** (pyyaml included up-front — minor review note; pyright covers tests — M-D)

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ruthless-efficiency"
version = "0.1.0"
description = "Ruthless Efficiency — a general optimisation/search substrate (pluggable strategies + compute backends)."
requires-python = ">=3.10"
readme = "README.md"
license = { text = "MIT" }
authors = [{ name = "Karsten Skyt" }]
keywords = ["optimization", "hyperparameter-optimization", "evolutionary-search", "optuna"]
# numpy pinned <3 so the RandomSearch RNG stream stays stable for the determinism gate (review H-D).
dependencies = ["pydantic>=2", "numpy>=1.24,<3", "pyyaml>=6"]

[project.optional-dependencies]
optuna = ["optuna>=4.0"]                                          # Phase 2
evolve = ["openevolve>=0.2.0"]                                    # Plan 1B (hybrid: our orchestration + OpenEvolve loop)
backends = ["paramiko>=3", "huggingface_hub>=0.25", "docker>=7"]  # Plan 1B
dev = ["pytest>=8", "hypothesis>=6", "ruff>=0.6", "pyright>=1.1.380", "import-linter>=2.0"]

[project.scripts]
ruthless = "ruthless.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["ruthless"]

[tool.ruff]
line-length = 120
target-version = "py310"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "UP", "B", "S", "BLE", "RUF"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]

[tool.pyright]
include = ["ruthless", "tests"]
typeCheckingMode = "basic"
pythonVersion = "3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: `.importlinter`** (exact contracts — spec L2)

```ini
[importlinter]
root_packages = ruthless

[importlinter:contract:core-isolation]
name = core must not import strategies or backends
type = forbidden
source_modules =
    ruthless.errors
    ruthless.result
    ruthless.objective
    ruthless.backend
    ruthless.strategy
    ruthless.guards
    ruthless.parallel
    ruthless.config
    ruthless.report
forbidden_modules =
    ruthless.strategies
    ruthless.backends

[importlinter:contract:strategy-isolation]
name = strategies must not import backends or each other
type = forbidden
source_modules =
    ruthless.strategies
forbidden_modules =
    ruthless.backends
```

- [ ] **Step 3: `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.ruff_cache/
.pytest_cache/
dist/
*.egg-info/
.import_linter_cache/
```

- [ ] **Step 4: package markers.** `ruthless/__init__.py`:
```python
"""Ruthless Efficiency — general optimisation/search substrate."""

__version__ = "0.1.0"
```
`ruthless/strategies/__init__.py` and `ruthless/strategies/random_/__init__.py`: empty.

- [ ] **Step 5: Verify**

Run: `uv venv && uv pip install -e ".[dev]" && uv run python -c "import ruthless; print(ruthless.__version__)"`
Expected: `0.1.0`.
Run: `uv run ruff check ruthless && uv run lint-imports`
Expected: ruff clean; "Contracts: 2 kept".

- [ ] **Step 6: Commit** (PAUSE)
```bash
git add pyproject.toml .importlinter .gitignore ruthless/
git commit -m "chore: bootstrap ruthless-efficiency 0.1.0 (packaging, tooling, import-linter)"
```

---

## Task 2: `errors.py` — error taxonomy (spec M1)

**Files:** Create `ruthless/errors.py`, `tests/test_errors.py`

- [ ] **Step 1: Failing test**
```python
# tests/test_errors.py
import math
import pytest
from ruthless.errors import (
    OptimizationError, FatalEvaluationError, TransientEvaluationError, classify_metric,
)


def test_classify_metric_passes_finite():
    classify_metric(0.42, candidate_id="c1", metric="score")  # no raise


@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan])
def test_classify_metric_raises_on_nonfinite(bad):
    with pytest.raises(FatalEvaluationError) as exc:
        classify_metric(bad, candidate_id="c1", metric="score")
    assert "c1" in str(exc.value) and "score" in str(exc.value)


def test_hierarchy():
    assert issubclass(FatalEvaluationError, OptimizationError)
    assert issubclass(TransientEvaluationError, OptimizationError)
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_errors.py -v` (module not found).

- [ ] **Step 3: Implement**
```python
# ruthless/errors.py
"""Error taxonomy. FATAL eval failures (crash/timeout/inf-or-NaN on the SCORED metric) are never
recorded as a valid score — they are surfaced (and, for remote backends in Plan 1B, retried when
transient). DEGENERATE-but-valid candidates are a separate concept handled by ruthless.guards (a
recorded penalty score).

NOTE (review M-E): the *who-retries-transient-with-bounded-backoff* contract is owned by the remote
backends in Plan 1B; Phase 1A only defines the taxonomy + the scored-metric finiteness check."""

from __future__ import annotations

import math


class OptimizationError(Exception):
    """Base class for all ruthless errors."""


class TransientEvaluationError(OptimizationError):
    """A retryable failure (e.g. backend timeout, transient network error). Retry contract: Plan 1B."""


class FatalEvaluationError(OptimizationError):
    """A non-retryable evaluation failure. Surfaced with the candidate key; never recorded as a score."""


def classify_metric(value: float, *, candidate_id: str, metric: str) -> None:
    """Raise FatalEvaluationError if the SCORED metric is inf/NaN (a broken evaluation, not a score).

    Callers pass ONLY the optimisation target metric here — diagnostic/auxiliary metrics are allowed
    to be non-finite (review C-C)."""
    if not math.isfinite(value):
        msg = f"non-finite scored metric {metric}={value!r} for candidate {candidate_id} (broken evaluation)"
        raise FatalEvaluationError(msg)
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_errors.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/errors.py tests/test_errors.py
git commit -m "feat: error taxonomy — fatal vs transient; classify_metric (scored metric only)"
```

---

## Task 3: `result.py` — value types (Candidate hashable — review H-A)

**Files:** Create `ruthless/result.py`, `tests/test_result.py`

- [ ] **Step 1: Failing test** (asserts real hashability + equality — H-A)
```python
# tests/test_result.py
from ruthless.result import Candidate, Evaluation, Result


def test_candidate_is_hashable_and_value_equal():
    a = Candidate(id="c1", params={"x": 1.0, "y": 2.0})
    b = Candidate(id="c1", params={"y": 2.0, "x": 1.0})  # same id+params, different insertion order
    assert hash(a) == hash(b)          # really hashable; order-independent
    assert a == b
    assert {a, b} == {a}               # usable as a set/dict key (Phase 2 dedup)


def test_result_tracks_best_and_history():
    e0 = Evaluation(candidate=Candidate("c0", {"x": 0.0}), metrics={"score": 1.0}, ok=True)
    e1 = Evaluation(candidate=Candidate("c1", {"x": 1.0}), metrics={"score": 2.0}, ok=True)
    r = Result(best=e1, history=[e0, e1], diagnostics={}, provenance={"seed": 42})
    assert r.best.candidate.id == "c1" and len(r.history) == 2 and r.provenance["seed"] == 42
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_result.py -v`.

- [ ] **Step 3: Implement**
```python
# ruthless/result.py
"""Value types. Candidate is hashable (param values must be hashable; do NOT mutate params after
construction) so Phase 2 can use it as a cache/dedup key (review H-A). The Result returned by a
strategy is the unified surface report.py renders; persistence is strategy-owned (spec H1).
Result is mutable-during-build but should be treated as immutable once returned (review M-C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Metrics = dict[str, float]


@dataclass(frozen=True, eq=False)
class Candidate:
    id: str
    params: dict[str, Any]  # values must be hashable; treat as immutable after construction

    def _key(self) -> tuple[str, frozenset]:
        return (self.id, frozenset(self.params.items()))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Candidate) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())


@dataclass(frozen=True)
class Evaluation:
    candidate: Candidate
    metrics: Metrics
    ok: bool  # False = penalty/degenerate (recorded); fatal failures are never recorded


@dataclass
class Result:
    """Treat as immutable once returned by SearchStrategy.run (review M-C)."""

    best: Evaluation | None
    history: list[Evaluation] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_result.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/result.py tests/test_result.py
git commit -m "feat: value types — hashable Candidate, Evaluation, Result"
```

---

## Task 4: `objective.py` — Objective port (structural — review M-A)

**Files:** Create `ruthless/objective.py`, `tests/test_objective.py`

- [ ] **Step 1: Failing test** (the conforming class does NOT inherit the Protocol — structural typing, M-A)
```python
# tests/test_objective.py
from ruthless.objective import Objective
from ruthless.result import Candidate


class Quadratic:  # NOT inheriting Objective — duck-typed conformance
    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        return {"loss": (candidate.params["x"] - 3.0) ** 2}


def test_structural_conformance():
    obj: Objective = Quadratic()
    assert obj.evaluate(Candidate("c", {"x": 3.0}))["loss"] == 0.0
    assert isinstance(obj, Objective)  # NOTE: runtime_checkable is name-only — does not verify signatures
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_objective.py -v`.

- [ ] **Step 3: Implement**
```python
# ruthless/objective.py
"""The Objective port — the ONLY thing a consumer must write. Structural (duck-typed) Protocol:
implementers need not inherit it. runtime_checkable isinstance is NAME-only (won't catch a wrong
signature) — used for a shallow CLI guard (cli.py), not a correctness guarantee.

CachedObjective (invariant-prep + per-trial patch, the TC3 pattern) is an Optuna-family extension
that does NOT map to evolve; it lands in Phase 2 with [optuna]."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ruthless.result import Candidate, Metrics


@runtime_checkable
class Objective(Protocol):
    def evaluate(self, candidate: Candidate) -> Metrics: ...
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_objective.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/objective.py tests/test_objective.py
git commit -m "feat: Objective port (structural Protocol; CachedObjective deferred to Phase 2)"
```

---

## Task 5: `backend.py` — ComputeBackend port (+ timeout, H-C) + InProcessBackend (no metric inspection, C-C)

**Files:** Create `ruthless/backend.py`, `tests/test_backend.py`

(BackendPool + SSH/HF-Jobs/Docker → Plan 1B.)

- [ ] **Step 1: Failing test** (backend runs the objective and returns metrics verbatim — it does NOT reject non-finite metrics; that is the strategy's job for the scored metric only — C-C)
```python
# tests/test_backend.py
import math
from ruthless.backend import ComputeBackend, InProcessBackend
from ruthless.result import Candidate


class Good:
    def evaluate(self, candidate: Candidate):
        return {"loss": candidate.params["x"] ** 2, "aux_ratio": math.nan}  # NaN diagnostic is allowed


def test_inprocess_returns_metrics_including_nonfinite_diagnostics():
    b: ComputeBackend = InProcessBackend()
    assert b.available() is True
    m = b.evaluate(Candidate("c", {"x": 2.0}), Good())
    assert m["loss"] == 4.0
    assert math.isnan(m["aux_ratio"])      # backend does NOT police diagnostics (C-C)


def test_evaluate_accepts_timeout_kw():
    # timeout is on the port now (H-C); InProcessBackend documents-and-ignores it.
    assert InProcessBackend().evaluate(Candidate("c", {"x": 1.0}), Good(), timeout=5.0)["loss"] == 1.0
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_backend.py -v`.

- [ ] **Step 3: Implement**
```python
# ruthless/backend.py
"""ComputeBackend port + the in-process backend. A backend is the INTER-candidate dispatch path
(one evaluation → one compute resource). It returns the objective's metrics verbatim — it does NOT
inspect metric values; the strategy validates its own SCORED metric (review C-C). `timeout` is part
of the port from day one (review H-C); InProcessBackend documents-and-ignores it (only the remote
backends in Plan 1B enforce per-candidate timeout + the transient-retry contract)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ruthless.objective import Objective
from ruthless.result import Candidate, Metrics


@runtime_checkable
class ComputeBackend(Protocol):
    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics: ...
    def available(self) -> bool: ...


class InProcessBackend:
    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics:
        # timeout ignored in-process (no cross-process cancellation here); enforced by remote backends in 1B.
        return objective.evaluate(candidate)

    def available(self) -> bool:
        return True
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_backend.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/backend.py tests/test_backend.py
git commit -m "feat: ComputeBackend port (timeout on signature) + InProcessBackend (no metric policing)"
```

---

## Task 6: `strategy.py` — Direction + SearchStrategy port

**Files:** Create `ruthless/strategy.py`, `tests/test_strategy_port.py`

- [ ] **Step 1: Failing test** (structural conformance — M-A)
```python
# tests/test_strategy_port.py
from ruthless.strategy import Direction, SearchStrategy
from ruthless.result import Result


class FakeStrategy:  # NOT inheriting SearchStrategy — structural
    def run(self, objective, *, backend) -> Result:
        return Result(best=None)


def test_direction_values():
    assert Direction.MINIMIZE.value == "minimize" and Direction.MAXIMIZE.value == "maximize"


def test_strategy_structural_conformance():
    s: SearchStrategy = FakeStrategy()
    assert s.run(objective=None, backend=None).best is None
    assert isinstance(s, SearchStrategy)
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_strategy_port.py -v`.

- [ ] **Step 3: Implement**
```python
# ruthless/strategy.py
"""Direction + the SearchStrategy port. Each strategy OWNS its loop (spec C1): it drives the search
and returns a Result. Core imposes no template-method driver; persistence/resume is strategy-internal
(spec H1/C3). report.py renders the returned Result."""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from ruthless.backend import ComputeBackend
from ruthless.objective import Objective
from ruthless.result import Result


class Direction(str, Enum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


@runtime_checkable
class SearchStrategy(Protocol):
    def run(self, objective: Objective, *, backend: ComputeBackend) -> Result: ...
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_strategy_port.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/strategy.py tests/test_strategy_port.py
git commit -m "feat: Direction + SearchStrategy port (strategy owns its loop)"
```

---

## Task 7: `guards.py` — degenerate-candidate penalty (distinct from errors, spec M1)

**Files:** Create `ruthless/guards.py`, `tests/test_guards.py`

- [ ] **Step 1: Failing test**
```python
# tests/test_guards.py
import math
from ruthless.guards import penalty_metrics
from ruthless.strategy import Direction


def test_penalty_minimize_is_large_and_finite():
    m = penalty_metrics("loss", Direction.MINIMIZE, magnitude=1e9)
    assert m["loss"] == 1e9 and math.isfinite(m["loss"])  # recordable, not an error


def test_penalty_maximize_is_small():
    assert penalty_metrics("score", Direction.MAXIMIZE, magnitude=1e9)["score"] == -1e9
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_guards.py -v`.

- [ ] **Step 3: Implement**
```python
# ruthless/guards.py
"""Degenerate-but-evaluable candidates get a recorded penalty score (steers the sampler away). This
is NOT an error — fatal failures live in ruthless.errors and are never recorded (spec M1)."""

from __future__ import annotations

from ruthless.result import Metrics
from ruthless.strategy import Direction


def penalty_metrics(metric: str, direction: Direction, *, magnitude: float = 1e9) -> Metrics:
    """A finite, deliberately-bad score for the given optimisation direction."""
    return {metric: magnitude if direction is Direction.MINIMIZE else -magnitude}
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_guards.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/guards.py tests/test_guards.py
git commit -m "feat: degenerate-candidate penalty scores (recorded; distinct from fatal errors)"
```

---

## Task 8: `parallel.py` — pluggable intra-objective map (spec M3/H4)

**Files:** Create `ruthless/parallel.py`, `tests/test_parallel.py`

- [ ] **Step 1: Failing test**
```python
# tests/test_parallel.py
from ruthless.parallel import map_work_units


def _square(n: int) -> int:
    return n * n


def test_thread_map_preserves_order():
    assert map_work_units(_square, [1, 2, 3, 4], workers=2, executor="thread") == [1, 4, 9, 16]


def test_process_map_preserves_order():
    assert map_work_units(_square, [1, 2, 3], workers=2, executor="process") == [1, 4, 9]
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_parallel.py -v`.

- [ ] **Step 3: Implement**
```python
# ruthless/parallel.py
"""Optional intra-objective parallel map over work-units. NOT the candidate-dispatch path (that is
the backend). A consumer's Objective may call this internally.

GIL caveat: the default "thread" executor only scales for work that releases the GIL
(numpy/pandas/IO). For CPU-bound pure-Python work-units, pass executor="process"."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Literal, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def map_work_units(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    workers: int = 4,
    executor: Literal["thread", "process"] = "thread",
) -> list[R]:
    """Map fn over items in parallel, preserving input order."""
    if workers <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    pool_cls = ThreadPoolExecutor if executor == "thread" else ProcessPoolExecutor
    with pool_cls(max_workers=workers) as pool:
        return list(pool.map(fn, items))
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_parallel.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/parallel.py tests/test_parallel.py
git commit -m "feat: pluggable parallel map utility (thread/process) with GIL caveat"
```

---

## Task 9: `_logging.py` — observability (spec M3)

**Files:** Create `ruthless/_logging.py`, `tests/test_logging.py`

- [ ] **Step 1: Failing test**
```python
# tests/test_logging.py
import logging
from ruthless._logging import get_logger


def test_logger_namespaced_and_no_handlers():
    log = get_logger("strategy")
    assert log.name == "ruthless.strategy"
    assert logging.getLogger("ruthless").handlers == []  # library never configures root/handlers


def test_logger_emits(caplog):
    log = get_logger("strategy")
    with caplog.at_level(logging.INFO, logger="ruthless.strategy"):
        log.info("trial_start")
    assert any(r.message == "trial_start" for r in caplog.records)
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_logging.py -v`.

- [ ] **Step 3: Implement**
```python
# ruthless/_logging.py
"""Observability: namespaced loggers under "ruthless.*". The library NEVER configures root logging
or adds handlers — consumers attach their own (spec M3)."""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ruthless.{name}")
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_logging.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/_logging.py tests/test_logging.py
git commit -m "feat: namespaced ruthless.* loggers (no root config)"
```

---

## Task 10: `config.py` — layered config + extensible param-space union (review H-B)

**Files:** Create `ruthless/config.py`, `tests/test_config.py`

- [ ] **Step 1: Failing test**
```python
# tests/test_config.py
import pytest
from pydantic import ValidationError
from ruthless.config import RuthlessConfig, RandomConfig, FloatRange, IntRange, Choice


def test_loads_random_with_mixed_param_space():
    cfg = RuthlessConfig.model_validate({
        "seed": 7,
        "strategy": {"kind": "random", "n_trials": 50, "direction": "minimize", "metric": "loss",
                     "param_space": {
                         "x": {"kind": "float", "lo": -5.0, "hi": 5.0},
                         "n": {"kind": "int", "lo": 1, "hi": 8},
                         "act": {"kind": "choice", "choices": ["relu", "gelu"]},
                         "lr": {"kind": "float", "lo": 1e-4, "hi": 1e-1, "log": True},
                     }},
    })
    assert isinstance(cfg.strategy, RandomConfig) and cfg.seed == 7
    assert isinstance(cfg.strategy.param_space["x"], FloatRange)
    assert isinstance(cfg.strategy.param_space["n"], IntRange)
    assert isinstance(cfg.strategy.param_space["act"], Choice)
    assert cfg.strategy.param_space["lr"].log is True


def test_unknown_strategy_kind_rejected():
    with pytest.raises(ValidationError):
        RuthlessConfig.model_validate({"strategy": {"kind": "no_such"}})


def test_float_range_bounds_validated():
    with pytest.raises(ValidationError):
        FloatRange.model_validate({"kind": "float", "lo": 5.0, "hi": 1.0})
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_config.py -v`.

- [ ] **Step 3: Implement** (param-space is a discriminated union now — the long-lived contract — even though only RandomSearch consumes it in 1A; evolve/optuna extend the *strategy* union later)
```python
# ruthless/config.py
"""Layered config: a common block + a discriminated STRATEGY union, and a discriminated PARAM-SPACE
union (review H-B: int/choice/log must not force a breaking config change at Phase 2). Phase 1A
registers only the `random` strategy. Persistence is strategy-scoped (spec H1) — added per strategy."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

import yaml
from pydantic import BaseModel, Field, model_validator

from ruthless.strategy import Direction


class FloatRange(BaseModel):
    kind: Literal["float"]
    lo: float
    hi: float
    log: bool = False  # log-uniform sampling (cf. Optuna suggest_float(log=True))

    @model_validator(mode="after")
    def _bounds(self) -> "FloatRange":
        if self.lo >= self.hi:
            raise ValueError(f"FloatRange lo {self.lo} must be < hi {self.hi}")
        if self.log and self.lo <= 0:
            raise ValueError("log FloatRange requires lo > 0")
        return self


class IntRange(BaseModel):
    kind: Literal["int"]
    lo: int
    hi: int

    @model_validator(mode="after")
    def _bounds(self) -> "IntRange":
        if self.lo > self.hi:
            raise ValueError(f"IntRange lo {self.lo} must be <= hi {self.hi}")
        return self


class Choice(BaseModel):
    kind: Literal["choice"]
    choices: list[Any]

    @model_validator(mode="after")
    def _nonempty(self) -> "Choice":
        if not self.choices:
            raise ValueError("Choice requires at least one option")
        return self


ParamSpec = Annotated[Union[FloatRange, IntRange, Choice], Field(discriminator="kind")]


class RandomConfig(BaseModel):
    kind: Literal["random"]
    metric: str
    direction: Direction = Direction.MINIMIZE
    n_trials: int = 50
    param_space: dict[str, ParamSpec] = {}


# Strategy union — evolve/optuna append their configs in later plans.
StrategyConfig = Annotated[Union[RandomConfig], Field(discriminator="kind")]


class RuthlessConfig(BaseModel):
    seed: int = 42
    strategy: StrategyConfig

    @classmethod
    def from_yaml(cls, path: str) -> "RuthlessConfig":
        with open(path) as f:
            return cls.model_validate(yaml.safe_load(f))
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_config.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/config.py tests/test_config.py
git commit -m "feat: layered config + extensible param-space union (float/int/choice/log)"
```

---

## Task 11: `strategies/random_/strategy.py` — RandomSearchStrategy (first SearchStrategy caller)

**Files:** Create `ruthless/strategies/random_/strategy.py`, `tests/test_random_strategy.py`

Validates the `SearchStrategy` port with a real caller and drives the gate (Task 14). It samples each
param per its `ParamSpec` kind and validates only the **scored** metric is finite (C-C).

- [ ] **Step 1: Failing test**
```python
# tests/test_random_strategy.py
import math
import pytest
from ruthless.backend import InProcessBackend
from ruthless.config import RandomConfig
from ruthless.errors import FatalEvaluationError
from ruthless.result import Candidate
from ruthless.strategies.random_.strategy import RandomSearchStrategy


class Quadratic:
    def evaluate(self, candidate: Candidate):
        return {"loss": (candidate.params["x"] - 3.0) ** 2, "aux": math.nan}  # NaN diagnostic OK


class BrokenScore:
    def evaluate(self, candidate: Candidate):
        return {"loss": math.nan}


def _cfg(n=200):
    return RandomConfig.model_validate({"kind": "random", "metric": "loss", "direction": "minimize",
                                        "n_trials": n, "param_space": {"x": {"kind": "float", "lo": -10.0, "hi": 10.0}}})


def test_finds_minimum_and_ignores_nan_diagnostic():
    r = RandomSearchStrategy(_cfg(), seed=42).run(Quadratic(), backend=InProcessBackend())
    assert r.best is not None and abs(r.best.candidate.params["x"] - 3.0) < 0.5 and len(r.history) == 200


def test_deterministic_under_fixed_seed():
    a = RandomSearchStrategy(_cfg(50), seed=42).run(Quadratic(), backend=InProcessBackend())
    b = RandomSearchStrategy(_cfg(50), seed=42).run(Quadratic(), backend=InProcessBackend())
    assert a.best.candidate.params == b.best.candidate.params and a.best.metrics == b.best.metrics


def test_nonfinite_scored_metric_raises():
    with pytest.raises(FatalEvaluationError):
        RandomSearchStrategy(_cfg(1), seed=1).run(BrokenScore(), backend=InProcessBackend())


def test_int_and_choice_sampling():
    cfg = RandomConfig.model_validate({"kind": "random", "metric": "loss", "n_trials": 30,
                                       "param_space": {"n": {"kind": "int", "lo": 1, "hi": 3},
                                                       "a": {"kind": "choice", "choices": ["p", "q"]}}})

    class _Obj:
        def evaluate(self, c):
            return {"loss": float(c.params["n"])}
    r = RandomSearchStrategy(cfg, seed=0).run(_Obj(), backend=InProcessBackend())
    assert all(1 <= e.candidate.params["n"] <= 3 for e in r.history)
    assert all(e.candidate.params["a"] in ("p", "q") for e in r.history)
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_random_strategy.py -v`.

- [ ] **Step 3: Implement**
```python
# ruthless/strategies/random_/strategy.py
"""RandomSearchStrategy — minimal built-in SearchStrategy. First real caller of the port (validates
it before any consumer pins it) and the driver of the dependency-free determinism+convergence gate.
A legitimate zero-dependency baseline; evolve/optuna are separate strategies."""

from __future__ import annotations

import numpy as np

from ruthless._logging import get_logger
from ruthless.backend import ComputeBackend
from ruthless.config import Choice, FloatRange, IntRange, ParamSpec, RandomConfig
from ruthless.errors import classify_metric
from ruthless.objective import Objective
from ruthless.result import Candidate, Evaluation, Result
from ruthless.strategy import Direction

_log = get_logger("strategies.random")


def _sample(spec: ParamSpec, rng: np.random.Generator):
    if isinstance(spec, FloatRange):
        if spec.log:
            return float(np.exp(rng.uniform(np.log(spec.lo), np.log(spec.hi))))
        return float(rng.uniform(spec.lo, spec.hi))
    if isinstance(spec, IntRange):
        return int(rng.integers(spec.lo, spec.hi + 1))  # inclusive hi
    if isinstance(spec, Choice):
        return spec.choices[int(rng.integers(0, len(spec.choices)))]
    raise TypeError(f"unsupported param spec {type(spec).__name__}")


class RandomSearchStrategy:
    def __init__(self, config: RandomConfig, *, seed: int = 42) -> None:
        self._cfg = config
        self._seed = seed
        self._rng = np.random.default_rng(seed)

    def run(self, objective: Objective, *, backend: ComputeBackend) -> Result:
        cfg = self._cfg
        history: list[Evaluation] = []
        best: Evaluation | None = None
        better = (lambda a, b: a < b) if cfg.direction is Direction.MINIMIZE else (lambda a, b: a > b)

        for i in range(cfg.n_trials):
            params = {name: _sample(spec, self._rng) for name, spec in cfg.param_space.items()}
            candidate = Candidate(id=f"r{i}", params=params)
            metrics = backend.evaluate(candidate, objective)
            classify_metric(metrics[cfg.metric], candidate_id=candidate.id, metric=cfg.metric)  # scored only (C-C)
            ev = Evaluation(candidate=candidate, metrics=metrics, ok=True)
            history.append(ev)
            if best is None or better(metrics[cfg.metric], best.metrics[cfg.metric]):
                best = ev
                _log.info("new_best", extra={"trial": i, cfg.metric: metrics[cfg.metric]})

        return Result(best=best, history=history, diagnostics={"n_trials": cfg.n_trials},
                      provenance={"strategy": "random", "seed": self._seed, "direction": cfg.direction.value})
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_random_strategy.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/strategies/random_/strategy.py tests/test_random_strategy.py
git commit -m "feat: RandomSearchStrategy — first SearchStrategy caller; scored-metric finiteness"
```

---

## Task 12: `report.py` — standardized Result rendering (spec L5)

**Files:** Create `ruthless/report.py`, `tests/test_report.py`

- [ ] **Step 1: Failing test**
```python
# tests/test_report.py
import json
from ruthless.report import render_json, render_summary_md
from ruthless.result import Candidate, Evaluation, Result


def _result():
    best = Evaluation(Candidate("r7", {"x": 3.01}), {"loss": 0.0001}, ok=True)
    return Result(best=best, history=[best], diagnostics={"n_trials": 200},
                  provenance={"strategy": "random", "seed": 42})


def test_render_json_roundtrips():
    p = json.loads(render_json(_result()))
    assert p["best"]["candidate"]["params"]["x"] == 3.01 and p["provenance"]["seed"] == 42 and p["n_history"] == 1


def test_render_summary_md():
    md = render_summary_md(_result())
    assert md.startswith("# ") and "0.0001" in md and "random" in md
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_report.py -v`.

- [ ] **Step 3: Implement**
```python
# ruthless/report.py
"""Standardized rendering of a Result → machine JSON + human Markdown SUMMARY. Strategy-specific
artifacts (checkpoint dirs, best_program.py) stay strategy-owned (spec L5)."""

from __future__ import annotations

import json

from ruthless.result import Evaluation, Result


def _eval_dict(ev: Evaluation) -> dict:
    return {"candidate": {"id": ev.candidate.id, "params": ev.candidate.params}, "metrics": ev.metrics, "ok": ev.ok}


def render_json(result: Result) -> str:
    return json.dumps(
        {"best": _eval_dict(result.best) if result.best else None, "n_history": len(result.history),
         "diagnostics": result.diagnostics, "provenance": result.provenance},
        indent=2, default=str,
    )


def render_summary_md(result: Result) -> str:
    lines = ["# Ruthless Efficiency — Run Summary", ""]
    if result.best:
        lines += [f"**Best metrics:** `{result.best.metrics}`",
                  f"**Best params:** `{result.best.candidate.params}`", ""]
    lines += [f"**Trials:** {len(result.history)}", f"**Provenance:** `{result.provenance}`"]
    return "\n".join(lines)
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_report.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/report.py tests/test_report.py
git commit -m "feat: standardized Result rendering (JSON + Markdown SUMMARY)"
```

---

## Task 13: `cli.py` — config-driven entry + trusted import-string loader (spec M2/L3)

**Files:** Create `ruthless/cli.py`, `tests/test_cli.py`, `tests/fixtures/__init__.py`, `tests/fixtures/objectives.py`

- [ ] **Step 1: Fixtures + failing test**

`tests/fixtures/__init__.py`: empty.
`tests/fixtures/objectives.py`:
```python
# tests/fixtures/objectives.py
from ruthless.result import Candidate


class _Quadratic:
    def evaluate(self, candidate: Candidate):
        return {"loss": (candidate.params["x"] - 3.0) ** 2}


quadratic = _Quadratic()
```
```python
# tests/test_cli.py
import pytest
from ruthless.cli import resolve_objective
from ruthless.objective import Objective


def test_resolve_objective_imports_and_checks():
    assert isinstance(resolve_objective("tests.fixtures.objectives:quadratic"), Objective)


def test_resolve_objective_rejects_non_objective():
    with pytest.raises(TypeError):
        resolve_objective("os:getcwd")  # resolves via importlib but is not an Objective
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_cli.py -v`.

- [ ] **Step 3: Implement**
```python
# ruthless/cli.py
"""CLI entry. The objective import-string is a TRUSTED-CONFIG-ONLY convenience: it resolves via
importlib.import_module + getattr (NEVER eval) and is isinstance-checked against Objective (spec L3;
the check is name-only — see objective.py). Programmatic construction is the primary API (spec M2)."""

from __future__ import annotations

import argparse
import importlib

from ruthless.backend import InProcessBackend
from ruthless.config import RandomConfig, RuthlessConfig
from ruthless.objective import Objective
from ruthless.report import render_json, render_summary_md
from ruthless.strategies.random_.strategy import RandomSearchStrategy


def resolve_objective(spec: str) -> Objective:
    module_path, _, attr = spec.partition(":")
    if not attr:
        raise ValueError(f"objective spec must be 'package.module:attr', got {spec!r}")
    obj = getattr(importlib.import_module(module_path), attr)
    if not isinstance(obj, Objective):
        raise TypeError(f"resolved object {spec!r} does not satisfy the Objective protocol")
    return obj


def _build_strategy(cfg: RuthlessConfig):
    if isinstance(cfg.strategy, RandomConfig):
        return RandomSearchStrategy(cfg.strategy, seed=cfg.seed)
    raise ValueError(f"strategy {cfg.strategy.kind!r} not available in this build")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ruthless Efficiency")
    parser.add_argument("--config", required=True)
    parser.add_argument("--objective", required=True, help="trusted import-string 'pkg.mod:attr'")
    args = parser.parse_args()

    cfg = RuthlessConfig.from_yaml(args.config)
    result = _build_strategy(cfg).run(resolve_objective(args.objective), backend=InProcessBackend())
    print(render_json(result))
    print(render_summary_md(result))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/test_cli.py -v`.

- [ ] **Step 5: Commit** (PAUSE)
```bash
git add ruthless/cli.py tests/test_cli.py tests/fixtures/
git commit -m "feat: CLI + trusted import-string objective loader (importlib+getattr+isinstance)"
```

---

## Task 14: Determinism + convergence gate (review H-D — honestly named)

**Files:** Create `tests/e2e/__init__.py`, `tests/e2e/test_determinism_convergence_gate.py`

This is the standing CI gate (spec §8): a deterministic, dependency-free optimisation proving the
orchestration (config → strategy → backend → result → report) works and reproduces under a fixed
seed. **It is NOT a frozen-value golden** — numpy does not guarantee `Generator.uniform` streams
across versions (hence `numpy<3` pin in Task 1); a future frozen-best-params golden would need a
tighter numpy pin. Named for what it is (review H-D).

- [ ] **Step 1: Write the test**
```python
# tests/e2e/test_determinism_convergence_gate.py
"""Standing CI gate (spec §8): deterministic + convergent, zero domain/strategy-extra deps."""

from ruthless.backend import InProcessBackend
from ruthless.config import RuthlessConfig
from ruthless.report import render_json
from ruthless.result import Candidate
from ruthless.strategies.random_.strategy import RandomSearchStrategy


class _Bowl:
    def evaluate(self, candidate: Candidate):
        x, y = candidate.params["x"], candidate.params["y"]
        return {"loss": (x - 2.0) ** 2 + (y + 1.0) ** 2}


def _cfg():
    return RuthlessConfig.model_validate({
        "seed": 123,
        "strategy": {"kind": "random", "metric": "loss", "direction": "minimize", "n_trials": 500,
                     "param_space": {"x": {"kind": "float", "lo": -10.0, "hi": 10.0},
                                     "y": {"kind": "float", "lo": -10.0, "hi": 10.0}}},
    })


def test_converges_and_is_reproducible():
    cfg = _cfg()
    r1 = RandomSearchStrategy(cfg.strategy, seed=cfg.seed).run(_Bowl(), backend=InProcessBackend())
    r2 = RandomSearchStrategy(cfg.strategy, seed=cfg.seed).run(_Bowl(), backend=InProcessBackend())

    # Convergence near the analytic optimum (2, -1)
    assert r1.best.metrics["loss"] < 0.05
    assert abs(r1.best.candidate.params["x"] - 2.0) < 0.4
    assert abs(r1.best.candidate.params["y"] + 1.0) < 0.4

    # Reproducibility under fixed seed (within a numpy version)
    assert render_json(r1) == render_json(r2)
```

- [ ] **Step 2: Run → PASS** — `uv run pytest tests/e2e/test_determinism_convergence_gate.py -v`.

- [ ] **Step 3: Commit** (PAUSE)
```bash
git add tests/e2e/
git commit -m "test: determinism + convergence gate (standing CI gate; numpy-version-coupled)"
```

---

## Task 15: CI workflow + README + full gate

**Files:** Create `.github/workflows/ci.yml`, `README.md`

(No `test_imports_contract.py` — CI's `lint-imports` is the single source of truth; a subprocess
re-check is fragile + redundant — review M-B.)

- [ ] **Step 1: `.github/workflows/ci.yml`** (includes `ruff format --check` — minor review note; pyright on `ruthless` + `tests` via pyproject `include` — M-D)
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install 3.10
      - run: uv pip install --system -e ".[dev]"
      - run: ruff check ruthless tests
      - run: ruff format --check ruthless tests
      - run: pyright
      - run: lint-imports
      - run: pytest -v
```

- [ ] **Step 2: `README.md`** (install lines as a list — no nested code fences, review minor)
```markdown
# Ruthless Efficiency

> "Our chief weapons are Ruthless Efficiency! …and warm-start caching."

A general optimisation/search substrate: a pure hexagonal core + pluggable search strategies
(`random` built-in; `evolve`, `optuna` via extras) + pluggable compute backends.

![hero](assets/ruthless-efficiency.jpg)

## Status

`0.x` — ports are still being validated against real consumers; the API may change until `1.0`.

## Install

- `pip install ruthless-efficiency` — core + random strategy
- `pip install "ruthless-efficiency[optuna]"` — + Optuna strategy (Phase 2)
- `pip install "ruthless-efficiency[evolve]"` — + evolve strategy (our orchestration over OpenEvolve)
- `pip install "ruthless-efficiency[backends]"` — + SSH / HF-Jobs / Docker compute backends
```

- [ ] **Step 3: Run the full gate**

Run: `uv run ruff check ruthless tests && uv run ruff format --check ruthless tests && uv run pyright && uv run lint-imports && uv run pytest -v`
Expected: all green. (If `ruff format --check` flags hand-written blocks, run `uv run ruff format ruthless tests` and re-stage.)

- [ ] **Step 4: Commit** (PAUSE)
```bash
git add .github/workflows/ci.yml README.md
git commit -m "ci: GitHub Actions (ruff/format/pyright/import-linter/pytest) + README"
```

---

## Self-Review

**Review items addressed:**
- **C-A** (evolve = hybrid, our orchestration over OpenEvolve) — resolved in the *spec* (§1/§8/§11); 1A keeps the `evolve = ["openevolve>=0.2.0"]` extra (Task 1) and defers the strategy to 1B. ✔
- **C-B** (dependency order) — tasks reordered errors→result→objective→backend→strategy→guards→parallel→logging→config→random→report→cli→gate→ci; every task independently green. ✔
- **C-C** (scored-metric finiteness only) — backend returns metrics verbatim (Task 5); strategy validates `metrics[cfg.metric]` only (Task 11); NaN diagnostics allowed (tests in 5 + 11). ✔
- **H-A** (Candidate hashable) — frozen + custom `__eq__`/`__hash__` over sorted params; test asserts `hash`, equality, set-dedup (Task 3). ✔
- **H-B** (param-space union) — `FloatRange`/`IntRange`/`Choice` (+ `log` flag) discriminated union; RandomSearch implements all (Tasks 10/11). ✔
- **H-C** (timeout on the port now) — `ComputeBackend.evaluate(..., *, timeout=None)`; InProcessBackend documents-and-ignores (Task 5). ✔
- **H-D** (honest gate name + numpy coupling) — renamed "determinism + convergence gate"; `numpy<3` pin + note (Tasks 1/14). ✔
- **M-A** (structural Protocol) — test fakes do NOT inherit the Protocols; note that runtime_checkable isinstance is name-only (Tasks 4/6/13). ✔
- **M-B** (drop subprocess import test) — removed; CI `lint-imports` is canonical (Task 15). ✔
- **M-C** (Result immutability) — documented mutable-during-build / treat-immutable-after-return (Task 3). ✔
- **M-D** (pyright on tests) — `include = ["ruthless", "tests"]` + bare `pyright` in CI (Tasks 1/15). ✔
- **M-E** (transient-retry contract owner) — noted in `errors.py` as a Plan 1B responsibility (Task 2). ✔
- **Minors** — pyyaml in Task 1 pyproject; `ruff format` in CI + gate; README without nested fences; seed flows `RuthlessConfig.seed → strategy ctor` via `_build_strategy` (Task 13) and is recorded in `Result.provenance` (Task 11). ✔

**Placeholder scan:** none — every code step shows full content; every command has an expected outcome.

**Type consistency:** `Candidate(id, params)` (hashable), `Evaluation(candidate, metrics, ok)`, `Result(best, history, diagnostics, provenance)`, `Metrics=dict[str,float]`, `Objective.evaluate(candidate)->Metrics`, `ComputeBackend.evaluate(candidate, objective, *, timeout=None)->Metrics` + `available()`, `SearchStrategy.run(objective, *, backend)->Result`, `Direction.{MINIMIZE,MAXIMIZE}`, `FloatRange/IntRange/Choice`/`ParamSpec`, `RandomConfig(kind, metric, direction, n_trials, param_space)`, `RuthlessConfig(seed, strategy)`, `classify_metric(value, *, candidate_id, metric)`, `penalty_metrics(metric, direction, *, magnitude)` — consistent across Tasks 2–14.

**Spec back-port already applied:** `RandomSearchStrategy` is in spec §4/§9.

---

## Execution Deviations (rev 2 → as-shipped, 2026-05-28)

Four issues surfaced when running the full gate (`ruff` / `ruff format` / `pyright` / `lint-imports` /
`pytest`) on Python 3.10.19 + numpy 2.2.6 + pydantic 2.13.4. All were defects in the rev-2 code/test
blocks above, fixed during execution; the shipped code is the source of truth where it differs.

1. **`config.py` — ruff UP007/UP037.** With `from __future__ import annotations`, ruff flagged the
   quoted return annotations (`-> "FloatRange"` etc.) and the `Union[...]` aliases. Auto-fixed to
   unquoted forward refs and PEP-604 `X | Y` unions: `ParamSpec = Annotated[FloatRange | IntRange |
   Choice, Field(discriminator="kind")]` and `StrategyConfig = Annotated[RandomConfig,
   Field(discriminator="kind")]`. Runtime-equivalent (`Union[RandomConfig]` already collapses to
   `RandomConfig`); all config tests still pass.

2. **`.importlinter` — `root_packages`.** import-linter 2.x mis-parsed the single-line
   `root_packages = ruthless` (iterated it character-by-character → "Could not find package 'r'").
   Switched to the canonical multiline list form. Now: "Contracts: 2 kept, 0 broken."

3. **Tests — pyright cleanliness (honours M-D: pyright runs on `tests`).** The rev-2 test blocks were
   not pyright-clean. Semantics-preserving fixes: added `assert <result>.best is not None` before
   `Optional[Evaluation]` member access (`test_result.py`, `test_random_strategy.py`, the gate);
   narrowed the param-space union with `isinstance(lr, FloatRange)` before reading `.log`
   (`test_config.py`); renamed `_Obj.evaluate(self, c)` → `(self, candidate)` to satisfy the
   `Objective` protocol's parameter name. Now: 0 errors.

4. **Determinism gate — statistically-sound thresholds.** The rev-2 convergence assertions
   (`loss < 0.05`, params within `0.4`) cannot be reliably met by pure random search: best-of-500
   uniform samples over a 20×20 box averages ~0.25 loss with high variance (seed=123/numpy 2.2.6
   yields ~0.44). Loosened to `loss < 2.0` and params within `1.5` — still ~35× better than the
   uniform-random expectation (~70), so it proves convergence, while staying robust to seed/numpy
   drift (cf. the H-D note + the `numpy<3` pin). The exact-match reproducibility assertion
   (`render_json(r1) == render_json(r2)`) is unchanged. The strategy itself is correct — the 1D unit
   convergence test (`test_finds_minimum_and_ignores_nan_diagnostic`) passes as written.

5. **CI workflow — `--system` install fails on the runner.** The rev-2 `ci.yml` ran
   `uv pip install --system -e ".[dev]"`, which targets the runner's PEP 668 externally-managed
   `/usr` Python 3.12 (uv refuses to install there) and ignores the `uv python install 3.10` step
   entirely — the first push's CI failed in 14s. Fixed to the venv flow that matches local dev and
   CONTRIBUTING.md: `uv venv --python 3.10` → `uv pip install -e ".[dev]"` → `uv run <tool>` for each
   gate step. This also guarantees CI runs on 3.10 (the determinism gate's numpy/RNG target).

**As-shipped gate (local, Python 3.10.19):** ruff clean · ruff format clean (31 files) · pyright 0
errors · import-linter 2 kept / 0 broken · pytest 30 passed. CI mirrors this via the venv flow above.
