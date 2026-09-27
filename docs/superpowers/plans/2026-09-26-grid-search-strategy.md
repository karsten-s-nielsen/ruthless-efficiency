# GridSearchStrategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan
> task-by-task, **inline in this session, on the owner's chosen implementation model** (handoff §7). Do **not**
> dispatch subagents without the owner's explicit approval (owner rule, 2026-09-23). Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Add a native, zero-dependency `GridSearchStrategy` (cartesian / one-at-a-time / points) with
fingerprint-keyed sqlite resume, release ruthless 0.7.0, and — as a library-wide fail-closed rule — make
`StoreConfig.objective_id` required and identity-guard both Grid and Optuna resume stores.

**Architecture:** Grid mirrors `random_` (a core, zero-dependency baseline strategy that owns its loop and
returns a `Result`). Enumeration/validation helpers live in the core (`config/space.py`,
`config/strategies.py`) because `GridConfig`'s pydantic validators run inside a `core-isolation` module that
cannot import `ruthless.strategies`. Resume is a strategy-owned stdlib-`sqlite3` store keyed by
`fingerprint(params)`, guarded by a config+objective meta. The same objective-identity rule is applied to
Optuna's SQLite resume via one atomic `ruthless_identity` study user-attr.

**Tech Stack:** Python ≥3.10, pydantic v2 (`<3`), stdlib `sqlite3`/`json`/`itertools`/`math`; dev: pytest,
hypothesis, ruff, pyright (basic), import-linter, hatchling. (numpy is a dep but grid does not use it.)

**Spec:** `docs/superpowers/specs/2026-09-26-grid-search-strategy-design.md` (rev 7, independent-review
APPROVED). The plan argues from the spec; executors read both. Appendix A is the binding TF-58 contract.

## Global Constraints

- **Commit discipline (OVERRIDES the writing-plans template):** **NO micro-commits, no per-task commits.**
  Each task is TDD (write failing test → run it fail → implement minimal → run it pass) and ends **without**
  committing. The whole feature is **one** coherent, fully-tested commit made only in Task 12, only after the
  full local gate + `/final-review` pass **and** the owner gives explicit approval for that specific
  commit+push+PR. Do not `git add`/`commit`/`push` before Task 12's approval gate. Do **not** create the
  `~/.claude-git-approval` sentinel — the owner runs the `!`-prefixed one-shot themselves if their hook needs
  it; you never `touch` it.
- **Branch:** work on the existing `feat/grid-strategy` (off `main` @ `a93734a`). **No git worktrees.** One
  branch, one PR.
- **Shift-Left per task:** every "run to verify pass" step also runs `uv run ruff check <touched files>` and
  `uv run pyright` on the touched files before the task is considered done — not only the Task-12 gate. Fix at
  the root; never weaken a test to make it pass.
- **Task-12 local gate (mirrors CI):** `uv run ruff check ruthless tests` · `uv run ruff format --check
  ruthless tests` · `uv run pyright` · `uv run lint-imports` · `uv run pytest -v`. `pyright` covers `ruthless`
  **and** `tests`.
- **Import-linter contracts stay green:** core must not import `ruthless.strategies`/`ruthless.backends`;
  strategies must not import backends or each other. Grid imports only core (`ruthless.backend` is the port
  module, allowed — not the `ruthless.backends` package). `config/space.py` and `config/strategies.py` may
  import `ruthless._fingerprint` (core→core, allowed).
- **Digest stability:** do **not** touch `_fingerprint.py` `_tag`; `tests/test_fingerprint_golden.py` stays
  green unchanged. `fingerprint_model(..., exclude=...)` takes a **`frozenset[str]`** — always pass
  `frozenset({...})`, never a set literal (pyright basic flags a `set` as `reportArgumentType`).
- **Ruff:** `tests/**` waives only `S101`; test function names lowercase (N802). Line length 120. Selected
  E,W,F,I,N,UP,B,S,BLE,RUF (RUF022 auto-sorts `__all__`; put imports at the top of each file — no mid-file
  imports (E402), no unused imports (F401); ruff format rewrites one-line defs and semicolons, so write
  multi-line).
- **Naming (verbatim from the spec/Appendix A):** `from ruthless.strategies.grid_ import GridSearchStrategy`;
  `from ruthless.config import GridConfig`; union member `kind: Literal["grid"]`; designs
  `"cartesian" | "one_at_a_time" | "points"`; grid candidate ids `f"g{i}"`; Optuna identity attr key
  `"ruthless_identity"` = `{"schema": 1, "objective_id", "config_fingerprint"}`.

## Spec §4 → plan test mapping (every acceptance test is covered)

| Spec test | Plan test (file :: name) |
|---|---|
| 1 loads 3 designs | T3 `test_grid_config.py::test_loads_cartesian_oat_points` |
| 2 FloatRange rejected | T3 `::test_rejects_floatrange` |
| 3 empty param_space | T3 `::test_rejects_empty_param_space` |
| 4 OAT baseline (missing/incomplete/extra-key/not-level/3.0/True) | T3 `::test_oat_baseline_rules` |
| 5 points rules | T3 `::test_points_rules` |
| 6 cross-field exclusivity | T3 `::test_cross_field_exclusivity` |
| 7 size guard fast | T3 `::test_size_guard_is_fast_and_bounded` |
| 8 boundary | T3 `::test_size_guard_boundary` |
| 9 fingerprintability (numpy) | T3 `::test_rejects_unfingerprintable_level` |
| 9b hashability (set/frozenset) | T3 `::test_rejects_set_accepts_frozenset` |
| 10 cartesian | T4 `test_grid_plan.py::test_cartesian_order_and_count` |
| 11 OAT | T4 `::test_one_at_a_time` |
| 12 points | T4 `::test_points_as_given` |
| 13 dedup (dup points + OAT-swap + contiguous ids) | T4 `::test_dedup_points`, `::test_oat_swap_dedup`, `::test_ids_contiguous_after_dedup` |
| 14 determinism | T4 `::test_deterministic` |
| 15 best MIN/MAX + tie→first (non-vacuous) | T6 `test_grid_strategy.py::test_best_minimize`, `::test_best_maximize`, `::test_tie_goes_to_first` |
| 16 history full metrics | T6 `::test_history_carries_full_metrics` |
| 17 diagnostics/provenance no seed | T6 `::test_diagnostics_and_provenance` |
| 18 non-finite scored raises | T6 `::test_nonfinite_scored_metric_raises` |
| 19 CachedObjective (extra/prepare-once/equiv/typed) | T6 `::test_cached_extra_param_rejected`, `::test_cached_prepare_once`, `::test_cached_equivalence`, `::test_conforms_to_search_strategy` |
| 20 durability/partial | T6 `test_grid_resume_gate.py::test_partial_resume_after_abort` |
| 21 full resume 0 eval | T6 `::test_full_resume_zero_evaluations` |
| 22 tag-typed levels + store | T6 `::test_tag_typed_levels_roundtrip` |
| 23 numpy aux metric + store | T6 `::test_numpy_aux_metric_roundtrip` |
| 24 objective_id change raises; path/max_points no-raise | T6 `::test_objective_id_change_raises`, `::test_path_and_max_points_change_do_not_raise` |
| 25 config + schema_version mismatch | T5 `test_grid_store.py::test_meta_guard_config`, `::test_schema_version_mismatch_raises` |
| 25b corrupt meta missing row | T5 `::test_corrupt_meta_missing_row_raises` |
| 26 mkdir | T5 `::test_put_get_roundtrip_and_mkdir` |
| 27 cached + full resume → 0 prepare | T6 `::test_cached_full_resume_zero_prepare` |
| 28 store golden | T10 `test_grid_store_golden.py::test_grid_store_schema_is_pinned` |
| 29 matching id+config resumes | T9 `test_optuna_resume_gate.py::test_optuna_matching_identity_resumes` |
| 30 objective_id mismatch raises | T9 `::test_optuna_objective_id_mismatch_raises` |
| 30b config mismatch raises; n_trials/warm_start no-raise | T9 `::test_optuna_config_mismatch_raises`, `::test_optuna_ntrials_warmstart_change_ok` |
| 30c malformed identity raises | T9 `::test_optuna_malformed_identity_raises` |
| 31 legacy raises w/ adopt message | T9 `::test_optuna_legacy_study_raises` |
| 32 adopt then resume succeeds | T9 `::test_adopt_then_resume_succeeds` |
| 33 adopt already-stamped raises | T9 `::test_adopt_already_stamped_raises` |
| 34 adopt then diff objective_id raises | T9 `::test_adopt_then_diff_objective_id_raises` |
| 35 adopt then diff param_space raises | T9 `::test_adopt_then_diff_config_raises` |
| 35b adopt store=None / no study raises | T9 `::test_adopt_requires_store_and_study` |
| 36 public API names | T7 `test_public_api.py` (`_EXPECTED_PUBLIC` gains `GridSearchStrategy`, `GridConfig`; `adopt_legacy_store` importability covered by `::test_optuna_pkg_import_is_lazy`) |
| 37 lean-install no optuna | T7 `::test_grid_is_core_and_pulls_no_extras`, `::test_optuna_pkg_import_is_lazy` |
| 38 CLI grid runs | T8 `test_cli.py::test_cli_grid_runs_end_to_end` |
| 39 StoreConfig required-field | T1 `test_store_config.py::test_storeconfig_requires_objective_id` |
| 40 fingerprint golden stays green | Task-12 gate (existing `test_fingerprint_golden.py`, unchanged) |

---

### Task 1: `StoreConfig.objective_id` becomes required (core config)

**Files:**
- Modify: `ruthless/config/common.py` (`StoreConfig`, lines 118-120)
- Modify (keep suite green): `tests/test_optuna_config.py:23`, `tests/e2e/test_optuna_resume_gate.py:24`
- Test: `tests/test_store_config.py` (new)

**Interfaces:**
- Produces: `StoreConfig(kind="sqlite", path: str, objective_id: str)` — `objective_id` required, non-empty.
  Consumed by `GridConfig.store` (T3), `GridStore` (T5), the Optuna guard (T9).

- [ ] **Step 1: Write the failing tests** — create `tests/test_store_config.py`:

```python
import pytest
from pydantic import ValidationError

from ruthless.config import StoreConfig


def test_storeconfig_requires_objective_id():
    with pytest.raises(ValidationError):
        StoreConfig.model_validate({"kind": "sqlite", "path": "r/s.db"})


def test_storeconfig_rejects_blank_objective_id():
    with pytest.raises(ValidationError, match="objective_id"):
        StoreConfig.model_validate({"kind": "sqlite", "path": "r/s.db", "objective_id": "  "})


def test_storeconfig_accepts_objective_id():
    s = StoreConfig.model_validate({"kind": "sqlite", "path": "r/s.db", "objective_id": "v1"})
    assert s.objective_id == "v1"
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/test_store_config.py -v` → FAIL.

- [ ] **Step 3: Implement** — in `ruthless/config/common.py` replace the `StoreConfig` body:

```python
class StoreConfig(BaseModel):
    kind: Literal["sqlite"] = "sqlite"  # only sqlite (single-process resume; RDB is later)
    path: str
    objective_id: str  # REQUIRED identity of the objective (code + data version) these results are valid for

    @model_validator(mode="after")
    def _objective_id_nonempty(self) -> StoreConfig:
        # Fail-closed: the caller must DECLARE the objective identity a resume store's rows belong to.
        if not self.objective_id.strip():
            raise ValueError("StoreConfig.objective_id must be a non-empty string")
        return self
```

- [ ] **Step 4: Fix the two existing store sites** so the suite stays green:
  - `tests/test_optuna_config.py` line ~23:
    `"store": {"kind": "sqlite", "path": "results/study.db", "objective_id": "test-obj-v1"},`
  - `tests/e2e/test_optuna_resume_gate.py` line ~24:
    `"store": {"kind": "sqlite", "path": path, "objective_id": "resume-gate-obj"},`

- [ ] **Step 5: Run to verify pass** —
  `uv run pytest tests/test_store_config.py tests/test_optuna_config.py tests/e2e/test_optuna_resume_gate.py -v`
  then `uv run ruff check ruthless/config/common.py tests/test_store_config.py` and `uv run pyright ruthless/config/common.py`.
  Expected: PASS. (No commit.)

---

### Task 2: Grid level + size helpers (core `config/space.py`)

**Files:**
- Modify: `ruthless/config/space.py` (append after the `ParamSpec` union, line 51; add `import math` and
  `from collections.abc import Mapping` to the top imports)
- Test: `tests/test_grid_space.py` (new)

**Interfaces:**
- Produces (imported by T3 validators and T4 enumeration):
  - `levels(spec: ParamSpec) -> tuple[Any, ...]` — MATERIALISES; `TypeError` on `FloatRange`.
  - `level_count(spec: ParamSpec) -> int` — non-materialising.
  - `is_level(value: object, spec: ParamSpec) -> bool` — type-strict; arithmetic for `IntRange`.
  - `grid_plan_size(design: str, param_space: Mapping[str, ParamSpec], points: list[dict[str, Any]] | None) -> int`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_grid_space.py`:

```python
import pytest

from ruthless.config import Choice, FloatRange, IntRange
from ruthless.config.space import grid_plan_size, is_level, level_count, levels


def _choice(*xs):
    return Choice(kind="choice", choices=tuple(xs))


def test_levels_choice_and_intrange():
    assert levels(_choice("a", "b")) == ("a", "b")
    assert levels(IntRange(kind="int", lo=2, hi=5)) == (2, 3, 4, 5)


def test_levels_floatrange_raises():
    with pytest.raises(TypeError):
        levels(FloatRange(kind="float", lo=0.0, hi=1.0))


def test_level_count_is_arithmetic_for_intrange():
    assert level_count(IntRange(kind="int", lo=0, hi=10**12)) == 10**12 + 1
    assert level_count(_choice("a", "b", "c")) == 3


def test_is_level_type_strict():
    c = _choice(1, 2, 3)
    assert is_level(2, c)
    assert not is_level(2.0, c)
    assert not is_level(True, c)
    r = IntRange(kind="int", lo=0, hi=4)
    assert is_level(3, r)
    assert not is_level(3.0, r)
    assert not is_level(True, r)
    assert not is_level(5, r)


def test_grid_plan_size_by_design():
    ps = {"a": _choice("x", "y"), "b": IntRange(kind="int", lo=1, hi=3)}
    assert grid_plan_size("cartesian", ps, None) == 6
    assert grid_plan_size("one_at_a_time", ps, None) == 1 + 1 + 2
    assert grid_plan_size("points", ps, [{"a": "x", "b": 1}, {"a": "y", "b": 2}]) == 2
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/test_grid_space.py -v` → FAIL (ImportError).

- [ ] **Step 3: Implement** — append to `ruthless/config/space.py`:

```python
def levels(spec: ParamSpec) -> tuple[Any, ...]:
    """Discrete levels of a grid dimension, in enumeration order. MATERIALISES — used only by the grid
    STRATEGY, after the size guard has bounded the plan. FloatRange has no finite levels (grid rejects it at
    config validation with a clearer message; this is the backstop)."""
    if isinstance(spec, Choice):
        return tuple(spec.choices)
    if isinstance(spec, IntRange):
        return tuple(range(spec.lo, spec.hi + 1))  # inclusive hi
    raise TypeError(f"levels() is undefined for {type(spec).__name__} (a grid needs discrete levels)")


def level_count(spec: ParamSpec) -> int:
    """Number of levels WITHOUT materialising them, so the size guard can reject a mistyped
    IntRange(0, 10**12) at construction instead of building a 10**12-element tuple."""
    if isinstance(spec, Choice):
        return len(spec.choices)
    if isinstance(spec, IntRange):
        return spec.hi - spec.lo + 1
    raise TypeError(f"level_count() is undefined for {type(spec).__name__}")


def is_level(value: object, spec: ParamSpec) -> bool:
    """Type-strict membership, matching `_tag`'s int/float/bool tagging so config validation and the store
    key agree. Arithmetic for IntRange (never materialises)."""
    if isinstance(spec, IntRange):
        return type(value) is int and spec.lo <= value <= spec.hi
    if isinstance(spec, Choice):
        return any(type(value) is type(lvl) and value == lvl for lvl in spec.choices)
    return False  # FloatRange rejected upstream by GridConfig validation


def grid_plan_size(design: str, param_space: Mapping[str, ParamSpec], points: list[dict[str, Any]] | None) -> int:
    """The design's theoretical point count (pre-dedup), closed-form, never enumerating."""
    if design == "points":
        return len(points or [])
    counts = [level_count(s) for s in param_space.values()]
    if design == "cartesian":
        return math.prod(counts) if counts else 0
    if design == "one_at_a_time":
        return 1 + sum(c - 1 for c in counts)
    raise ValueError(f"unknown grid design {design!r}")
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_grid_space.py -v`, `uv run ruff check
  ruthless/config/space.py tests/test_grid_space.py`, `uv run pyright ruthless/config/space.py`. PASS. (No commit.)

---

### Task 3: `GridConfig` + validators + public config export

**Files:**
- Modify: `ruthless/config/strategies.py` (add `_assert_usable_level`, `GridConfig`, extend the union; add
  imports `from ruthless.config.space import Choice, FloatRange, grid_plan_size, is_level` and
  `from ruthless._fingerprint import fingerprint`)
- Modify: `ruthless/config/__init__.py` (import `GridConfig`, add to `__all__`)
- Test: `tests/test_grid_config.py` (new)

**Interfaces:**
- Consumes: `StoreConfig` (T1); `grid_plan_size`/`is_level` (T2); `fingerprint` (core).
- Produces: `GridConfig` (union member `kind="grid"`), `from ruthless.config import GridConfig`. Fields:
  `metric: str`, `direction: Direction = MINIMIZE`, `design: Literal["cartesian","one_at_a_time","points"]`,
  `param_space: dict[str, ParamSpec]` (required), `baseline: dict[str, Any] | None = None`,
  `points: list[dict[str, Any]] | None = None`, `store: StoreConfig | None = None`, `max_points: int = 100_000`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_grid_config.py`:

```python
import numpy as np
import pytest
from pydantic import ValidationError

from ruthless.config import GridConfig, RuthlessConfig


def _cart(**extra):
    base = {
        "kind": "grid",
        "metric": "loss",
        "design": "cartesian",
        "param_space": {
            "a": {"kind": "choice", "choices": ("x", "y")},
            "b": {"kind": "int", "lo": 1, "hi": 3},
        },
    }
    base.update(extra)
    return base


def test_loads_cartesian_oat_points():
    assert isinstance(RuthlessConfig.model_validate({"strategy": _cart()}).strategy, GridConfig)
    oat = GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x", "b": 1}))
    assert oat.design == "one_at_a_time"
    pts = GridConfig.model_validate(_cart(design="points", points=[{"a": "x", "b": 1}, {"a": "y", "b": 2}]))
    assert pts.points is not None
    assert len(pts.points) == 2


def test_rejects_floatrange():
    with pytest.raises(ValidationError, match="Choice"):
        GridConfig.model_validate(_cart(param_space={"a": {"kind": "float", "lo": 0.0, "hi": 1.0}}))


def test_rejects_empty_param_space():
    with pytest.raises(ValidationError):
        GridConfig.model_validate({"kind": "grid", "metric": "loss", "design": "cartesian", "param_space": {}})


def test_oat_baseline_rules():
    with pytest.raises(ValidationError, match="baseline"):
        GridConfig.model_validate(_cart(design="one_at_a_time"))  # missing baseline
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x"}))  # missing key b
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x", "b": 1, "z": 9}))  # extra key
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x", "b": 9}))  # not a level
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x", "b": 1.0}))  # 1.0 != int 1
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x", "b": True}))  # True != int 1


def test_points_rules():
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="points"))  # missing points
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="points", points=[{"a": "x"}]))  # wrong keys
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="points", points=[{"a": "x", "b": 99}]))  # not a level


def test_cross_field_exclusivity():
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(baseline={"a": "x", "b": 1}))  # baseline on cartesian
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(points=[{"a": "x", "b": 1}]))  # points on cartesian


def test_size_guard_is_fast_and_bounded():
    big = _cart(param_space={"a": {"kind": "int", "lo": 0, "hi": 10**12}})
    with pytest.raises(ValidationError, match="max_points"):
        GridConfig.model_validate(big)


def test_size_guard_boundary():
    ok = _cart(param_space={"a": {"kind": "int", "lo": 1, "hi": 10}}, max_points=10)
    assert GridConfig.model_validate(ok)
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(param_space={"a": {"kind": "int", "lo": 1, "hi": 11}}, max_points=10))


def test_rejects_unfingerprintable_level():
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(param_space={"a": {"kind": "choice", "choices": (np.int64(3),)}}))


def test_rejects_set_accepts_frozenset():
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(param_space={"a": {"kind": "choice", "choices": ({1, 2},)}}))
    assert GridConfig.model_validate(
        _cart(param_space={"a": {"kind": "choice", "choices": (frozenset({1, 2}),)}})
    )
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/test_grid_config.py -v` → FAIL (GridConfig missing).

- [ ] **Step 3: Implement** — in `ruthless/config/strategies.py` add:

```python
def _assert_usable_level(value: object, name: str) -> None:
    # A level becomes a Candidate param value (must be hashable, result.py) and a fingerprint/store key
    # (must be _tag-supported). Validate BOTH at construction so a numpy scalar or a `set` fails here.
    try:
        hash(value)
    except TypeError as e:
        raise ValueError(f"level {value!r} for param {name!r} is unhashable ({e}); use a frozenset, not a set") from e
    try:
        fingerprint({name: value})
    except TypeError as e:
        raise ValueError(f"level {value!r} for param {name!r} is not fingerprint-able ({e}); use a native type") from e


class GridConfig(BaseModel):
    """Exhaustive/structured grid search (spec 2026-09-26). Three designs; discrete levels only (floats are
    Choice). Zero-dependency; CLI-available. `store` (with a required `objective_id`) gives fingerprint-keyed
    sqlite resume."""

    kind: Literal["grid"]
    metric: str
    direction: Direction = Direction.MINIMIZE
    design: Literal["cartesian", "one_at_a_time", "points"]
    param_space: dict[str, ParamSpec]
    baseline: dict[str, Any] | None = None
    points: list[dict[str, Any]] | None = None
    store: StoreConfig | None = None
    max_points: int = 100_000

    @model_validator(mode="after")
    def _validate(self) -> GridConfig:
        ps = self.param_space
        if not ps:  # rule 1
            raise ValueError("GridConfig.param_space must not be empty (a grid needs at least one dimension)")
        floats = [k for k, s in ps.items() if isinstance(s, FloatRange)]  # rule 2
        if floats:
            raise ValueError(f"FloatRange param(s) {sorted(floats)} not allowed in a grid; discrete floats are a Choice")
        if self.design == "one_at_a_time":  # rule 3
            if self.baseline is None:
                raise ValueError("design 'one_at_a_time' requires a baseline")
            if self.points is not None:
                raise ValueError("points must not be set for design 'one_at_a_time'")
        elif self.design == "points":
            if not self.points:
                raise ValueError("design 'points' requires a non-empty points list")
            if self.baseline is not None:
                raise ValueError("baseline must not be set for design 'points'")
        elif self.baseline is not None or self.points is not None:  # cartesian
            raise ValueError("baseline/points must not be set for design 'cartesian'")
        n = grid_plan_size(self.design, ps, self.points)  # rule 4: closed-form, before membership
        if n > self.max_points:
            raise ValueError(f"grid has {n} points > max_points={self.max_points}; narrow the space or raise max_points")
        for name, s in ps.items():  # rule 5
            if isinstance(s, Choice):
                for lvl in s.choices:
                    _assert_usable_level(lvl, name)
        if self.design == "one_at_a_time":  # rule 6
            assert self.baseline is not None
            if set(self.baseline) != set(ps):
                raise ValueError(f"baseline keys {sorted(self.baseline)} must equal param_space keys {sorted(ps)}")
            for k, v in self.baseline.items():
                _assert_usable_level(v, k)
                if not is_level(v, ps[k]):
                    raise ValueError(f"baseline[{k!r}]={v!r} is not a level of {k!r}")
        if self.design == "points":  # rule 7
            assert self.points is not None
            for i, pt in enumerate(self.points):
                if set(pt) != set(ps):
                    raise ValueError(f"points[{i}] keys {sorted(pt)} must equal param_space keys {sorted(ps)}")
                for k, v in pt.items():
                    _assert_usable_level(v, k)
                    if not is_level(v, ps[k]):
                        raise ValueError(f"points[{i}][{k!r}]={v!r} is not a level of {k!r}")
        return self
```

Extend the union:

```python
StrategyConfig = Annotated[
    RandomConfig | EvolveConfig | OptunaConfig | GridConfig, Field(discriminator="kind")
]
```

- [ ] **Step 4: Export** — in `ruthless/config/__init__.py` add `GridConfig` to the
  `from ruthless.config.strategies import (...)` block and to `__all__`.

- [ ] **Step 5: Run to verify pass** — `uv run pytest tests/test_grid_config.py -v`,
  `uv run ruff check ruthless/config tests/test_grid_config.py`, `uv run pyright ruthless/config`,
  `uv run lint-imports`. PASS + contracts kept. (No commit.)

---

### Task 4: Grid enumeration (`grid_/plan.py`)

**Files:**
- Create: `ruthless/strategies/grid_/__init__.py` (empty for now; re-export added in T7)
- Create: `ruthless/strategies/grid_/plan.py`
- Create: `tests/strategies/grid_/__init__.py` (empty — siblings have one)
- Test: `tests/strategies/grid_/test_grid_plan.py`

**Interfaces:**
- Consumes: `GridConfig` (T3); `levels` (T2); `fingerprint` (core).
- Produces: `enumerate_points(cfg: GridConfig) -> list[dict[str, Any]]` — ordered, de-duplicated by
  `fingerprint(params)`, first-occurrence preserved. Consumed by T6.

- [ ] **Step 1: Write the failing tests** — create `tests/strategies/grid_/__init__.py` (empty) and
  `tests/strategies/grid_/test_grid_plan.py`:

```python
from ruthless.config import GridConfig
from ruthless.strategies.grid_.plan import enumerate_points


def _cfg(**extra):
    base = {
        "kind": "grid",
        "metric": "loss",
        "design": "cartesian",
        "param_space": {
            "a": {"kind": "choice", "choices": ("x", "y")},
            "b": {"kind": "int", "lo": 1, "hi": 3},
        },
    }
    base.update(extra)
    return GridConfig.model_validate(base)


def test_cartesian_order_and_count():
    assert enumerate_points(_cfg()) == [
        {"a": "x", "b": 1}, {"a": "x", "b": 2}, {"a": "x", "b": 3},
        {"a": "y", "b": 1}, {"a": "y", "b": 2}, {"a": "y", "b": 3},
    ]


def test_one_at_a_time():
    pts = enumerate_points(_cfg(design="one_at_a_time", baseline={"a": "x", "b": 1}))
    assert pts == [
        {"a": "x", "b": 1},
        {"a": "y", "b": 1},
        {"a": "x", "b": 2},
        {"a": "x", "b": 3},
    ]


def test_points_as_given():
    pts = enumerate_points(_cfg(design="points", points=[{"a": "x", "b": 1}, {"a": "y", "b": 2}]))
    assert pts == [{"a": "x", "b": 1}, {"a": "y", "b": 2}]


def test_dedup_points():
    pts = enumerate_points(_cfg(design="points", points=[{"a": "x", "b": 1}, {"a": "x", "b": 1}]))
    assert pts == [{"a": "x", "b": 1}]


def test_oat_swap_dedup():
    # OAT over a Choice with a repeated non-baseline level exercises the OAT enumeration path: the two "y"
    # swaps collapse to one evaluated point (baseline "x" emitted once, then "y" once).
    cfg = GridConfig.model_validate({
        "kind": "grid", "metric": "loss", "design": "one_at_a_time",
        "param_space": {"a": {"kind": "choice", "choices": ("x", "y", "y")}},
        "baseline": {"a": "x"}})
    assert enumerate_points(cfg) == [{"a": "x"}, {"a": "y"}]


def test_ids_contiguous_after_dedup():
    # Enumeration returns params only; ids are assigned g0..g{n-1} by the strategy. Here we assert the
    # deduped list has no gap so the strategy's f"g{i}" ids are contiguous.
    pts = enumerate_points(_cfg(design="points", points=[{"a": "x", "b": 1}, {"a": "x", "b": 1}, {"a": "y", "b": 2}]))
    assert len(pts) == 2


def test_deterministic():
    assert enumerate_points(_cfg()) == enumerate_points(_cfg())
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/strategies/grid_/test_grid_plan.py -v` → FAIL.

- [ ] **Step 3: Implement** — `ruthless/strategies/grid_/plan.py`:

```python
"""Pure, deterministic grid enumeration. Zero-dependency; imports only core. De-duplicates on
`fingerprint(params)` (the same identity the resume store keys on), preserving first occurrence."""

from __future__ import annotations

import itertools
from typing import Any

from ruthless._fingerprint import fingerprint
from ruthless.config import GridConfig
from ruthless.config.space import levels


def enumerate_points(cfg: GridConfig) -> list[dict[str, Any]]:
    if cfg.design == "cartesian":
        names = list(cfg.param_space)
        raw = [
            dict(zip(names, combo, strict=True))
            for combo in itertools.product(*(levels(cfg.param_space[n]) for n in names))
        ]
    elif cfg.design == "one_at_a_time":
        base = dict(cfg.baseline or {})
        raw = [dict(base)]
        for name in cfg.param_space:
            for lvl in levels(cfg.param_space[name]):
                if not (type(lvl) is type(base[name]) and lvl == base[name]):  # type-strict "other level"
                    raw.append({**base, name: lvl})
    else:  # points
        raw = [dict(pt) for pt in (cfg.points or [])]

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for params in raw:
        fp = fingerprint(params)  # order-insensitive, value-distinguishing (spec §0.1)
        if fp not in seen:
            seen.add(fp)
            out.append(params)
    return out
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/strategies/grid_/test_grid_plan.py -v`,
  `uv run ruff check ruthless/strategies/grid_ tests/strategies/grid_`, `uv run pyright ruthless/strategies/grid_`. PASS. (No commit.)

---

### Task 5: Grid resume store (`grid_/store.py`)

**Files:**
- Create: `ruthless/strategies/grid_/store.py`
- Test: `tests/strategies/grid_/test_grid_store.py`

**Interfaces:**
- Consumes: `GridConfig`/`StoreConfig` (T1,T3); `fingerprint_model` (core); `get_logger` (core).
- Produces: `GridStore(cfg: GridConfig)` with `get(fp: str) -> dict[str, float] | None`,
  `put(fp: str, metrics: dict[str, float]) -> None` (durable per put), `close() -> None`; module constants
  `SCHEMA_VERSION = "1"`, `GRID_META_DDL`, `GRID_RESULT_DDL` (T10 golden test pins them).

- [ ] **Step 1: Write the failing tests** — create `tests/strategies/grid_/test_grid_store.py`:

```python
import numpy as np
import pytest

from ruthless.config import GridConfig
from ruthless.strategies.grid_.store import GridStore


def _cfg(store_dir, *, objective_id="obj-v1", **extra):
    base = {
        "kind": "grid",
        "metric": "loss",
        "design": "cartesian",
        "param_space": {"a": {"kind": "choice", "choices": ("x", "y")}},
        "store": {"kind": "sqlite", "path": str(store_dir / "grid.db"), "objective_id": objective_id},
    }
    base.update(extra)
    return GridConfig.model_validate(base)


def test_put_get_roundtrip_and_mkdir(tmp_path):
    cfg = _cfg(tmp_path / "nested")  # parent dir does not exist yet
    store = GridStore(cfg)
    assert store.get("fp1") is None
    store.put("fp1", {"loss": 0.5, "aux": 2.0})
    assert store.get("fp1") == {"loss": 0.5, "aux": 2.0}
    store.close()


def test_reopen_sees_committed_rows(tmp_path):
    cfg = _cfg(tmp_path)
    first = GridStore(cfg)
    first.put("fp1", {"loss": 1.0})
    first.close()
    assert GridStore(cfg).get("fp1") == {"loss": 1.0}


def test_meta_guard_objective_id(tmp_path):
    GridStore(_cfg(tmp_path, objective_id="v1")).close()
    with pytest.raises(ValueError, match="different grid"):
        GridStore(_cfg(tmp_path, objective_id="v2"))


def test_meta_guard_config(tmp_path):
    GridStore(_cfg(tmp_path)).close()
    changed = GridConfig.model_validate({**_cfg(tmp_path).model_dump(), "metric": "acc"})
    with pytest.raises(ValueError, match="different grid"):
        GridStore(changed)


def test_max_points_change_does_not_raise(tmp_path):
    GridStore(_cfg(tmp_path, max_points=100)).close()
    GridStore(_cfg(tmp_path, max_points=200)).close()  # max_points excluded from identity -> no raise


def test_schema_version_mismatch_raises(tmp_path):
    cfg = _cfg(tmp_path)
    store = GridStore(cfg)
    store._conn.execute("UPDATE grid_meta SET value='0' WHERE key='schema_version'")
    store.close()
    with pytest.raises(ValueError, match="different grid"):
        GridStore(cfg)


def test_corrupt_meta_missing_row_raises(tmp_path):
    cfg = _cfg(tmp_path)
    store = GridStore(cfg)
    store._conn.execute("DELETE FROM grid_meta WHERE key='objective_id'")
    store.close()
    with pytest.raises(ValueError, match="corrupt"):
        GridStore(cfg)


def test_metrics_float_coercion(tmp_path):
    store = GridStore(_cfg(tmp_path))
    store.put("fp1", {"loss": np.float32(0.25)})  # numpy would break json.dumps without coercion
    assert store.get("fp1") == {"loss": 0.25}
    store.close()
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/strategies/grid_/test_grid_store.py -v` → FAIL.

- [ ] **Step 3: Implement** — `ruthless/strategies/grid_/store.py`:

```python
"""Strategy-owned sqlite resume store for GridSearchStrategy. Rows keyed by fingerprint(params); a meta
table binds the store to one (grid config + objective) identity and fails loud on mismatch. stdlib sqlite3,
single-process (StoreConfig scope). See ADR-003."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ruthless._fingerprint import fingerprint_model
from ruthless._logging import get_logger
from ruthless.config import GridConfig

SCHEMA_VERSION = "1"
GRID_META_DDL = "CREATE TABLE IF NOT EXISTS grid_meta (key TEXT PRIMARY KEY, value TEXT)"
GRID_RESULT_DDL = "CREATE TABLE IF NOT EXISTS grid_result (fp TEXT PRIMARY KEY, metrics_json TEXT)"

_log = get_logger("strategies.grid.store")


class GridStore:
    def __init__(self, cfg: GridConfig) -> None:
        if cfg.store is None:
            raise ValueError("GridStore requires cfg.store to be set")
        self._path = cfg.store.path
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, isolation_level=None)  # autocommit => durable per put
        self._conn.execute(GRID_META_DDL)
        self._conn.execute(GRID_RESULT_DDL)
        self._init_and_guard(cfg)

    def _init_and_guard(self, cfg: GridConfig) -> None:
        assert cfg.store is not None
        want = {
            "schema_version": SCHEMA_VERSION,
            "config_fingerprint": fingerprint_model(cfg, exclude=frozenset({"store", "max_points"})),
            "objective_id": cfg.store.objective_id,
        }
        rows = dict(self._conn.execute("SELECT key, value FROM grid_meta").fetchall())
        if not rows:
            self._conn.execute("BEGIN")  # atomic meta init: no partial meta after a crash
            try:
                self._conn.executemany("INSERT INTO grid_meta (key, value) VALUES (?, ?)", list(want.items()))
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            return
        for key in want:
            if key not in rows:
                raise ValueError(f"grid store at {self._path!r} has corrupt meta (missing {key!r})")
        for key, value in want.items():
            if rows[key] != value:
                raise ValueError(
                    f"grid store at {self._path!r} was written for a different grid ({key} differs); "
                    "use a new path or delete the store"
                )

    def get(self, fp: str) -> dict[str, float] | None:
        row = self._conn.execute("SELECT metrics_json FROM grid_result WHERE fp = ?", (fp,)).fetchone()
        if row is None:
            return None
        loaded: dict[str, float] = json.loads(row[0])
        return loaded

    def put(self, fp: str, metrics: dict[str, float]) -> None:
        payload = json.dumps({k: float(v) for k, v in metrics.items()})  # float() accepts numpy scalars
        self._conn.execute("INSERT OR REPLACE INTO grid_result (fp, metrics_json) VALUES (?, ?)", (fp, payload))

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/strategies/grid_/test_grid_store.py -v`,
  `uv run ruff check ruthless/strategies/grid_/store.py tests/strategies/grid_/test_grid_store.py`,
  `uv run pyright ruthless/strategies/grid_/store.py`. PASS. (No commit.)

---

### Task 6: `GridSearchStrategy` (`grid_/strategy.py`) + strategy & resume tests

**Files:**
- Create: `ruthless/strategies/grid_/strategy.py`
- Test: `tests/strategies/grid_/test_grid_strategy.py`, `tests/e2e/test_grid_resume_gate.py`

**Interfaces:**
- Consumes: `enumerate_points` (T4); `GridStore` (T5); `GridConfig` (T3); core ports/types.
- Produces: `GridSearchStrategy(config: GridConfig)` with
  `run(self, objective: Objective, *, backend: ComputeBackend) -> Result` (structurally a `SearchStrategy`).

- [ ] **Step 1: Write the failing strategy tests** — create `tests/strategies/grid_/test_grid_strategy.py`:

```python
import math

import pytest

from ruthless.backend import InProcessBackend
from ruthless.config import GridConfig
from ruthless.errors import FatalEvaluationError
from ruthless.objective import CachedObjective
from ruthless.result import Candidate
from ruthless.strategy import SearchStrategy
from ruthless.strategies.grid_ import GridSearchStrategy
from ruthless.testing import assert_cache_equivalence


def _cfg(**extra):
    base = {"kind": "grid", "metric": "loss", "design": "cartesian",
            "param_space": {"b": {"kind": "int", "lo": 1, "hi": 3}}}
    base.update(extra)
    return GridConfig.model_validate(base)


class _Quad:
    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        b = candidate.params["b"]
        return {"loss": float((b - 2) ** 2), "aux": float(b)}


def test_best_minimize():
    r = GridSearchStrategy(_cfg()).run(_Quad(), backend=InProcessBackend())
    assert r.best is not None
    assert r.best.candidate.params["b"] == 2
    assert r.best.metrics["loss"] == 0.0


def test_best_maximize():
    r = GridSearchStrategy(_cfg(direction="maximize")).run(_Quad(), backend=InProcessBackend())
    assert r.best is not None
    assert r.best.metrics["loss"] == 1.0  # (1-2)^2 == (3-2)^2 == 1; max over {1,0,1}
    assert r.best.candidate.params["b"] == 1  # tie between b=1 and b=3 -> first in order


def test_tie_goes_to_first():
    # Two DISTINCT points with equal metric; best must be the first enumerated (not the last).
    class _Const:
        def evaluate(self, candidate: Candidate) -> dict[str, float]:
            return {"loss": 5.0}
    r = GridSearchStrategy(_cfg(param_space={"b": {"kind": "int", "lo": 1, "hi": 2}})).run(
        _Const(), backend=InProcessBackend())
    assert r.best is not None
    assert r.best.candidate.id == "g0"
    assert r.best.candidate.params["b"] == 1


def test_history_carries_full_metrics():
    r = GridSearchStrategy(_cfg()).run(_Quad(), backend=InProcessBackend())
    assert len(r.history) == 3
    assert all("loss" in ev.metrics and "aux" in ev.metrics for ev in r.history)


def test_diagnostics_and_provenance():
    r = GridSearchStrategy(_cfg()).run(_Quad(), backend=InProcessBackend())
    assert r.diagnostics == {"design": "cartesian", "n_points": 3, "n_unique": 3, "n_from_store": 0}
    assert r.provenance["strategy"] == "grid"
    assert r.provenance["design"] == "cartesian"
    assert r.provenance["direction"] == "minimize"
    assert "seed" not in r.provenance
    assert "ruthless_version" in r.provenance  # code_identity()


def test_nonfinite_scored_metric_raises():
    class _Bad:
        def evaluate(self, candidate: Candidate) -> dict[str, float]:
            return {"loss": math.inf}
    with pytest.raises(FatalEvaluationError):
        GridSearchStrategy(_cfg()).run(_Bad(), backend=InProcessBackend())


class _Cached:
    patch_params = frozenset({"b"})
    prepared = 0

    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        return {"loss": float(candidate.params["b"])}

    def prepare(self) -> dict[str, int]:
        _Cached.prepared += 1
        return {"inv": 1}

    def evaluate_patch(self, invariant: object, candidate: Candidate) -> dict[str, float]:
        return {"loss": float(candidate.params["b"])}


def test_cached_extra_param_rejected():
    cfg = _cfg(param_space={"b": {"kind": "int", "lo": 1, "hi": 2}, "c": {"kind": "int", "lo": 0, "hi": 1}})
    with pytest.raises(ValueError, match="patch_params"):
        GridSearchStrategy(cfg).run(_Cached(), backend=InProcessBackend())


def test_cached_prepare_once():
    _Cached.prepared = 0
    GridSearchStrategy(_cfg()).run(_Cached(), backend=InProcessBackend())
    assert _Cached.prepared == 1
    assert isinstance(_Cached(), CachedObjective)


def test_cached_equivalence():
    cands = [Candidate(f"g{i}", {"b": v}) for i, v in enumerate([1, 2, 3])]
    assert_cache_equivalence(_Cached(), cands)  # fast path == full recompute; varies patch_param b


def test_conforms_to_search_strategy():
    strategy: SearchStrategy = GridSearchStrategy(_cfg())
    assert strategy is not None
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/strategies/grid_/test_grid_strategy.py -v` → FAIL.

- [ ] **Step 3: Implement** — `ruthless/strategies/grid_/strategy.py`:

```python
"""GridSearchStrategy — a zero-dependency baseline strategy over a discrete grid. Owns its loop (spec C1),
returns a Result. Deterministic (no RNG). Optional fingerprint-keyed sqlite resume via GridStore."""

from __future__ import annotations

from ruthless._fingerprint import fingerprint
from ruthless._logging import get_logger
from ruthless._provenance import code_identity
from ruthless.backend import ComputeBackend
from ruthless.config import GridConfig
from ruthless.config.space import grid_plan_size
from ruthless.errors import classify_metric
from ruthless.objective import CachedObjective, Objective
from ruthless.result import Candidate, Evaluation, Result
from ruthless.strategy import Direction
from ruthless.strategies.grid_.plan import enumerate_points
from ruthless.strategies.grid_.store import GridStore

_log = get_logger("strategies.grid")


class GridSearchStrategy:
    """Exhaustive/structured grid search over a :class:`~ruthless.config.GridConfig`. Deterministic; no seed."""

    def __init__(self, config: GridConfig) -> None:
        self._cfg = config

    def run(self, objective: Objective, *, backend: ComputeBackend) -> Result:
        cfg = self._cfg
        plan = enumerate_points(cfg)
        better = (lambda a, b: a < b) if cfg.direction is Direction.MINIMIZE else (lambda a, b: a > b)

        cached: CachedObjective | None = objective if isinstance(objective, CachedObjective) else None
        if cached is not None:
            extra = set(cfg.param_space) - cached.patch_params
            if extra:  # same rule as OptunaStrategy: a non-patch param would reuse a stale invariant
                raise ValueError(f"param_space keys {sorted(extra)} are not in objective.patch_params")
        invariant: object | None = None
        prepared = False

        store = GridStore(cfg) if cfg.store is not None else None
        history: list[Evaluation] = []
        best: Evaluation | None = None
        n_from_store = 0
        try:
            for i, params in enumerate(plan):
                candidate = Candidate(id=f"g{i}", params=params)
                fp = fingerprint(params)
                metrics = store.get(fp) if store is not None else None
                if metrics is None:
                    if cached is not None:
                        if not prepared:
                            invariant = cached.prepare()  # lazy: zero prepare() on a fully-resumed run
                            prepared = True
                        metrics = cached.evaluate_patch(invariant, candidate)
                    else:
                        metrics = backend.evaluate(candidate, objective)
                    classify_metric(metrics[cfg.metric], candidate_id=candidate.id, metric=cfg.metric)
                    if store is not None:
                        store.put(fp, metrics)  # durable before the next point
                else:
                    n_from_store += 1
                ev = Evaluation(candidate=candidate, metrics=metrics, ok=True)
                history.append(ev)
                if best is None or better(metrics[cfg.metric], best.metrics[cfg.metric]):
                    best = ev
                    _log.info("new_best", extra={"point": i, cfg.metric: metrics[cfg.metric]})
        finally:
            if store is not None:
                store.close()

        return Result(
            best=best,
            history=history,
            diagnostics={
                "design": cfg.design,
                "n_points": grid_plan_size(cfg.design, cfg.param_space, cfg.points),
                "n_unique": len(history),
                "n_from_store": n_from_store,
            },
            provenance={
                "strategy": "grid",
                "design": cfg.design,
                "direction": cfg.direction.value,
                **code_identity(),
            },
        )
```

- [ ] **Step 4: Write the failing resume tests** — create `tests/e2e/test_grid_resume_gate.py`:

```python
import datetime as dt
from enum import Enum
from pathlib import PurePosixPath

import numpy as np
import pytest

from ruthless.backend import InProcessBackend
from ruthless.config import GridConfig
from ruthless.errors import FatalEvaluationError
from ruthless.objective import CachedObjective
from ruthless.result import Candidate
from ruthless.strategies.grid_ import GridSearchStrategy


class _Color(Enum):
    RED = 1
    BLUE = 2


def _cfg(tmp_path, *, objective_id="obj-v1", **extra):
    base = {"kind": "grid", "metric": "loss", "design": "cartesian",
            "param_space": {"b": {"kind": "int", "lo": 1, "hi": 4}},
            "store": {"kind": "sqlite", "path": str(tmp_path / "g.db"), "objective_id": objective_id}}
    base.update(extra)
    return GridConfig.model_validate(base)


class _Counting:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        self.calls += 1
        return {"loss": float(candidate.params["b"])}


class _RaiseAtK:
    def __init__(self, k: int) -> None:
        self.k = k
        self.seen = 0

    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        self.seen += 1
        if self.seen > self.k:
            raise FatalEvaluationError("boom")
        return {"loss": float(candidate.params["b"])}


def test_full_resume_zero_evaluations(tmp_path):
    cfg = _cfg(tmp_path)
    GridSearchStrategy(cfg).run(_Counting(), backend=InProcessBackend())
    obj = _Counting()
    r = GridSearchStrategy(cfg).run(obj, backend=InProcessBackend())
    assert obj.calls == 0
    assert r.diagnostics["n_from_store"] == 4
    assert len(r.history) == 4


def test_partial_resume_after_abort(tmp_path):
    cfg = _cfg(tmp_path)
    with pytest.raises(FatalEvaluationError):
        GridSearchStrategy(cfg).run(_RaiseAtK(2), backend=InProcessBackend())  # 2 stored, then abort
    obj = _Counting()
    r = GridSearchStrategy(cfg).run(obj, backend=InProcessBackend())
    assert r.diagnostics["n_from_store"] == 2
    assert obj.calls == 2
    assert len(r.history) == 4


def test_objective_id_change_raises(tmp_path):
    GridSearchStrategy(_cfg(tmp_path, objective_id="v1")).run(_Counting(), backend=InProcessBackend())
    with pytest.raises(ValueError, match="different grid"):
        GridSearchStrategy(_cfg(tmp_path, objective_id="v2")).run(_Counting(), backend=InProcessBackend())


def test_path_and_max_points_change_do_not_raise(tmp_path):
    GridSearchStrategy(_cfg(tmp_path, max_points=100)).run(_Counting(), backend=InProcessBackend())
    # same path, different max_points -> excluded from identity -> resumes fine
    GridSearchStrategy(_cfg(tmp_path, max_points=200)).run(_Counting(), backend=InProcessBackend())
    # different path -> a fresh store -> no raise
    other = GridConfig.model_validate({**_cfg(tmp_path).model_dump(),
                                       "store": {"kind": "sqlite", "path": str(tmp_path / "g2.db"),
                                                 "objective_id": "obj-v1"}})
    GridSearchStrategy(other).run(_Counting(), backend=InProcessBackend())


def test_tag_typed_levels_roundtrip(tmp_path):
    cfg = GridConfig.model_validate({
        "kind": "grid", "metric": "loss", "design": "cartesian",
        "param_space": {"c": {"kind": "choice",
                              "choices": (_Color.RED, PurePosixPath("/x"),
                                          dt.datetime(2020, 1, 1), frozenset({1, 2}))}},
        "store": {"kind": "sqlite", "path": str(tmp_path / "tag.db"), "objective_id": "v1"}})

    class _Obj:
        def evaluate(self, candidate: Candidate) -> dict[str, float]:
            return {"loss": 1.0}

    r1 = GridSearchStrategy(cfg).run(_Obj(), backend=InProcessBackend())
    r2 = GridSearchStrategy(cfg).run(_Obj(), backend=InProcessBackend())  # resume: all from store
    assert len(r1.history) == 4
    assert r2.diagnostics["n_from_store"] == 4


def test_numpy_aux_metric_roundtrip(tmp_path):
    class _Obj:
        def evaluate(self, candidate: Candidate) -> dict[str, float]:
            return {"loss": float(candidate.params["b"]), "aux": np.float32(0.5)}

    cfg = _cfg(tmp_path)
    GridSearchStrategy(cfg).run(_Obj(), backend=InProcessBackend())
    r = GridSearchStrategy(cfg).run(_Obj(), backend=InProcessBackend())
    assert r.history[0].metrics["aux"] == 0.5


def test_cached_full_resume_zero_prepare(tmp_path):
    class _Cached:
        patch_params = frozenset({"b"})
        prepared = 0

        def evaluate(self, candidate: Candidate) -> dict[str, float]:
            return {"loss": float(candidate.params["b"])}

        def prepare(self) -> dict[str, int]:
            _Cached.prepared += 1
            return {"inv": 1}

        def evaluate_patch(self, invariant: object, candidate: Candidate) -> dict[str, float]:
            return {"loss": float(candidate.params["b"])}

    assert isinstance(_Cached(), CachedObjective)
    cfg = _cfg(tmp_path)
    GridSearchStrategy(cfg).run(_Cached(), backend=InProcessBackend())  # populates store; prepare() once
    _Cached.prepared = 0
    GridSearchStrategy(cfg).run(_Cached(), backend=InProcessBackend())  # fully resumed
    assert _Cached.prepared == 0
```

- [ ] **Step 5: Run to verify pass** —
  `uv run pytest tests/strategies/grid_/ tests/e2e/test_grid_resume_gate.py -v`,
  `uv run ruff check ruthless/strategies/grid_ tests/strategies/grid_ tests/e2e/test_grid_resume_gate.py`,
  `uv run pyright ruthless/strategies/grid_`. PASS. (No commit.)

---

### Task 7: Grid package re-export + public API

**Files:**
- Modify: `ruthless/strategies/grid_/__init__.py`
- Modify: `ruthless/__init__.py`
- Modify: `tests/test_public_api.py`

**Interfaces:**
- Produces: `from ruthless.strategies.grid_ import GridSearchStrategy`;
  `from ruthless import GridSearchStrategy, GridConfig`. (`adopt_legacy_store` is NOT top-level — T9.)

- [ ] **Step 1: Write the failing tests** — in `tests/test_public_api.py` add `"GridSearchStrategy"` and
  `"GridConfig"` to `_EXPECTED_PUBLIC`, and append:

```python
def test_grid_is_core_and_pulls_no_extras() -> None:
    code = (
        "import ruthless, sys; ruthless.GridSearchStrategy;"
        " assert 'optuna' not in sys.modules and 'openevolve' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603


def test_optuna_pkg_import_is_lazy() -> None:
    # Importing the optuna_ package (for adopt_legacy_store / OptunaStrategy) must not import optuna at
    # module load; optuna is imported lazily inside run()/adopt_legacy_store().
    code = (
        "import sys, ruthless.strategies.optuna_ as m; m.adopt_legacy_store;"
        " assert 'optuna' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/test_public_api.py -v` → FAIL.

- [ ] **Step 3: Implement**

`ruthless/strategies/grid_/__init__.py`:

```python
"""Built-in grid-search strategy (core; no extra required)."""

from __future__ import annotations

from ruthless.strategies.grid_.strategy import GridSearchStrategy

__all__ = ["GridSearchStrategy"]
```

In `ruthless/__init__.py`: add `from ruthless.strategies.grid_ import GridSearchStrategy`; add `GridConfig`
to the existing `from ruthless.config import (...)` block; add both names to `__all__` (ruff RUF022 orders it).

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_public_api.py -v`,
  `uv run ruff check ruthless/__init__.py ruthless/strategies/grid_/__init__.py tests/test_public_api.py`,
  `uv run pyright ruthless`. PASS. (No commit.) Note: `test_optuna_pkg_import_is_lazy` depends on T9's
  `adopt_legacy_store`; if running T7 before T9, mark that one test xfail and un-xfail in T9, or reorder T9
  before T7 — reordering is fine (T9 has no dependency on T7).

---

### Task 8: CLI registration

**Files:**
- Modify: `ruthless/cli.py`
- Test: `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing test** — append to `tests/test_cli.py` (imports at the top of the file):

```python
def test_cli_grid_runs_end_to_end():
    from ruthless.backend import InProcessBackend
    from ruthless.cli import _build_strategy
    from ruthless.config import RuthlessConfig
    from ruthless.result import Candidate
    from ruthless.strategies.grid_ import GridSearchStrategy

    class _Obj:
        def evaluate(self, candidate: Candidate) -> dict[str, float]:
            return {"loss": float(candidate.params["b"])}

    cfg = RuthlessConfig.model_validate({"strategy": {
        "kind": "grid", "metric": "loss", "design": "cartesian",
        "param_space": {"b": {"kind": "int", "lo": 1, "hi": 2}}}})
    strategy = _build_strategy(cfg)
    assert isinstance(strategy, GridSearchStrategy)
    result = strategy.run(_Obj(), backend=InProcessBackend())
    assert result.best is not None
    assert len(result.history) == 2
```

(If `tests/test_cli.py` already imports these at the top, move the imports up and drop the in-function ones to
satisfy ruff. Keep the file's existing import style.)

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/test_cli.py::test_cli_grid_runs_end_to_end -v` → FAIL.

- [ ] **Step 3: Implement** — in `ruthless/cli.py`: add imports `from ruthless.config import GridConfig` (extend
  the existing config import) and `from ruthless.strategies.grid_ import GridSearchStrategy`; add one row to
  `_STRATEGY_BUILDERS`:

```python
    GridConfig: lambda strategy_cfg, seed: GridSearchStrategy(strategy_cfg),  # deterministic; ignores seed
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_cli.py -v`,
  `uv run ruff check ruthless/cli.py tests/test_cli.py`, `uv run pyright ruthless/cli.py`. PASS. (No commit.)

---

### Task 9: Optuna store-identity guard + `adopt_legacy_store`

**Files:**
- Modify: `ruthless/strategies/optuna_/strategy.py`
- Modify: `ruthless/strategies/optuna_/__init__.py`
- Test: `tests/e2e/test_optuna_resume_gate.py` (append; imports at top)

**Interfaces:**
- Consumes: `fingerprint_model` (core), `OptunaConfig`, `StoreConfig.objective_id` (T1).
- Produces: `from ruthless.strategies.optuna_ import adopt_legacy_store`;
  `adopt_legacy_store(config: OptunaConfig) -> None`. Identity attr key `"ruthless_identity"`
  = `{"schema": 1, "objective_id", "config_fingerprint"}`.

- [ ] **Step 1: Write the failing tests** — append to `tests/e2e/test_optuna_resume_gate.py` (add these imports
  to the top import block: `import optuna`, `import pytest`, `from ruthless.backend import InProcessBackend`,
  `from ruthless.config import OptunaConfig`, `from ruthless.strategies.optuna_ import OptunaStrategy, adopt_legacy_store`):

```python
def _ocfg(path, *, objective_id="v1", **extra):
    base = {"kind": "optuna", "metric": "loss", "n_trials": 2, "sampler": "random",
            "param_space": {"x": {"kind": "float", "lo": 0.0, "hi": 1.0}},
            "store": {"kind": "sqlite", "path": path, "objective_id": objective_id}}
    base.update(extra)
    return OptunaConfig.model_validate(base)


class _OObj:
    def evaluate(self, candidate):
        return {"loss": float(candidate.params["x"])}


def test_optuna_matching_identity_resumes(tmp_path):
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())
    r = OptunaStrategy(_ocfg(p, n_trials=4)).run(_OObj(), backend=InProcessBackend())  # more budget OK
    assert len(r.history) >= 2


def test_optuna_ntrials_warmstart_change_ok(tmp_path):
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())
    # n_trials and warm_start are excluded from the identity -> changing them does NOT raise
    OptunaStrategy(_ocfg(p, n_trials=3, warm_start={"x": 0.5})).run(_OObj(), backend=InProcessBackend())


def test_optuna_objective_id_mismatch_raises(tmp_path):
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p, objective_id="v1")).run(_OObj(), backend=InProcessBackend())
    with pytest.raises(ValueError, match="different objective"):
        OptunaStrategy(_ocfg(p, objective_id="v2")).run(_OObj(), backend=InProcessBackend())


def test_optuna_config_mismatch_raises(tmp_path):
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())
    changed = _ocfg(p, param_space={"x": {"kind": "float", "lo": 0.0, "hi": 2.0}})
    with pytest.raises(ValueError, match="different config"):
        OptunaStrategy(changed).run(_OObj(), backend=InProcessBackend())


@pytest.mark.parametrize("bad", [{"schema": 99}, "not-a-dict", {"schema": 1, "objective_id": "v1"}])
def test_optuna_malformed_identity_raises(tmp_path, bad):
    # unknown schema / non-dict / dict missing a sub-field all fail loud, never an undefined comparison.
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())
    study = optuna.load_study(study_name=p, storage=f"sqlite:///{p}")
    study.set_user_attr("ruthless_identity", bad)
    with pytest.raises(ValueError, match="corrupt|unrecognised"):
        OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())


def test_optuna_legacy_study_raises(tmp_path):
    p = str(tmp_path / "legacy.db")
    st = optuna.create_study(study_name=p, storage=f"sqlite:///{p}", direction="minimize")
    st.optimize(lambda t: t.suggest_float("x", 0.0, 1.0), n_trials=1)  # >=1 trial, no ruthless_identity
    with pytest.raises(ValueError, match="adopt_legacy_store"):
        OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())


def test_adopt_then_resume_succeeds(tmp_path):
    p = str(tmp_path / "legacy.db")
    st = optuna.create_study(study_name=p, storage=f"sqlite:///{p}", direction="minimize")
    st.optimize(lambda t: t.suggest_float("x", 0.0, 1.0), n_trials=1)
    cfg = _ocfg(p)
    adopt_legacy_store(cfg)
    OptunaStrategy(cfg).run(_OObj(), backend=InProcessBackend())  # now guarded, resumes fine


def test_adopt_already_stamped_raises(tmp_path):
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())  # stamps identity
    with pytest.raises(ValueError, match="already carries"):
        adopt_legacy_store(_ocfg(p))


def test_adopt_then_diff_objective_id_raises(tmp_path):
    p = str(tmp_path / "legacy.db")
    st = optuna.create_study(study_name=p, storage=f"sqlite:///{p}", direction="minimize")
    st.optimize(lambda t: t.suggest_float("x", 0.0, 1.0), n_trials=1)
    adopt_legacy_store(_ocfg(p, objective_id="v1"))
    with pytest.raises(ValueError, match="different objective"):
        OptunaStrategy(_ocfg(p, objective_id="v2")).run(_OObj(), backend=InProcessBackend())


def test_adopt_then_diff_config_raises(tmp_path):
    p = str(tmp_path / "legacy.db")
    st = optuna.create_study(study_name=p, storage=f"sqlite:///{p}", direction="minimize")
    st.optimize(lambda t: t.suggest_float("x", 0.0, 1.0), n_trials=1)
    adopt_legacy_store(_ocfg(p))
    changed = _ocfg(p, param_space={"x": {"kind": "float", "lo": 0.0, "hi": 2.0}})
    with pytest.raises(ValueError, match="different config"):
        OptunaStrategy(changed).run(_OObj(), backend=InProcessBackend())


def test_adopt_requires_store_and_study(tmp_path):
    with pytest.raises(ValueError):
        adopt_legacy_store(OptunaConfig.model_validate(
            {"kind": "optuna", "metric": "loss", "param_space": {"x": {"kind": "float", "lo": 0.0, "hi": 1.0}}}))
    with pytest.raises(ValueError, match="no optuna study"):
        adopt_legacy_store(_ocfg(str(tmp_path / "nope.db")))
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/e2e/test_optuna_resume_gate.py -v` → FAIL.

- [ ] **Step 3: Implement** — in `ruthless/strategies/optuna_/strategy.py`, add to the top imports
  `from pathlib import Path`, `from ruthless._fingerprint import fingerprint_model`, and extend the existing
  `from ruthless.config import ...` line to include `OptunaConfig`. Add module-level helpers:

```python
_IDENTITY_KEY = "ruthless_identity"


def _identity(cfg: OptunaConfig) -> dict[str, object]:
    assert cfg.store is not None
    return {
        "schema": 1,
        "objective_id": cfg.store.objective_id,
        "config_fingerprint": fingerprint_model(cfg, exclude=frozenset({"store", "n_trials", "warm_start"})),
    }


def _check_identity(stored: object, want: dict[str, object], path: str) -> None:
    if not isinstance(stored, dict):  # split so pyright narrows `stored` to dict before indexing below
        raise ValueError(f"optuna store at {path!r} has a corrupt/unrecognised ruthless_identity; use a new store path")
    if stored.get("schema") != 1 or "objective_id" not in stored or "config_fingerprint" not in stored:
        raise ValueError(f"optuna store at {path!r} has a corrupt/unrecognised ruthless_identity; use a new store path")
    if stored["objective_id"] != want["objective_id"]:
        raise ValueError(f"optuna store at {path!r} was written for a different objective; use a new store path")
    if stored["config_fingerprint"] != want["config_fingerprint"]:
        raise ValueError(f"optuna store at {path!r} was written for a different config; use a new store path")


def adopt_legacy_store(config: OptunaConfig) -> None:
    """One-shot, deliberate adoption of a legacy (pre-0.7.0) Optuna SQLite study: stamp `ruthless_identity`
    once from `config`. Refuses a study that already carries the attr, a config without a store, and a path
    with no study. See ADR-003."""
    import optuna

    if config.store is None:
        raise ValueError("adopt_legacy_store requires config.store to be set")
    path = config.store.path
    if not Path(path).exists():
        raise ValueError(f"no optuna study to adopt at {path!r}: file does not exist")
    try:
        study = optuna.load_study(study_name=path, storage=f"sqlite:///{path}")
    except KeyError as e:  # study name not present in the storage
        raise ValueError(f"no optuna study to adopt at {path!r}: {e}") from e
    if study.user_attrs.get(_IDENTITY_KEY) is not None:
        raise ValueError(f"optuna store at {path!r} already carries a ruthless_identity; refusing to overwrite")
    study.set_user_attr(_IDENTITY_KEY, _identity(config))
    _log.info("adopted_legacy_store", extra={"path": path, "objective_id": config.store.objective_id})
```

In `OptunaStrategy.run`, immediately after `study = optuna.create_study(...)` (line ~104) and before
`n_existing = len(study.trials)`, insert the guard:

```python
        if cfg.store is not None:
            stored = study.user_attrs.get(_IDENTITY_KEY)
            want = _identity(cfg)
            if stored is not None:
                _check_identity(stored, want, cfg.store.path)
            elif len(study.trials) == 0:
                study.set_user_attr(_IDENTITY_KEY, want)  # fresh study: stamp once (one atomic write)
            else:
                raise ValueError(
                    f"optuna store at {cfg.store.path!r} predates ruthless 0.7.0 identity guarding; run "
                    "ruthless.strategies.optuna_.adopt_legacy_store(config) to adopt it"
                )
```

- [ ] **Step 4: Re-export** — `ruthless/strategies/optuna_/__init__.py`:

```python
"""OptunaStrategy ([optuna] extra). `optuna` is imported lazily inside run()/adopt_legacy_store(), so
importing this package is dependency-light."""

from __future__ import annotations

from ruthless.strategies.optuna_.strategy import OptunaStrategy, adopt_legacy_store

__all__ = ["OptunaStrategy", "adopt_legacy_store"]
```

- [ ] **Step 5: Run to verify pass** — `uv run pytest tests/e2e/test_optuna_resume_gate.py -v`,
  `uv run ruff check ruthless/strategies/optuna_ tests/e2e/test_optuna_resume_gate.py`,
  `uv run pyright ruthless/strategies/optuna_`. PASS. Re-run `tests/test_public_api.py`
  (`test_optuna_pkg_import_is_lazy` now passes). (No commit.)

---

### Task 10: Grid store golden test (ADR-003 enforcement)

**Files:**
- Test: `tests/test_grid_store_golden.py`

- [ ] **Step 1: Write the test** — create `tests/test_grid_store_golden.py`:

```python
from ruthless.strategies.grid_.store import GRID_META_DDL, GRID_RESULT_DDL, SCHEMA_VERSION


def test_grid_store_schema_is_pinned():
    # ADR-003: the on-disk store is a compatibility surface. A schema change must be deliberate — bump
    # SCHEMA_VERSION and this test together, and note the store invalidation in the CHANGELOG.
    assert SCHEMA_VERSION == "1"
    assert GRID_META_DDL == "CREATE TABLE IF NOT EXISTS grid_meta (key TEXT PRIMARY KEY, value TEXT)"
    assert GRID_RESULT_DDL == "CREATE TABLE IF NOT EXISTS grid_result (fp TEXT PRIMARY KEY, metrics_json TEXT)"
```

- [ ] **Step 2: Run** — `uv run pytest tests/test_grid_store_golden.py -v` and
  `uv run ruff check tests/test_grid_store_golden.py`. PASS (constants defined in T5). (No commit.)

---

### Task 11: Version bump, CHANGELOG, ADR-003, AGENTS.md

**Files:**
- Modify: `ruthless/_version.py` (`0.6.0` → `0.7.0`)
- Modify: `CHANGELOG.md`
- Create: `docs/adr/ADR-003-grid-resume-store-schema.md`
- Modify: `AGENTS.md`
- Test: `tests/test_agents_md_budget.py`, `tests/test_docs_no_digest_literals.py` (must stay green)

- [ ] **Step 1: Bump the version** — `ruthless/_version.py`: `__version__ = "0.7.0"`. Verify
  `uv run python -c "import ruthless; print(ruthless.__version__)"` → `0.7.0`.

- [ ] **Step 2: CHANGELOG `[0.7.0]`** — add a top section (Keep-a-Changelog format):
  - `### Added` — `GridSearchStrategy` + `GridConfig` (cartesian / one_at_a_time / points; fingerprint-keyed
    sqlite resume with a config+objective meta-guard; closed-form `max_points` size guard; CLI-available).
  - `### Changed` / `### Breaking` — (a) `StoreConfig.objective_id` is now **required**; (b) Optuna resume is
    identity-guarded (a resume whose `objective_id` **or** config `param_space`/`sampler`/`direction`/`metric`
    differs now **raises**; 0.6.0 continued silently) — remedy: a new `store.path`; (c) resuming a legacy
    (≤0.6.0, attr-less) Optuna store now **raises** — remedy
    `ruthless.strategies.optuna_.adopt_legacy_store(config)`.
  - A sentence: `fingerprint` caches are **not** invalidated (digest path untouched); a grid store's `fp` key
    depends on the digest (ADR-002/ADR-003), so a future `_tag` change would invalidate grid stores.

- [ ] **Step 3: Write ADR-003** (`docs/adr/ADR-003-grid-resume-store-schema.md`) following ADR-002's
  Context/Decision/Consequences structure. Record: the `grid_meta`/`grid_result` schema + columns +
  `SCHEMA_VERSION`; row key `fingerprint(params)` and its dependence on ADR-002 (a `_tag` change invalidates
  grid stores and must say so in the CHANGELOG — stated where the next editor of `_fingerprint.py` will find
  it); store identity = `config_fingerprint` + `objective_id`, honoured by Grid (sqlite meta) and Optuna (one
  `ruthless_identity` study attr with a `schema` sub-field; malformed/unknown `schema` fails loud); legacy
  Optuna studies fail-closed with one-shot `adopt_legacy_store`; params not stored (re-derived from the plan);
  durability = commit per point; stability stance = a schema change bumps `SCHEMA_VERSION`, an older store
  fails loud with no silent migration, under 0.x it takes the minor slot with a CHANGELOG line stating it
  invalidates existing stores; scope = single-process, sqlite only, multi-process resume deferred. **No digest
  literal** in the .md (`tests/test_docs_no_digest_literals.py`).

- [ ] **Step 4: AGENTS.md** — bump "Ships at 0.6.0" → `0.7.0`; add under "Architecture decisions":
  `` - `docs/adr/ADR-003-grid-resume-store-schema.md` — grid/optuna resume store schema + library-wide store-identity rule. ``

- [ ] **Step 5: Run the guards** —
  `uv run pytest tests/test_agents_md_budget.py tests/test_docs_no_digest_literals.py -v`. PASS. If the budget
  test fails, shorten the added AGENTS.md wording (keep the "Ships at" bump + the one ADR line, shorten the
  ADR line if needed) rather than dropping content. (No commit.)

---

### Task 12: FINAL — full gate, /final-review, single approved commit

**Files:** none new (verification + the one commit).

- [ ] **Step 1: Full local quality gate (Shift Left)**

```bash
uv run ruff check ruthless tests
uv run ruff format --check ruthless tests
uv run pyright
uv run lint-imports
uv run pytest -v
```
All five green. Fix any failure at its root. `lint-imports` shows all 3 contracts kept.

- [ ] **Step 2: Run `/final-review`** — the mandatory pre-commit gate; it regenerates the C4 diagram at
  `docs/c4/architecture.html` (render with Graphviz `dot`, per the user's C4 convention). Surface every finding
  loudly; fix, do not grade-down. Re-run the gate if anything changed.

- [ ] **Step 3: Present for explicit approval (HARD GATE — do NOT commit/push/PR before a yes)**

Show the owner exactly what would land: `git status`, `git diff --stat`, the proposed commit message, and the
intended PR. State that spec + plan + code + tests + ADR-003 + CHANGELOG + version bump + C4 land in **one**
commit. **Wait for the owner's explicit approval for this specific commit + push + PR.** None of "tests are
green", this plan, or any earlier approval counts (owner rule). The owner enables the commit via their own
`!`-prefixed one-shot if their git hook requires it — **you do not create the `~/.claude-git-approval`
sentinel**.

- [ ] **Step 4: On explicit approval, make the single commit**

```bash
git add ruthless tests docs/superpowers docs/adr docs/c4 CHANGELOG.md AGENTS.md
git commit
```
Explicit path list, **not** `git add -A` (the tree carries untracked `.serena/` that must not be committed;
G-PLAN-09). `docs/c4` (the directory) stages **both** `architecture.html` **and** `architecture.dsl` —
`/final-review` regenerates both, and committing the rendered diagram without its DSL source leaves the tree
dirty (G-PLAN-10). **Before `git commit`, require `git status --short` to show nothing unstaged or untracked
except `.serena/`** — otherwise a `/final-review` output (e.g. the DSL) was missed; add it and re-check. Commit
message (feat,
describing the whole coherent change), ending with the required Co-Authored-By
attribution line for the implementing session (do not hard-code a model name — use this session's mandated
trailer):

```
feat(grid): native GridSearchStrategy + library-wide store-identity guard (release 0.7.0)

- GridSearchStrategy (cartesian / one_at_a_time / points), zero-dependency, CLI-available
- fingerprint-keyed sqlite resume with a config+objective meta-guard (ADR-003)
- StoreConfig.objective_id now required; Optuna resume identity-guarded + adopt_legacy_store
- bump _version.py to 0.7.0; CHANGELOG; ADR-003; C4 regenerated

<Co-Authored-By line as mandated for this session>
```

- [ ] **Step 5: Push + open the PR (only after the approved commit)**

`git push -u origin feat/grid-strategy`; open the PR `feat/grid-strategy` → `main` with a body summarising the
change and ending with the mandated PR attribution line. Hand the PR to the independent session for
implementation review. Release (`v0.7.0` tag + OIDC publish) is the owner's, after the impl review passes.

---

## Notes for the executor

- **The spec is the source of truth.** Where plan and spec disagree, stop and reconcile with the owner.
- **No scope changes without owner approval.** Surface anything the spec didn't cover; don't defer, drop, or
  expand on your own judgment.
- **Optuna tests need the `[optuna]` extra** (the `uv run` dev env provides it). The lean-install guards (T7)
  prove the *core* import path stays optuna-free.
- **`git status` at start shows** `?? .serena/` (untracked; leave it). Do not `git add -A` until Task 12 Step 4
  after approval — and confirm `.serena/` is either gitignored or intentionally excluded before that add.
