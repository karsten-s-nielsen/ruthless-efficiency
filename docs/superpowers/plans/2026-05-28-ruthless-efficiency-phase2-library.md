# Ruthless Efficiency — Phase 2 (library side: Optuna) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** rev 3 — incorporates the silly-kicks-session round-2 review (R1 delete the leftover Task O4, R2 unused-import, R3 split the O6 test file, R4 drop the private-API SQLite poke, R5 enforce patch-param-exercised, R6/R7 doc caveats, R8 changelog wording, + the DRY nit dropping the duplicate union-load test). rev 2 incorporated the round-1 review (B1/B2/B3/M1–M5/minors). Pending the next review round before execution.

**Review changelog (rev 2 → rev 3):**
- **R1 (blocking):** the leftover **Task O4 section is deleted** (the doc previously told a task-by-task worker to build the very `scoring.group_stratified_cv` it said it dropped); the Task Z `/final-review` C4 line no longer says "add scoring".
- **R2:** removed the unused `import pytest` from the O5 test (would fail `ruff check` F401 in the Z gate).
- **R3:** O6's integration tests live in a **separate file** `tests/strategies/optuna/test_optuna_cached.py` (O2's unit file keeps its own minimal imports) — every checkpoint stays ruff-clean (no E402↔F401 churn).
- **R4:** dropped the private-API `study._storage.remove_session()` poke from O7 (unstable across Optuna 4.x; CI is ubuntu-only).
- **R5:** `assert_cache_equivalence` now **enforces** that ≥2 candidates vary every patch_param (raises otherwise) — turns the M3 documented contract into a checked one; `_OverDeclared` test adjusted to vary both params.
- **R6/R7:** caveats added — reconstructed history is always `ok=True` (Optuna doesn't persist the 1A flag; filter by metric); a fatal trial permanently consumes an `n_trials` slot and isn't retried on resume (`n_complete` < `n_trials`).
- **R8 + DRY nit:** changelog reworded (hypothesis test proves no-false-positive; `_OverDeclared`+R5 catch over-declaration); dropped the duplicate `test_random_still_loads_via_union` (test_config.py already owns it).

**Review changelog (rev 1 → rev 2):**
- **B1 (resume best/history):** `OptunaStrategy.run` now derives `best` from `study.best_trial` and **reconstructs `history` from `study.trials`** (params + per-trial metrics persisted in `user_attrs`), so `best`/`history`/`n_trials` all span the store on resume (O5/O7).
- **B2 (warm-start duplicate):** `enqueue_trial` only on a fresh study (`len(study.trials) == 0`) (O5).
- **B3 + M5 (CI):** follow the shipped CI structure — extend the `test` job to `.[dev,backends,evolve,optuna]`; `core-lean --ignore` gains `tests/strategies/optuna` + `tests/e2e/test_optuna_resume_gate.py` (O0). No nonexistent "per-extra legs".
- **M1 (scoring dropped):** `scoring.group_stratified_cv` is **removed from Phase 2** (the named consumer uses StratifiedGroupKFold internally and can run CV inside its own `score_fn`; the rev-1 design was neither properly stratified nor grouped). A correctly-designed scoring helper can land later when a consumer needs it. Removes Task O4 + the `scikit-learn` dep + M8/m6.
- **M2 + M3 (cache-equivalence rigor):** O3 adds a **hypothesis** property test that sweeps every `patch_param`'s range against a CORRECT trivial `CachedObjective` (proves no false-positive across the range); a separate hand-written `_OverDeclared` test proves the harness CATCHES a patch_param that actually affects the invariant; and (R5) `assert_cache_equivalence` now ENFORCES that candidates vary every patch_param (raises if one is held constant), turning the documented contract into a checked one.
- **M4:** `ruthless.testing` added to the `core-isolation` import-linter contract.
- **minors:** imports at file top (m1); `assert_cache_equivalence` gets a separate `atol` + NaN-both-equal handling + raises on key-mismatch (m2); resume gate asserts trial-id contiguity (m3); fatal-trial-aborts-study contract documented (m4); `OptunaConfig` validates `warm_start ⊆ param_space` (m5); `direction = cfg.direction.value` (m7); SQLite-dispose-on-Windows noted (m9).

**Goal:** Add the `[optuna]` half of the substrate — `OptunaStrategy` (resumable Bayesian/sampler calibration on the `SearchStrategy` port) and the `CachedObjective` invariant-prep/per-trial-patch port + `ruthless.testing.assert_cache_equivalence` harness — so **silly-kicks can run its own Optuna calibrations through ruthless** (the first consumer; lakehouse/TC3 later). (A group-scoring utility is intentionally NOT shipped this phase — see the changelog/M1.)

**Architecture:** Hexagonal, unchanged. `OptunaStrategy` (`ruthless/strategies/optuna_/`, `[optuna]`) wraps an Optuna study (ask via `study.optimize` callback; resume via `create_study(load_if_exists=True)` + a remaining-trials guard), maps the 1A `ParamSpec` union to `trial.suggest_*`, validates only the scored metric, and returns the unified `Result`. `CachedObjective` (a pure core Protocol, no optuna dep) generalises the TC3 invariant-cache/patch decomposition: an objective that exposes a full `evaluate(candidate)` (the 1A port) **plus** `prepare() -> Invariant` (expensive, once) + `evaluate_patch(invariant, candidate) -> Metrics` (cheap, per-trial) + `patch_params`. `OptunaStrategy` uses the fast path for a `CachedObjective` and asserts every tuned param is a declared patch param (H1/M5).

**Tech Stack:** Python ≥3.10, pydantic v2, numpy, pyyaml (core). `[optuna]` adds `optuna>=4`. Tests: pytest + hypothesis (the cache-equivalence property test).

**Spec:** `docs/superpowers/specs/2026-05-28-optimization-engine-carveout-design.md` (rev 3), §9 Phase 2 (library side; the TC3 *migration* is the consumer's job, deferred).

**Extraction source (read-only oracle):** lakehouse `D:\Development\karstenskyt__luxury-lakehouse\scripts\run_tc3_calibration.py` (the generic Optuna orchestration; identical in the `-d32` clone). Phase 2 library code is mostly **new abstraction** (ports + utilities generalising TC3's domain-coupled functions), not a verbatim port — the TC3 functions (`_enrich_match_invariant`, `_patch_trial_columns`, `_compute_provider_brier`) stay in the consumer as concrete implementations.

**Working directory:** ruthless repo root. No worktrees (project convention) — a feature branch. `/final-review` is the pre-commit gate. One commit/PR after the full gate + final-review (per the repo's commit-workflow rule).

**Determinism / resume posture (spec C3, §11 — load-bearing):** Optuna does **not** persist sampler RNG state across restart, so a resumed TPE study does **not** reproduce an uninterrupted run trial-for-trial. The `OptunaStrategy` resume contract is the *achievable* one: **no lost or duplicate trials, monotone study growth, convergence within tolerance** — asserted in the gate; trajectory-identity is explicitly NOT promised. **SQLite storage is single-process-safe only**; concurrent dispatch over a backend pool (not built here — YAGNI) requires an RDB (Postgres) — documented at the config boundary.

**Out of scope (deferred):** TC3 domain migration (lakehouse); silly-kicks objective authoring (the consumer-adoption step that follows this plan); multi-backend Optuna dispatch (§10 — ship the in-process path, not a forced backend integration); pruners/multi-objective (no TC3 caller).

---

## Central design decisions

### 1. `OptunaStrategy` on the 1A `SearchStrategy` port
`run(self, objective, *, backend) -> Result`. It owns its loop via Optuna's `study.optimize(callback, n_trials=remaining)`. The `backend` is used to dispatch each trial's evaluation (default `InProcessBackend` → `objective.evaluate(candidate)`); a `CachedObjective` short-circuits the backend for the fast path (prepare once in-process, then `evaluate_patch` per trial — see decision 3). Resume: `optuna.create_study(study_name, storage="sqlite:///<path>", sampler=TPESampler(seed), direction, load_if_exists=True)`, then `remaining = n_trials - len(study.trials)`; only `remaining` trials are requested. Warm-start: `study.enqueue_trial(warm_start)` before `optimize`. The scored metric is validated with `classify_metric` (1A); a degenerate candidate is the consumer's responsibility to return as `guards.penalty_metrics` (recorded, steers the sampler).

### 2. `CachedObjective` — invariant-prep / per-trial-patch (a pure core Protocol; spec §4, H1)
```python
# ruthless/objective.py  (core — NO optuna/sklearn import)
@runtime_checkable
class CachedObjective(Protocol):
    """An Objective whose expensive work is invariant across the tuned params, with a cheap per-trial
    patch. The consumer implements BOTH the full path (evaluate, the 1A port) and the fast path
    (prepare once + evaluate_patch per candidate); assert_cache_equivalence proves they agree.

    `patch_params` declares the ONLY params a trial may vary — everything else feeds the invariant.
    A param tuned but NOT in patch_params would change the invariant yet reuse the cached one => a
    silent wrong score; OptunaStrategy rejects that at construction (H1/M5)."""

    patch_params: frozenset[str]

    def evaluate(self, candidate: Candidate) -> Metrics: ...                       # full recompute (1A Objective)
    def prepare(self) -> object: ...                                               # build the invariant once
    def evaluate_patch(self, invariant: object, candidate: Candidate) -> Metrics: ...  # cheap per-trial
```
The TC3 mapping (consumer-side, not built here): `prepare` ≈ `_invariant_worker` (cache the enriched-base parquet per match), `evaluate_patch` ≈ `_patch_worker` (`_patch_trial_columns` → score), `patch_params` ≈ `{"k3","pre_seconds","min_displacement_m"}`.

### 3. `OptunaStrategy` × `CachedObjective` integration (H1/M5)
At construction, if the objective is a `CachedObjective`, assert `set(cfg.param_space) <= objective.patch_params` (every tuned param is a declared patch param — the safety direction; a loud config error, never a silent wrong score). At `run`, call `prepare()` once, then per trial call `evaluate_patch(invariant, candidate)`. A plain `Objective` uses the full `backend.evaluate(candidate, objective)` path per trial.

### 4. `ruthless.testing.assert_cache_equivalence` (shipped for consumers; spec §8)
`assert_cache_equivalence(objective, candidates, *, rtol=1e-9)` — `inv = objective.prepare()`; for each candidate assert `evaluate_patch(inv, c)` ≈ `evaluate(c)` (per-metric, within rtol). Raises `AssertionError` naming the first divergent candidate+metric. Consumers call it in their own suites against their domain objective; the substrate's own property test runs it against a trivial in-repo objective.

### 5. Group-scoring utility — DEFERRED (M1)
The rev-1 `scoring.group_stratified_cv` is **not shipped this phase**. It was neither properly stratified nor properly grouped (it nested a synthetic inner partition), and the named consumer (silly-kicks) uses `StratifiedGroupKFold` over match groups and can run CV inside its own objective's `score_fn`/`evaluate`. A correctly-designed helper (a single `StratifiedGroupKFold`/`GroupKFold` pass over the caller's real groups, returning per-fold scores) can land when a consumer actually needs it. This drops the `scikit-learn` dependency from `[optuna]`.

---

## File Structure

```
ruthless/
  objective.py        # MODIFY: + CachedObjective Protocol (no new deps)
  config.py           # MODIFY: + OptunaConfig (kind="optuna") in the strategy union; + StoreConfig
  testing.py          # NEW: assert_cache_equivalence harness (pure; no optuna)
  strategies/
    optuna_/          # NEW  [extra: optuna]
      __init__.py
      strategy.py     # OptunaStrategy(SearchStrategy): study/resume/warm-start/suggest/penalty/Result
tests/
  test_optuna_config.py  test_assert_cache_equivalence.py
  strategies/optuna/  test_optuna_strategy.py  test_cached_objective.py
  e2e/  test_optuna_resume_gate.py
pyproject.toml  .github/workflows/ci.yml
```

**Dependency order:** O0 pyproject/CI → O1 config (OptunaConfig) → O2 CachedObjective port → O3 testing.assert_cache_equivalence (+ hypothesis property test) → O5 OptunaStrategy (plain objective) → O6 OptunaStrategy×CachedObjective → O7 resume gate → Z gate/final-review/PR. (No O4 — group-scoring deferred, M1.)

---

## Task O0: pyproject `[optuna]` extra + CI leg

**Files:** Modify `pyproject.toml`, `.github/workflows/ci.yml`

- [ ] **Step 1:** In `pyproject.toml`, the optuna extra is optuna-only (no scikit-learn — scoring deferred, M1):
```toml
optuna = ["optuna>=4.0"]    # Phase 2: OptunaStrategy + CachedObjective
```
- [ ] **Step 2:** Follow the SHIPPED `ci.yml` structure (one `test` job + one `core-lean` job — there are no per-extra legs). (a) Extend the `test` job install to `uv pip install -e ".[dev,backends,evolve,optuna]"`. (b) The `core-lean` job (installs only `.[dev]`, runs `pytest -v` minus an `--ignore` list) gains TWO ignores so the optuna-importing tests aren't collected under the lean install: `--ignore=tests/strategies/optuna` AND `--ignore=tests/e2e/test_optuna_resume_gate.py`. (`tests/test_optuna_config.py` and `tests/test_assert_cache_equivalence.py` stay in core-lean — `config.py`/`testing.py` import no optuna; verified.)
- [ ] **Step 3: Verify** — `uv pip install -e ".[dev,optuna]"` resolves; `uv run python -c "import optuna; print(optuna.__version__)"`. (import-linter: `optuna_` is under `strategies`, covered by `strategy-isolation`; the new core module `ruthless.testing` is added to `core-isolation` in Task O3.)
- [ ] **Step 4: Commit (PAUSE — single commit at end per repo rule; treat as checkpoint).**

---

## Task O1: `config.py` — OptunaConfig + StoreConfig

**Files:** Modify `ruthless/config.py`, Create `tests/test_optuna_config.py`

- [ ] **Step 1: Failing test**
```python
# tests/test_optuna_config.py
import pytest
from pydantic import ValidationError
from ruthless.config import OptunaConfig, RuthlessConfig, StoreConfig
from ruthless.strategy import Direction


def test_loads_optuna_with_param_space_and_store():
    cfg = RuthlessConfig.model_validate({
        "seed": 7,
        "strategy": {
            "kind": "optuna", "metric": "loss", "direction": "minimize", "n_trials": 100,
            "sampler": "tpe",
            "param_space": {"x": {"kind": "float", "lo": -5.0, "hi": 5.0},
                            "k3": {"kind": "float", "lo": 0.1, "hi": 5.0, "log": True}},
            "warm_start": {"x": 0.0, "k3": 1.0},
            "store": {"kind": "sqlite", "path": "results/study.db"},
        },
    })
    assert isinstance(cfg.strategy, OptunaConfig)
    assert cfg.strategy.direction is Direction.MINIMIZE
    assert cfg.strategy.store.kind == "sqlite" and cfg.strategy.warm_start["k3"] == 1.0


def test_optuna_defaults_in_memory_store():
    cfg = OptunaConfig.model_validate({"kind": "optuna", "metric": "loss", "param_space": {}})
    assert cfg.store is None and cfg.sampler == "tpe" and cfg.n_trials == 50


def test_warm_start_key_not_in_param_space_rejected():
    with pytest.raises(ValidationError, match="warm_start"):
        OptunaConfig.model_validate({
            "kind": "optuna", "metric": "loss",
            "param_space": {"x": {"kind": "float", "lo": 0.0, "hi": 1.0}},
            "warm_start": {"typo_key": 0.5},   # not a param_space key
        })
```
- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_optuna_config.py -v`.
- [ ] **Step 3: Implement** — add to `ruthless/config.py` (reusing the 1A `ParamSpec`/`Direction`):
```python
class StoreConfig(BaseModel):
    kind: Literal["sqlite"] = "sqlite"   # only sqlite in Phase 2 (single-process resume; RDB is §10/later)
    path: str


class OptunaConfig(BaseModel):
    kind: Literal["optuna"]
    metric: str
    direction: Direction = Direction.MINIMIZE
    n_trials: int = 50
    sampler: Literal["tpe", "random"] = "tpe"
    param_space: dict[str, ParamSpec] = {}
    warm_start: dict[str, Any] = {}          # enqueued as the forced first trial (baseline)
    store: StoreConfig | None = None         # None => in-memory study (no resume)

    @model_validator(mode="after")
    def _warm_start_keys(self) -> "OptunaConfig":
        extra = set(self.warm_start) - set(self.param_space)
        if extra:  # m5: a typo'd warm-start key would be silently ignored by Optuna — fail loudly
            raise ValueError(f"warm_start keys {sorted(extra)} are not in param_space")
        return self
```
(`model_validator` is already imported in `config.py`.)
and extend the union: `StrategyConfig = Annotated[RandomConfig | EvolveConfig | OptunaConfig, Field(discriminator="kind")]`.
- [ ] **Step 4: Run → PASS** (+ existing config tests stay green).
- [ ] **Step 5: Commit (checkpoint).**

---

## Task O2: `objective.py` — CachedObjective Protocol

**Files:** Modify `ruthless/objective.py`, Create `tests/strategies/optuna/__init__.py`, `tests/strategies/optuna/test_cached_objective.py`

- [ ] **Step 1: Failing test** (structural conformance; a trivial cached objective)
```python
# tests/strategies/optuna/test_cached_objective.py  (O2 unit tests; O6 integration lives in a SEPARATE file)
from ruthless.objective import CachedObjective
from ruthless.result import Candidate


class _SumCached:  # NOT inheriting the Protocol — structural
    patch_params = frozenset({"a", "b"})

    def evaluate(self, candidate):           # full recompute
        return {"loss": float(candidate.params["a"] + candidate.params["b"])}

    def prepare(self):                       # invariant = a constant offset
        return {"offset": 10.0}

    def evaluate_patch(self, invariant, candidate):
        return {"loss": float(candidate.params["a"] + candidate.params["b"])}


def test_cached_objective_structural_conformance():
    obj: CachedObjective = _SumCached()
    assert isinstance(obj, CachedObjective)
    inv = obj.prepare()
    c = Candidate("c", {"a": 1.0, "b": 2.0})
    assert obj.evaluate_patch(inv, c)["loss"] == 3.0 == obj.evaluate(c)["loss"]
    assert obj.patch_params == {"a", "b"}
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement** — add `CachedObjective` to `ruthless/objective.py` exactly as in "Central design decision 2" (runtime_checkable Protocol; imports only `Candidate, Metrics` from `ruthless.result`). No optuna/sklearn import — it stays core.
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit (checkpoint).**

---

## Task O3: `testing.py` — assert_cache_equivalence

**Files:** Create `ruthless/testing.py`, `tests/test_assert_cache_equivalence.py`

- [ ] **Step 1: Failing test**
```python
# tests/test_assert_cache_equivalence.py
import pytest
from hypothesis import given
from hypothesis import strategies as st

from ruthless.result import Candidate
from ruthless.testing import assert_cache_equivalence

_PATCH = frozenset({"a", "b"})


class _Good:  # fast path == full recompute; invariant does NOT depend on a/b (correct)
    patch_params = _PATCH
    def evaluate(self, c): return {"loss": c.params["a"] ** 2 + c.params["b"]}
    def prepare(self): return {"offset": 0.0}
    def evaluate_patch(self, inv, c): return {"loss": c.params["a"] ** 2 + c.params["b"] + inv["offset"]}


class _Broken:  # fast path disagrees with full recompute
    patch_params = frozenset({"a"})
    def evaluate(self, c): return {"loss": c.params["a"] ** 2}
    def prepare(self): return None
    def evaluate_patch(self, inv, c): return {"loss": c.params["a"]}  # WRONG


class _OverDeclared:  # 'b' is declared a patch_param but actually feeds the (stale) invariant -> H1 bug
    patch_params = _PATCH
    def evaluate(self, c): return {"loss": c.params["a"] + c.params["b"]}            # full sees current b
    def prepare(self): return {"b_at_prepare": 0.0}                                  # invariant froze b=0
    def evaluate_patch(self, inv, c): return {"loss": c.params["a"] + inv["b_at_prepare"]}  # ignores current b


def test_equivalence_passes_for_consistent_objective():
    cands = [Candidate(f"c{i}", {"a": float(i), "b": float(-i)}) for i in range(5)]
    assert_cache_equivalence(_Good(), cands)  # no raise


def test_equivalence_raises_for_divergent_objective():
    with pytest.raises(AssertionError, match="loss"):
        assert_cache_equivalence(_Broken(), [Candidate("c", {"a": 3.0})])


def test_over_declared_patch_param_caught_when_varied():
    # M3/H1: 'b' is over-declared (it feeds the invariant); caught because candidates vary b. Both a
    # and b vary, so the R5 "exercised" check passes and the real failure is the loss mismatch.
    cands = [Candidate("c0", {"a": 1.0, "b": 0.0}), Candidate("c1", {"a": 2.0, "b": 9.0})]
    with pytest.raises(AssertionError, match="loss"):
        assert_cache_equivalence(_OverDeclared(), cands)


@given(a=st.floats(-1e3, 1e3, allow_nan=False), b=st.floats(-1e3, 1e3, allow_nan=False))
def test_equivalence_property_over_sampled_candidates(a, b):
    # M2: hypothesis sweeps the full range of every patch_param against a correct cached objective.
    assert_cache_equivalence(_Good(), [Candidate("c", {"a": a, "b": b})])
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement**
```python
# ruthless/testing.py
"""Consumer-facing test harness: prove a CachedObjective's fast path (prepare + evaluate_patch)
equals its full recompute (evaluate) for sampled candidates. The substrate cannot test consumer
correctness — the consumer calls this in its own suite (spec §8/H1)."""
from __future__ import annotations
import math
from collections.abc import Sequence
from ruthless.objective import CachedObjective
from ruthless.result import Candidate


def assert_cache_equivalence(
    objective: CachedObjective, candidates: Sequence[Candidate], *, rtol: float = 1e-9, atol: float = 1e-12
) -> None:
    """Raise AssertionError if the fast path diverges from the full recompute for any candidate.

    IMPORTANT (H1): `candidates` MUST collectively vary EVERY param in `objective.patch_params`
    across its range. An over-declared patch_param (one that actually affects the invariant) is only
    caught when candidates exercise it — otherwise a stale-invariant bug slips through. The substrate
    property test (test_assert_cache_equivalence.py) auto-varies each patch_param; consumers should
    pass candidates that sweep each patch_param (e.g. boundary + interior values).

    The contract is ENFORCED (R5): with >= 2 candidates, every patch_param MUST take >= 2 distinct
    values across `candidates`, else this raises — so an over-declared patch_param can't slip through
    by a consumer holding it constant."""
    cands = list(candidates)
    if len(cands) >= 2:
        for pp in objective.patch_params:
            values = {c.params.get(pp) for c in cands}
            if len(values) < 2:
                raise AssertionError(
                    f"patch_param {pp!r} is not exercised: all candidates share value {next(iter(values))!r}. "
                    f"assert_cache_equivalence requires candidates to vary every patch_param across its range."
                )
    invariant = objective.prepare()
    for c in cands:
        full = objective.evaluate(c)
        fast = objective.evaluate_patch(invariant, c)
        if full.keys() != fast.keys():
            raise AssertionError(f"metric keys differ for {c.id}: {sorted(full)} vs {sorted(fast)}")
        for k in full:
            a, b = full[k], fast[k]
            if math.isnan(a) and math.isnan(b):
                continue  # both paths agree the metric is NaN (e.g. a diagnostic) — not a mismatch
            if not math.isclose(a, b, rel_tol=rtol, abs_tol=atol):
                raise AssertionError(f"cache mismatch for {c.id} metric {k!r}: full={a!r} != patch={b!r}")
```
- [ ] **Step 3b (M4): guard the new core module.** Append `ruthless.testing` to the `core-isolation` contract's `source_modules` list in `.importlinter` (it is core and must not import `strategies`/`backends`). Run `uv run lint-imports` → "Contracts: 3 kept".
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit (checkpoint).**

---

## Task O5: `OptunaStrategy` — study, resume, warm-start, suggest, Result (plain Objective)

**Files:** Create `ruthless/strategies/optuna_/__init__.py` (empty), `ruthless/strategies/optuna_/strategy.py`, `tests/strategies/optuna/test_optuna_strategy.py`

- [ ] **Step 1: Failing tests** (analytic quadratic; deterministic-ish best within tolerance; warm-start enqueued first)
```python
# tests/strategies/optuna/test_optuna_strategy.py
from ruthless.backend import InProcessBackend
from ruthless.config import OptunaConfig
from ruthless.result import Candidate
from ruthless.strategies.optuna_.strategy import OptunaStrategy


class Quadratic:
    def evaluate(self, candidate: Candidate):
        return {"loss": (candidate.params["x"] - 3.0) ** 2}


def _cfg(n=60, **kw):
    return OptunaConfig.model_validate(
        {"kind": "optuna", "metric": "loss", "direction": "minimize", "n_trials": n,
         "param_space": {"x": {"kind": "float", "lo": -10.0, "hi": 10.0}}, **kw}
    )


def test_optuna_finds_minimum():
    r = OptunaStrategy(_cfg(), seed=42).run(Quadratic(), backend=InProcessBackend())
    assert r.best is not None and abs(r.best.candidate.params["x"] - 3.0) < 1.0 and len(r.history) == 60


def test_warm_start_is_first_trial():
    r = OptunaStrategy(_cfg(n=5, warm_start={"x": 7.5}), seed=1).run(Quadratic(), backend=InProcessBackend())
    assert r.history[0].candidate.params["x"] == 7.5  # enqueued baseline runs first


def test_int_and_choice_suggested():
    cfg = OptunaConfig.model_validate(
        {"kind": "optuna", "metric": "loss", "n_trials": 20,
         "param_space": {"n": {"kind": "int", "lo": 1, "hi": 4},
                         "a": {"kind": "choice", "choices": ["p", "q"]}}}
    )
    class _Obj:
        def evaluate(self, c): return {"loss": float(c.params["n"])}
    r = OptunaStrategy(cfg, seed=0).run(_Obj(), backend=InProcessBackend())
    assert all(1 <= e.candidate.params["n"] <= 4 for e in r.history)
    assert all(e.candidate.params["a"] in ("p", "q") for e in r.history)
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement**
```python
# ruthless/strategies/optuna_/strategy.py
"""OptunaStrategy — resumable Bayesian/sampler calibration on the SearchStrategy port. Owns its loop
via study.optimize; resume = create_study(load_if_exists=True) + a remaining-trials guard (spec C3:
no lost/dup trials + monotone growth + converge; NOT trajectory-identity). Maps the 1A ParamSpec
union to trial.suggest_*; validates only the scored metric; records each trial into the Result."""
from __future__ import annotations

from typing import Any

from ruthless._logging import get_logger
from ruthless.backend import ComputeBackend
from ruthless.config import Choice, FloatRange, IntRange, OptunaConfig, ParamSpec
from ruthless.errors import classify_metric
from ruthless.objective import CachedObjective, Objective
from ruthless.result import Candidate, Evaluation, Result
from ruthless.strategy import Direction

_log = get_logger("strategies.optuna")


def _suggest(trial: Any, name: str, spec: ParamSpec) -> Any:
    if isinstance(spec, FloatRange):
        return trial.suggest_float(name, spec.lo, spec.hi, log=spec.log)
    if isinstance(spec, IntRange):
        return trial.suggest_int(name, spec.lo, spec.hi)
    if isinstance(spec, Choice):
        return trial.suggest_categorical(name, spec.choices)
    raise TypeError(f"unsupported param spec {type(spec).__name__}")


class OptunaStrategy:
    def __init__(self, config: OptunaConfig, *, seed: int = 42) -> None:
        self._cfg = config
        self._seed = seed

    def run(self, objective: Objective, *, backend: ComputeBackend) -> Result:
        import optuna

        cfg = self._cfg
        cached = isinstance(objective, CachedObjective)
        if cached:
            extra = set(cfg.param_space) - objective.patch_params
            if extra:  # H1/M5: tuning a non-patch param would change the cached invariant -> wrong score
                raise ValueError(f"param_space keys {sorted(extra)} are not in objective.patch_params")
            invariant = objective.prepare()

        sampler = (optuna.samplers.TPESampler(seed=self._seed) if cfg.sampler == "tpe"
                   else optuna.samplers.RandomSampler(seed=self._seed))
        direction = cfg.direction.value   # m7: "minimize"/"maximize" (matches random_/strategy.py)
        storage = f"sqlite:///{cfg.store.path}" if cfg.store else None
        study = optuna.create_study(
            study_name=cfg.store.path if cfg.store else "ruthless-optuna",
            storage=storage, sampler=sampler, direction=direction, load_if_exists=True,
        )
        if cfg.warm_start and len(study.trials) == 0:   # B2: enqueue the baseline ONLY on a fresh study
            study.enqueue_trial(cfg.warm_start)

        def _objective(trial: Any) -> float:
            params = {name: _suggest(trial, name, spec) for name, spec in cfg.param_space.items()}
            candidate = Candidate(id=f"t{trial.number}", params=params)
            metrics = (objective.evaluate_patch(invariant, candidate) if cached
                       else backend.evaluate(candidate, objective))
            # m4/R7: a non-finite SCORED metric raises FatalEvaluationError here; Optuna does NOT catch
            # it (default catch=()), so it propagates out of run() and aborts the study. The aborted
            # trial is recorded FAILED in the store and PERMANENTLY consumes an n_trials slot — on
            # resume `remaining = n_trials - len(study.trials)` counts it and does NOT retry it, so
            # `n_complete` can be < n_trials (surfaced in diagnostics). That is intentional: a fatal
            # eval is a broken candidate, not a transient — don't loop on it. (Degenerate-but-valid
            # candidates use guards.penalty_metrics, which is FINITE, so they record COMPLETE and
            # steer the sampler — they do not abort.)
            classify_metric(metrics[cfg.metric], candidate_id=candidate.id, metric=cfg.metric)
            for k, v in metrics.items():
                trial.set_user_attr(k, v)   # persisted in the store -> lets resume reconstruct history (B1)
            return metrics[cfg.metric]

        remaining = max(0, cfg.n_trials - len(study.trials))
        if remaining:
            study.optimize(_objective, n_trials=remaining)

        # B1: best + history span the WHOLE store (reconstructed from study.trials, NOT this process),
        # so a resumed run reports a best that includes trials from earlier runs. trial.user_attrs holds
        # the metrics dict we set per trial; trial.params holds the candidate params — both persist.
        # R6 caveat: reconstructed Evaluations are all ok=True — Optuna does not persist the 1A `ok`
        # flag (matches the random_ convention). A consumer that needs to filter penalty/degenerate
        # trials should inspect the recorded metric (e.g. the guards.penalty_metrics sentinel value),
        # not `ok`.
        completed = [t for t in study.get_trials(deepcopy=False) if t.state == optuna.trial.TrialState.COMPLETE]
        history = [
            Evaluation(candidate=Candidate(id=f"t{t.number}", params=dict(t.params)),
                       metrics=dict(t.user_attrs), ok=True)
            for t in completed
        ]
        best: Evaluation | None = None
        if completed:
            bt = study.best_trial
            best = Evaluation(candidate=Candidate(id=f"t{bt.number}", params=dict(bt.params)),
                              metrics=dict(bt.user_attrs), ok=True)
        return Result(
            best=best, history=history,
            diagnostics={"n_trials": len(study.trials), "n_complete": len(completed), "sampler": cfg.sampler},
            provenance={"strategy": "optuna", "seed": self._seed, "direction": direction,
                        "storage": storage, "study_name": study.study_name},
        )
```
(`optuna` is imported lazily inside `run` so importing the module without the `[optuna]` extra doesn't fail. `history`/`best` are reconstructed from `study.get_trials` ordered by trial number, so `history[0]` is the warm-start trial on a fresh study.)
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit (checkpoint).**

---

## Task O6: `OptunaStrategy` × `CachedObjective` fast path + patch-param guard

**Files:** Create `tests/strategies/optuna/test_optuna_cached.py` (strategy-integration tests — separate from O2's unit file so each checkpoint stays ruff-clean, R3)

- [ ] **Step 1: Failing tests** (a SEPARATE new file — keeps every checkpoint ruff-clean; R3)
```python
# tests/strategies/optuna/test_optuna_cached.py
import pytest

from ruthless.backend import InProcessBackend
from ruthless.config import OptunaConfig
from ruthless.strategies.optuna_.strategy import OptunaStrategy


class _Cached:
    patch_params = frozenset({"x"})
    def __init__(self): self.prepared = 0; self.full_calls = 0
    def evaluate(self, c): self.full_calls += 1; return {"loss": (c.params["x"] - 2.0) ** 2}
    def prepare(self): self.prepared += 1; return {"target": 2.0}
    def evaluate_patch(self, inv, c): return {"loss": (c.params["x"] - inv["target"]) ** 2}


def _cfg(params):
    return OptunaConfig.model_validate(
        {"kind": "optuna", "metric": "loss", "n_trials": 30, "param_space": params}
    )


def test_cached_objective_uses_fast_path_and_prepares_once():
    obj = _Cached()
    r = OptunaStrategy(_cfg({"x": {"kind": "float", "lo": -10.0, "hi": 10.0}}), seed=42).run(obj, backend=InProcessBackend())
    assert obj.prepared == 1            # prepare() called exactly once
    assert obj.full_calls == 0          # fast path only; full evaluate never called
    assert r.best is not None and abs(r.best.candidate.params["x"] - 2.0) < 1.0


def test_tuning_a_non_patch_param_is_rejected():
    obj = _Cached()  # patch_params = {"x"}
    cfg = _cfg({"x": {"kind": "float", "lo": -1.0, "hi": 1.0},
                "y": {"kind": "float", "lo": -1.0, "hi": 1.0}})  # y is NOT a patch param
    with pytest.raises(ValueError, match="patch_params"):
        OptunaStrategy(cfg, seed=1).run(obj, backend=InProcessBackend())
```
- [ ] **Step 2: Run → FAIL** (if O5 implemented the guard correctly, the reject test may already pass; the fast-path/prepare-once assertions are new).
- [ ] **Step 3: Implement** — ensure O5's `run()` satisfies both (prepare once before optimize; `evaluate_patch` per trial; the `set(param_space) - patch_params` guard raises `ValueError`). No new file.
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit (checkpoint).**

---

## Task O7: e2e resume gate (C3 contract — no lost/dup + converges)

**Files:** Create `tests/e2e/test_optuna_resume_gate.py`

The standing Optuna gate (spec §8/C3): a resumable SQLite study on a quadratic — run `n/2`, "kill" (drop the strategy object), resume from the same store, assert **no lost/duplicate trials** (`len(study.trials)` grows monotonically to `n`), and convergence within tolerance. Trajectory-identity is NOT asserted (Optuna RNG not persisted).

- [ ] **Step 1: Write the gate**
```python
# tests/e2e/test_optuna_resume_gate.py
"""Standing Optuna gate (spec C3): resumable study — no lost/duplicate trials + converges. NOT
trajectory-identity (Optuna does not persist sampler RNG)."""
from ruthless.backend import InProcessBackend
from ruthless.config import OptunaConfig
from ruthless.result import Candidate
from ruthless.strategies.optuna_.strategy import OptunaStrategy


class _Bowl:
    def evaluate(self, candidate: Candidate):
        x = candidate.params["x"]
        return {"loss": (x - 2.0) ** 2}


def _cfg(n, path):
    return OptunaConfig.model_validate(
        {"kind": "optuna", "metric": "loss", "direction": "minimize", "n_trials": n,
         "param_space": {"x": {"kind": "float", "lo": -10.0, "hi": 10.0}},
         "store": {"kind": "sqlite", "path": path}}
    )


def test_resume_no_lost_or_duplicate_trials_and_converges(tmp_path):
    import optuna

    db = str(tmp_path / "study.db")
    # Run the first half, then "kill" (discard the strategy) and resume to the full count.
    r1 = OptunaStrategy(_cfg(20, db), seed=123).run(_Bowl(), backend=InProcessBackend())
    assert r1.diagnostics["n_trials"] == 20 and len(r1.history) == 20
    r2 = OptunaStrategy(_cfg(50, db), seed=123).run(_Bowl(), backend=InProcessBackend())
    # monotone growth, no lost/dup: the resumed study has exactly n_trials total.
    assert r2.diagnostics["n_trials"] == 50
    # B1: best + history span the WHOLE store, not just the 30 trials this process ran.
    assert len(r2.history) == 50
    # m3: trial ids are contiguous 0..49 (no lost, no duplicate).
    study = optuna.load_study(study_name=db, storage=f"sqlite:///{db}")
    assert sorted(t.number for t in study.trials) == list(range(50))
    # convergence within tolerance (NOT trajectory identity — Optuna RNG is not persisted).
    assert r2.best is not None and abs(r2.best.candidate.params["x"] - 2.0) < 0.5
```
(m9/R4: no SQLite-engine disposal — CI is ubuntu-only, and pytest tolerates a Windows `tmp_path`
teardown `PermissionError` with a warning. We deliberately do NOT poke `study._storage` (private,
unstable across Optuna 4.x — Hyrum's Law on an internal). If Windows local teardown noise ever
matters, give the study DB a non-`tmp_path` location, don't reach into `_storage`.)
- [ ] **Step 2: Run → PASS** — `uv run pytest tests/e2e/test_optuna_resume_gate.py -v`.
- [ ] **Step 3: Commit (checkpoint).**

---

## Task Z: full gate + final-review + PR

- [ ] **Step 1:** `uv run ruff check ruthless tests && uv run ruff format --check ruthless tests && uv run pyright && uv run lint-imports && uv run pytest -v` — all green (import-linter still 3 contracts; `optuna_` is under `strategies`).
- [ ] **Step 2:** `/final-review` — refresh `docs/c4/architecture.html` to add the `OptunaStrategy` container + the `testing` / `CachedObjective` (core) elements; update CLAUDE.md scope map (Phase 2 library side done; silly-kicks adoption next).
- [ ] **Step 3:** One commit on a feature branch + push + PR (per the repo commit-workflow rule). Then merge on approval.

---

## Self-Review

**Spec §9 Phase 2 (library side) coverage:** `OptunaStrategy` (resumable study + warm-start + sampler) → O5; `CachedObjective` (invariant/patch + `patch_params`) → O2/O6; `assert_cache_equivalence` harness + hypothesis property test (cache dispatch + over-declaration detection) → O3; config (discriminated `optuna` + store) → O1; resume contract C3 (no-lost/dup + converge, not trajectory-identity; best/history span the store) → O5/O7; SQLite-single-process note (§10/§11) → header + `StoreConfig`. **Group-scoring helper** (spec §3/M4) is **deferred** (M1) — the named consumer can't use the rev-1 design and runs CV in its own `score_fn`; a correct helper lands when a consumer needs it. **Staged pipeline** (spec §3) is intentionally NOT a built abstraction (YAGNI): a consumer stages by calling `OptunaStrategy.run` twice and threading the first study's best params (now correct across the store per B1) into the second's `warm_start`. **TC3 domain migration** and **silly-kicks objective authoring** are out of scope (consumer-side, follow-on).

**Placeholder scan:** none — every step is complete code with expected outcomes; no "TBD"/"add validation"/"similar to". (The earlier `isinstance_cached` drafting artifact was removed; the `best` selection is now an explicit min/max-or-None block.)

**Type consistency:** `OptunaConfig(kind, metric, direction, n_trials, sampler, param_space, warm_start, store)` + `_warm_start_keys` validator, `StoreConfig(kind, path)`, `CachedObjective.{patch_params, evaluate, prepare, evaluate_patch}`, `assert_cache_equivalence(objective, candidates, *, rtol, atol)`, `OptunaStrategy(config, *, seed).run(objective, *, backend) -> Result` (best/history reconstructed from `study.get_trials`), reuse of 1A `ParamSpec`/`FloatRange`/`IntRange`/`Choice`/`Direction`/`classify_metric` — consistent across O1–O7. (No `scoring` symbol — deferred.)

**Consumer-review resolutions (rev 2):** (1) `CachedObjective` shape — CONFIRMED by the consumer to map cleanly onto its frame-enrichment calibrations (invariant = per-match enriched/linked frames; patch = `LinkParams.k3`/`pre_seconds`/`min_displacement_m`); the over-declaration hole is closed by R5 (`assert_cache_equivalence` enforces that candidates vary every patch_param) + the `_OverDeclared` test. (2) Group-scoring — DEFERRED (M1): the consumer uses `StratifiedGroupKFold` internally and runs CV in its own `score_fn`; not shipped. (3) Staged pipeline — consumer confirmed it stages itself (two `run()` calls, best→`warm_start`), no helper needed; relies on B1 (now fixed). **Deviation from spec §9 — APPROVED (2026-05-28):** dropping `scoring` from Phase 2 (the consumer endorsed it; user signed off). A correctly-designed group-scoring helper can land in a later phase if a consumer needs it. Locked.

**Execution deviation (as-shipped):** the optuna test directory is `tests/strategies/optuna_/` (not `tests/strategies/optuna/`). A dir literally named `optuna` is put on `sys.path` by pytest (no `tests/__init__` chain) and **shadows the real `optuna` package** (`import optuna` → the empty test package → `ModuleNotFoundError: optuna.samplers`). The `optuna_` name mirrors the source package and avoids the collision. CI `core-lean --ignore` uses `tests/strategies/optuna_` accordingly. (The 1B `tests/strategies/evolve/` dir didn't collide only because nothing imports a top-level `evolve`.)
