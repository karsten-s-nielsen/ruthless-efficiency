# General Code-Evolution for `EvolveStrategy` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `EvolveStrategy` evolve an arbitrarily-named function (no `config` dict, no `custom_embed`/`custom_layers`) through ruthless — not by bypassing it into OpenEvolve directly.

**Architecture:** Approach B (clean reframe). `code_evolution=True` becomes the single "evolve CODE" switch: always attach the evolved source to the `Candidate` and make the `config = {…}` dict optional. Delete the hardcoded `custom_embed`/`custom_layers` name-detection from core. Validation becomes **secure-by-default**: a `code_evolution=True` run requires a `validation_profile` **or** an explicit `allow_unvalidated_code=True` opt-out — enforced at the config layer (primary) and the evaluator `__init__` (defense-in-depth). Fold `code_evolution` into the seed-cache identity so a stale resume across the upgrade self-heals.

**Tech Stack:** Python ≥3.10, pydantic v2 (`<3`), `openevolve>=0.2.0` (resolved 0.2.27), pytest.

**Spec:** `docs/superpowers/specs/2026-09-12-general-code-evolution-design.md` (approved through two review rounds; records in `D:\Development\_reviews\2026-09-12-ruthless-general-code-evolution-spec.md` and `…-spec-r2.md`).

## Global Constraints

Every task's requirements implicitly include this section.

- **TDD, red→green:** write the failing test, run it, watch it fail for the *stated* reason, then implement the minimal change to green. No implementation before a failing test.
- **No micro-commits / one coherent commit:** Tasks 1–6 accumulate on **one feature branch with NO intermediate commits**. The single commit happens only in Task 7, after the full local gate is green **and Karsten gives explicit per-commit approval**. Ignore the writing-plans template's per-task "Commit" steps — they are overridden here.
- **Feature branch, never a worktree:** branch off `main` in this repo (Task 1).
- **Local quality gate (mirrors CI exactly), all five green before "done":**
  ```bash
  uv run ruff check ruthless tests
  uv run ruff format --check ruthless tests
  uv run pyright
  uv run lint-imports
  uv run pytest -v
  ```
  `pyright` covers both `ruthless` and `tests`.
- **Version single source:** `ruthless/_version.py` only; `pyproject.toml` reads it dynamically.
- **Do NOT re-pin `openevolve`.** The floor stays `>=0.2.0` (`pyproject.toml:22`); the baseline suite is green against the resolved 0.2.27. The handoff's "0.3.2" is the silly-kicks env, not this repo's pin.
- **No digest literal in any `.md`.** `tests/test_docs_no_digest_literals.py` fails on any 16-hex literal in Markdown outside its declared exclusion set — keep CHANGELOG/ADR/CLAUDE prose digest-free (describe, don't quote).
- **`allow_unvalidated_code`** is the chosen opt-out field name (default `False` = secure). If a rename is preferred, change it consistently across config, evaluator, `_build_evaluator`, tests, CHANGELOG, and ADR.

---

## File Structure

**Modified (production):**
- `ruthless/config/strategies.py` — add `EvolveConfig.allow_unvalidated_code`; replace `_profile_required_for_code_evolution` with `_validation_required_for_code_evolution`; update the `validation_profile` field comment.
- `ruthless/strategies/evolve_/evaluator.py` — `_extract_config` returns `{}` on absence; drop `has_custom_embed`/`has_custom_layers` from `Program` + `_load_program`; add `allow_unvalidated_code` param + `__init__` fail-closed guard to `EvolveEvaluator`; rework `evaluate`'s attach/validate block (attach **after** a passing validation).
- `ruthless/strategies/evolve_/strategy.py` — `_build_evaluator` passes `allow_unvalidated_code`; `_eval_fingerprint` folds in `code_evolution`; add `fingerprint` to the `_fingerprint` import; update docstrings.
- `ruthless/_version.py` — `0.5.0` → `0.6.0`.

**Modified (docs):**
- `CHANGELOG.md` — new `## [0.6.0]` section.
- `CLAUDE.md` — "Ships at" line + `[evolve]`/`EvolveStrategy` description.
- `docs/adr/ADR-001-ast-sandbox-security-model.md` — secure-by-default addendum.

**Modified (tests):**
- `tests/test_evolve_config.py` — update the profile-required test; add opt-out-allows test.
- `tests/strategies/evolve/test_evolve_evaluator.py` — split the config-only assertion; add opt-out / reject / lakehouse-shaped-bypass / config-optional tests.
- `tests/strategies/evolve/test_evolve_strategy.py` — add a `_eval_fingerprint` `code_evolution`-sensitivity assertion.

**Created (tests):**
- `tests/strategies/evolve/test_general_code_evolution.py` — the acceptance integration test (silly-kicks shape, end-to-end through ruthless).

---

## Task 1: Feature branch

**Files:** none (git only).

- [ ] **Step 1: Confirm a clean tree on `main`**

Run: `git status --porcelain` (expected: only the untracked spec/plan under `docs/superpowers/`) and `git branch --show-current` (expected: `main`).

- [ ] **Step 2: Create and switch to the feature branch**

```bash
git switch -c feat/general-code-evolution
```

No commit. The spec + plan are untracked and will be included in the Task 7 commit.

---

## Task 2: Config layer — opt-out field + secure-by-default validator

**Files:**
- Modify: `ruthless/config/strategies.py` (EvolveConfig field `:44–50`, validator `:52–56`)
- Test: `tests/test_evolve_config.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `EvolveConfig.allow_unvalidated_code: bool` (default `False`); the model validator `_validation_required_for_code_evolution` raising `pydantic.ValidationError` when `evolution.code_evolution and validation_profile is None and not allow_unvalidated_code`.

- [ ] **Step 1: Write the failing tests**

Replace the existing `test_code_evolution_requires_validation_profile` in `tests/test_evolve_config.py` and add two tests:

```python
def test_code_evolution_without_profile_or_optout_is_rejected():
    with pytest.raises(ValidationError, match="requires a validation_profile"):
        EvolveConfig.model_validate(
            {
                "kind": "evolve",
                "fitness": {"primary": "s"},
                "entrypoint": "m:f",
                "seed_programs_dir": "seeds",
                "evolution": {"code_evolution": True},
            }
        )


def test_code_evolution_optout_allows_no_profile():
    cfg = EvolveConfig.model_validate(
        {
            "kind": "evolve",
            "fitness": {"primary": "s"},
            "entrypoint": "m:f",
            "seed_programs_dir": "seeds",
            "evolution": {"code_evolution": True},
            "allow_unvalidated_code": True,
        }
    )
    assert cfg.allow_unvalidated_code is True
    assert cfg.validation_profile is None


def test_code_evolution_profile_still_satisfies_the_gate():
    cfg = EvolveConfig.model_validate(
        {
            "kind": "evolve",
            "fitness": {"primary": "s"},
            "entrypoint": "m:f",
            "seed_programs_dir": "seeds",
            "evolution": {"code_evolution": True},
            "validation_profile": "pkg.mod:PROFILE",
        }
    )
    assert cfg.allow_unvalidated_code is False and cfg.validation_profile == "pkg.mod:PROFILE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_evolve_config.py -v`
Expected: `test_code_evolution_optout_allows_no_profile` FAILs (`allow_unvalidated_code` is an unknown field / `ValidationError` from the old validator), and the rejection test may fail on the message match — confirming the new contract isn't in place yet.

- [ ] **Step 3: Add the field and replace the validator**

In `ruthless/config/strategies.py`, add the field beside `validation_profile` and update its comment; replace the validator:

```python
    validation_profile: str | None = None  # "module:ATTR" -> a ValidationProfile; required in code mode unless allow_unvalidated_code
    pre_validate: str | None = None  # "module:callable" -> (config)->config pre-validation hook
    allow_unvalidated_code: bool = False  # code_evolution WITHOUT a profile: run LLM-generated code UNSANDBOXED (conscious opt-out)

    @model_validator(mode="after")
    def _validation_required_for_code_evolution(self) -> EvolveConfig:
        if self.evolution.code_evolution and self.validation_profile is None and not self.allow_unvalidated_code:
            raise ValueError(
                "code_evolution=True requires a validation_profile, or an explicit "
                "allow_unvalidated_code=True (runs LLM-generated code unsandboxed)"
            )
        return self
```

(Delete the old `_profile_required_for_code_evolution`; the field ordering just needs `pre_validate` to stay where it was — shown here for context.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_evolve_config.py -v`
Expected: PASS (all config tests, including the unchanged `test_evolution_code_evolution_default_false` and `test_loads_evolve_strategy_via_union`).

---

## Task 3: Evaluator — config-optional, drop name-detection, secure-by-default guard

**Files:**
- Modify: `ruthless/strategies/evolve_/evaluator.py` (`_extract_config :53–66`, `Program :45–50`, `_load_program :69–79`, `EvolveEvaluator.__init__ :83–102`, `EvolveEvaluator.evaluate :104–148`)
- Test: `tests/strategies/evolve/test_evolve_evaluator.py`

**Interfaces:**
- Consumes: `Candidate`, `RemoteObjective`, `ComputeBackend`, `FitnessConfig`, `ValidationProfile`, `validate_program`, `FatalEvaluationError` (all already imported in the module).
- Produces: `EvolveEvaluator(..., code_evolution: bool = False, validation_profile=None, allow_unvalidated_code: bool = False, ...)` that (a) raises `FatalEvaluationError` at construction if `code_evolution and validation_profile is None and not allow_unvalidated_code`; (b) in `evaluate`, attaches `candidate.program = source` in code mode **after** a passing validation, with `config` defaulting to `{}` when the program has no `config = {…}` literal.

- [ ] **Step 1: Write the failing tests**

In `tests/strategies/evolve/test_evolve_evaluator.py`, (a) **replace** `test_evaluate_dispatches_and_computes_combined_score` with two mode-specific tests — `test_code_mode_config_only_attaches_source` (code mode) and `test_hpo_mode_config_only_has_no_program` (HPO mode) — where the code-mode one **keeps the exact weighted-`combined_score == 0.75` pin** (the only exact assertion on the weighted branch of `_compute_combined_score`, evaluator.py:160 — GCE-PLAN-01; do not drop it to `> 0.0`); and (b) add four more tests. The module's `_evaluator` helper already passes `validation_profile=_PROFILE, code_evolution=True`; add a variant helper for the no-profile paths.

```python
def _evaluator_optout(backend, **kw):
    return EvolveEvaluator(
        backend=backend,
        objective=_FakeObjective(),
        fitness_config=FitnessConfig(primary="primary", combined_weights={"primary": 0.75, "aux": 0.25}),
        validation_profile=None,
        code_evolution=True,
        allow_unvalidated_code=True,
        **kw,
    )


def test_code_mode_config_only_attaches_source(tmp_path):
    # was test_evaluate_dispatches_and_computes_combined_score. Under the reframe, code_evolution=True
    # always attaches source; the weighted-combined_score pin is retained (GCE-PLAN-01).
    backend = _FakeBackend(metrics={"primary": 1.0, "aux": 0.0})
    path = _write(tmp_path, 'config = {"hidden_dim": 256}\n')
    result = _evaluator(backend).evaluate(path)
    assert result.metrics["combined_score"] == 0.75  # 0.75*1.0 + 0.25*0.0 — pins the WEIGHTED branch
    assert backend.candidate is not None
    assert backend.candidate.params == {"hidden_dim": 256}
    assert backend.candidate.program is not None  # code mode -> source attached


def test_hpo_mode_config_only_has_no_program(tmp_path):
    backend = _FakeBackend(metrics={"primary": 1.0, "aux": 0.0})
    ev = EvolveEvaluator(
        backend=backend,
        objective=_FakeObjective(),
        fitness_config=FitnessConfig(primary="primary", combined_weights={"primary": 0.75, "aux": 0.25}),
        code_evolution=False,
    )
    ev.evaluate(_write(tmp_path, 'config = {"hidden_dim": 256}\n'))
    assert backend.candidate is not None and backend.candidate.program is None


def test_code_mode_config_optional(tmp_path):
    backend = _FakeBackend(metrics={"primary": 1.0, "aux": 0.0})
    src = "def score(x):\n    return x * 2\n"  # no config = {...}
    _evaluator_optout(backend).evaluate(_write(tmp_path, src))
    assert backend.candidate is not None
    assert backend.candidate.params == {}
    assert backend.candidate.program is not None


def test_code_mode_with_optout_skips_validation(tmp_path):
    backend = _FakeBackend(metrics={"primary": 1.0, "aux": 0.0})
    src = "def anything(a, b):\n    return a + b\n"  # arbitrary name, would fail the sandbox belt if run
    result = _evaluator_optout(backend).evaluate(_write(tmp_path, src))
    assert "combined_score" in result.metrics and result.metrics["combined_score"] > 0.0
    assert backend.candidate is not None and backend.candidate.program is not None


def test_optout_dispatches_lakehouse_shaped_source_unvalidated(tmp_path):
    # GCE-SPEC-07: opt-out bypasses even a custom_embed program (no profile) — source attached, NOT validated.
    backend = _FakeBackend()
    src = """\
        def custom_embed(self, x, y):
            import os
            return x
    """
    result = _evaluator_optout(backend).evaluate(_write(tmp_path, src))
    assert backend.candidate is not None and backend.candidate.program is not None
    assert "validation_rejected" not in str(result.artifacts.get("error", ""))


def test_evaluator_rejects_code_evolution_without_profile_or_optout():
    with pytest.raises(FatalEvaluationError, match="requires a validation_profile"):
        EvolveEvaluator(
            backend=_FakeBackend(),
            objective=_FakeObjective(),
            fitness_config=FitnessConfig(primary="primary"),
            code_evolution=True,
            validation_profile=None,
            allow_unvalidated_code=False,
        )
```

Add `import pytest` at the top of the file if not present. Delete the old `test_evaluate_dispatches_and_computes_combined_score` — but note its two assertions migrate, not vanish: the weighted `combined_score == 0.75` pin moves into `test_code_mode_config_only_attaches_source`, and the `program is None` case is now covered by `test_hpo_mode_config_only_has_no_program`. Keep `test_level2_passes_source_as_candidate_program`, `test_sandbox_rejects_before_dispatch`, the two backend-error tests, and `test_injected_search_space_validator_blocks` unchanged.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/strategies/evolve/test_evolve_evaluator.py -v`
Expected: the new tests FAIL — `test_code_mode_config_optional` errors on the missing-config `ValueError`→sentinel (params not `{}`, program None); `test_evaluator_rejects_...` fails because `EvolveEvaluator.__init__` doesn't yet raise; the optout helper fails because `allow_unvalidated_code` is an unknown kwarg.

- [ ] **Step 3: `_extract_config` returns `{}` on absence**

In `ruthless/strategies/evolve_/evaluator.py`, change the terminal `raise` to a return:

```python
def _extract_config(tree: ast.Module, source: str, filename: str) -> dict[str, Any]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "config":
                value_source = ast.get_source_segment(source, node.value)
                if value_source is None:
                    raise ValueError(f"Cannot extract config value from {filename}")
                raw = ast.literal_eval(value_source)
                if not isinstance(raw, dict):
                    raise ValueError(f"config must be a dict, got {type(raw).__name__} in {filename}")
                return raw
    return {}  # absence is benign (a code program need not carry params); a malformed literal above still raises
```

- [ ] **Step 4: Drop name-detection from `Program` and `_load_program`**

```python
@dataclass(frozen=True)
class Program:
    config: dict[str, Any]
    source: str


def _load_program(program_path: str) -> Program:
    source = Path(program_path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=program_path)
    return Program(config=_extract_config(tree, source, program_path), source=source)
```

- [ ] **Step 5: Add the opt-out param + fail-closed guard to `__init__`**

Add the parameter (after `validation_profile`) and the guard at the top of `__init__`:

```python
    def __init__(
        self,
        *,
        backend: ComputeBackend,
        objective: RemoteObjective,
        fitness_config: FitnessConfig,
        code_evolution: bool = False,
        validation_profile: ValidationProfile | None = None,
        allow_unvalidated_code: bool = False,
        search_space_validator: Callable[[dict[str, Any]], tuple[bool, str]] | None = None,
        pre_validate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        timeout: float | None = None,
    ) -> None:
        if code_evolution and validation_profile is None and not allow_unvalidated_code:
            raise FatalEvaluationError(
                "code_evolution requires a validation_profile, or an explicit "
                "allow_unvalidated_code=True to run LLM-generated code unsandboxed"
            )
        self._backend = backend
        self._objective = objective
        self._fitness_config = fitness_config
        self._code_evolution = code_evolution
        self._validation_profile = validation_profile
        self._allow_unvalidated_code = allow_unvalidated_code
        self._search_space_validator = search_space_validator
        self._pre_validate = pre_validate
        self._timeout = timeout
```

- [ ] **Step 6: Rework the attach/validate block in `evaluate`**

Replace the name-gated block (`:120–130`) with the flag-gated one — **source attached after a passing validation**:

```python
        program_source: str | None = None
        if self._code_evolution:
            if self._validation_profile is not None:
                valid, reason = validate_program(program.source, self._validation_profile, code_evolution=True)
                if not valid:
                    _log.warning("validation_rejected", extra={"program": program_path, "reason": reason})
                    return self._sentinel(f"validation_rejected: {reason}", kind="objective")
            # profile is None here ONLY when allow_unvalidated_code=True (enforced in __init__) — conscious opt-out
            program_source = program.source

        candidate = Candidate(id=Path(program_path).stem, params=config, program=program_source)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/strategies/evolve/test_evolve_evaluator.py -v`
Expected: PASS (all evaluator tests, including the preserved `test_level2_passes_source_as_candidate_program` and `test_sandbox_rejects_before_dispatch`).

- [ ] **Step 8: Run the lakehouse-belt regression gate locally (localize any regression to this task)**

The spec (§5, §7) names the e2e `test_orchestration_gate` + all `test_sandbox.py` as the lakehouse-functionality gate, and the evaluator rework is exactly where it could break. Run them now rather than waiting for Task 7's full gate:

Run: `uv run pytest tests/strategies/evolve/test_sandbox.py tests/e2e/test_evolve_orchestration_gate.py -v`
Expected: PASS unchanged (they supply `_PROFILE`, so they pass the §4 gate and validate `custom_embed`/`custom_layers` exactly as before). A failure here isolates a regression to the evaluator change.

---

## Task 4: Strategy — wire the opt-out + fold `code_evolution` into the seed-cache identity

**Files:**
- Modify: `ruthless/strategies/evolve_/strategy.py` (import `:27`, `_build_evaluator :94–115`, `_eval_fingerprint :146–153`, docstrings)
- Test: `tests/strategies/evolve/test_evolve_strategy.py`

**Interfaces:**
- Consumes: `EvolveConfig.allow_unvalidated_code` (Task 2); `EvolveEvaluator(..., allow_unvalidated_code=...)` (Task 3); the public `fingerprint` from `ruthless._fingerprint`.
- Produces: `_eval_fingerprint(cfg)` whose output differs when `cfg.evolution.code_evolution` differs (all other eval params equal); `_build_evaluator` passing `allow_unvalidated_code=cfg.allow_unvalidated_code`.

- [ ] **Step 1: Write the failing test**

Add to `tests/strategies/evolve/test_evolve_strategy.py`, extending the existing fingerprint test's neighborhood:

```python
def test_eval_fingerprint_tracks_code_evolution(seed_dir):
    """code_evolution determines whether the evolved source is part of the evaluated artifact, so it
    must be in the seed-cache identity (spec §7)."""
    base = strat._eval_fingerprint(_cfg(seed_dir))  # code_evolution defaults to False
    flipped = strat._eval_fingerprint(_cfg(seed_dir, evolution={"code_evolution": True}, allow_unvalidated_code=True))
    assert flipped != base
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategies/evolve/test_evolve_strategy.py::test_eval_fingerprint_tracks_code_evolution -v`
Expected: FAIL with `assert base == base` (equal), because `_eval_fingerprint` currently ignores `code_evolution`.

- [ ] **Step 3: Import `fingerprint` and fold it in**

In `ruthless/strategies/evolve_/strategy.py`, extend the import and rewrite `_eval_fingerprint`:

```python
from ruthless._fingerprint import fingerprint, fingerprint_model
```

```python
def _eval_fingerprint(cfg: EvolveConfig) -> str:
    """Deterministic identity of the params that determine seed-result CONTENT.

    The EvalConfig fields (except `_SEED_CACHE_EXCLUDE`) plus `evolution.code_evolution` — the latter
    because it decides whether the evolved source is attached to the candidate, which changes what a
    config-only seed evaluates to (spec §7). `fingerprint` is Mapping-only, so compose via a mapping."""
    base = fingerprint_model(cfg.evaluation, exclude=_SEED_CACHE_EXCLUDE)
    return fingerprint({"eval": base, "code_evolution": cfg.evolution.code_evolution})
```

- [ ] **Step 4: Wire the opt-out through `_build_evaluator`**

In `_build_evaluator`, pass the flag to the evaluator:

```python
    return EvolveEvaluator(
        backend=backend,
        objective=objective,
        fitness_config=cfg.fitness,
        code_evolution=cfg.evolution.code_evolution,
        validation_profile=profile,
        allow_unvalidated_code=cfg.allow_unvalidated_code,
        search_space_validator=ssv,
        pre_validate=pre,
        timeout=cfg.evaluation.timeout_seconds,
    )
```

- [ ] **Step 5: Run the full strategy test file**

Run: `uv run pytest tests/strategies/evolve/test_evolve_strategy.py -v`
Expected: PASS — the new test, plus the unchanged fingerprint/resume tests (`test_eval_fingerprint_tracks_epochs_and_seed_but_not_timeout`, `test_run_seed_cache_resume_skips_cached`, `test_seed_cache_exclude_matches_the_golden_table`) which compare within a fixed `code_evolution` and so are unaffected by the fold.

---

## Task 5: Acceptance integration test (silly-kicks shape, through ruthless)

**Files:**
- Create: `tests/strategies/evolve/test_general_code_evolution.py`

**Interfaces:**
- Consumes: `EvolveConfig` (Task 2), `_build_evaluator` + `_remote_objective_from_config` (Task 4), a real entrypoint importable by dotted path.
- Produces: proof that a function-body seed (no config, arbitrary name) flows `_load_program` → `Candidate(program=source)` → backend → `objective.evaluate` → `program_to_path` → entrypoint loads the evolved function from `program_path` → metrics → `combined_score`.

- [ ] **Step 1: Write the failing test**

```python
import importlib.util
import textwrap

from ruthless.config import EvolveConfig
from ruthless.strategies.evolve_.strategy import _build_evaluator, _remote_objective_from_config


def _train(*, candidate_config, device, epochs, seed, program_path):
    """Entrypoint (silly-kicks shape): load the evolved function from program_path, run it, score it."""
    spec = importlib.util.spec_from_file_location("_evolved_candidate", program_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.f(3)  # seed evolves f(x) -> x * 2 ; f(3) == 6
    return {"score": float(value)}


class _InProcess:
    """Minimal backend: runs the objective in-process (mirrors InProcessBackend's contract)."""

    def evaluate(self, candidate, objective, *, timeout=None):
        return objective.evaluate(candidate)

    def available(self):
        return True


def _cfg(seed_dir):
    return EvolveConfig.model_validate(
        {
            "kind": "evolve",
            "fitness": {"primary": "score"},  # no weights -> combined_score == score
            "entrypoint": "tests.strategies.evolve.test_general_code_evolution:_train",
            "seed_programs_dir": str(seed_dir),
            "evaluation": {"epochs": 1, "seed": 0},
            "evolution": {"code_evolution": True},
            "allow_unvalidated_code": True,  # general scoring function, no lakehouse-shaped profile
        }
    )


def test_general_code_evolution_runs_through_ruthless(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    (seed_dir / "seed0.py").write_text(
        textwrap.dedent(
            """\
            # EVOLVE-BLOCK-START
            def f(x):
                return x * 2
            # EVOLVE-BLOCK-END
            """
        ),
        encoding="utf-8",
    )

    cfg = _cfg(seed_dir)
    objective = _remote_objective_from_config(cfg)
    evaluator = _build_evaluator(cfg, backend=_InProcess(), objective=objective)

    result = evaluator.evaluate(str(seed_dir / "seed0.py"))

    assert result.metrics["combined_score"] == 6.0  # f(3) == 6, no weights -> combined == score
    assert "error" not in result.metrics  # not the worst-score sentinel
```

- [ ] **Step 2: Run test to verify it fails (before Tasks 2–4 land) / passes (after)**

Run: `uv run pytest tests/strategies/evolve/test_general_code_evolution.py -v`
Expected once Tasks 2–4 are implemented: PASS. (If authored before Tasks 2–4, it fails at config construction on the unknown `allow_unvalidated_code` field — the correct red.)

- [ ] **Step 3: No new production code**

This task is pure acceptance coverage; it should pass on the code from Tasks 2–4 with no further changes. If it does not, the failure is a real defect in those tasks — fix there, not here.

---

## Task 6: Version bump + docs

**Files:**
- Modify: `ruthless/_version.py`, `CHANGELOG.md`, `CLAUDE.md`, `docs/adr/ADR-001-ast-sandbox-security-model.md`

**Interfaces:** none (docs/version only).

- [ ] **Step 1: Bump the version (single source)**

`ruthless/_version.py`:

```python
__version__ = "0.6.0"
```

- [ ] **Step 2: Refresh the editable install so `importlib.metadata` sees 0.6.0**

Run: `uv sync` (or `uv pip install -e .`). Rationale: `uv run` rebuilds only on `pyproject.toml` changes, so a bare `_version.py` bump can leave `importlib.metadata.version("ruthless-efficiency")` stale.

- [ ] **Step 3: Add the CHANGELOG section**

Prepend under the top `## [0.5.0]` header in `CHANGELOG.md` (no digest literals):

```markdown
## [0.6.0] - 2026-09-12

Minor rather than patch: `EvolveStrategy` gains a general code-evolution mode and a new config field, and
the evolve seed-cache key changes once (see Changed). **The `fingerprint`/`fingerprint_model` primitive is
byte-stable — the golden digest table did not move; general (non-evolve) consumer caches are unaffected.**

### Added
- **General code-evolution mode for `EvolveStrategy`.** With `evolution.code_evolution=True`, the evolved
  program source is always attached to the candidate and handed to the entrypoint via `program_path`, and the
  `config = {…}` dict is optional — so a consumer can evolve an arbitrarily-named function (no HPO params, no
  `custom_embed`/`custom_layers`) through ruthless instead of driving OpenEvolve directly.
- **`EvolveConfig.allow_unvalidated_code`** (default `False`) — the explicit opt-out that permits a code run
  without a `validation_profile`.

### Changed
- **`code_evolution` reframed.** Source-attach is now keyed on the flag, not on the hardcoded
  `custom_embed`/`custom_layers` names (which leave the core); the name-detection becomes a consumer concern
  expressed through `validation_profile`.
- **Validation is secure-by-default.** A `code_evolution=True` run requires a `validation_profile` **or**
  `allow_unvalidated_code=True`; the previous "profile required in code mode" rule is generalized (no config
  that was valid at 0.5.0 becomes invalid).
- **Seed-cache invalidation (evolve only).** `_eval_fingerprint` now includes `code_evolution`, so a
  `resume=True` evolve run upgrading from ≤0.5.0 recomputes its seed results once instead of reusing a value
  computed under the old source-attach behavior. This changes the evolve seed-cache key only; it is not a
  `fingerprint` primitive-digest change.

### Security
- Code evolution is now **default-closed**: a run with no `validation_profile` is rejected unless the operator
  consciously sets `allow_unvalidated_code=True`, which runs LLM-generated code unsandboxed. The AST belt
  remains defense-in-depth, not a boundary (ADR-001).
```

- [ ] **Step 4: Update `CLAUDE.md`**

- Change the "Ships at `0.5.0`" line to `0.6.0`.
- In the evolve description, note that `EvolveStrategy` now supports a general code-evolution mode
  (`code_evolution=True` evolves arbitrary code; `config` optional) gated **secure-by-default** (a
  `validation_profile` **or** `allow_unvalidated_code`), and that the `custom_embed`/`custom_layers`
  name-detection is gone from core.

- [ ] **Step 5: Add the ADR-001 addendum**

Append a dated addendum to `docs/adr/ADR-001-ast-sandbox-security-model.md`: as of 0.6.0, code evolution is
default-closed — no `validation_profile` ⇒ the run is rejected unless `allow_unvalidated_code=True`, and
setting that opt-out runs LLM-generated code unsandboxed by conscious operator choice. The AST allowlist
remains a defense-in-depth belt, not a boundary; it is unchanged and still validates only
`custom_embed`/`custom_layers` bodies. (No digest literals.)

- [ ] **Step 6: Sanity-check the docs gate**

Run: `uv run pytest tests/test_docs_no_digest_literals.py -v`
Expected: PASS (no 16-hex literal introduced into any `.md`).

---

## Task 7: Full local gate + single commit (STOP for approval)

**Files:** all of the above (staged together as one coherent commit).

- [ ] **Step 1: Run the full local quality gate**

```bash
uv run ruff check ruthless tests
uv run ruff format --check ruthless tests
uv run pyright
uv run lint-imports
uv run pytest -v
```
Expected: all five green. `lint-imports` must stay green (no new cross-package import; the reframe removes coupling, it doesn't add any). If `ruff format --check` flags anything, run `uv run ruff format ruthless tests` and re-run the gate.

- [ ] **Step 2: Present the diff and STOP**

Run: `git status` and `git --no-pager diff` (plus `git --no-pager diff --stat`). Show Karsten exactly what would be committed — production changes, tests, docs, version, and the untracked spec + plan under `docs/superpowers/`. **Do not commit.** Wait for explicit per-commit approval (Karsten's standing rule; none of "tests green", "the plan says commit", or prior approvals count).

- [ ] **Step 3: Commit only after explicit approval**

On Karsten's explicit "yes", stage everything (code + tests + docs + spec + plan) and commit on `feat/general-code-evolution`:

```bash
git add -A
git commit  # message below
```

Commit message body (bundles the plan + code, one coherent state):

```
feat(evolve): general code-evolution mode for EvolveStrategy (secure-by-default) (release 0.6.0)

code_evolution=True now evolves arbitrary code: the evolved source is always attached to the
candidate (program_path) and the `config = {...}` dict is optional. The hardcoded
custom_embed/custom_layers name-detection leaves the core; validation is secure-by-default
(a validation_profile OR an explicit allow_unvalidated_code opt-out). _eval_fingerprint folds
in code_evolution, invalidating evolve seed caches once (the fingerprint primitive is unchanged).
```

Then append the `Co-Authored-By:` + `Claude-Session:` trailer **for the executing session** — its own
session URL from its environment's git-commit convention, **not** a URL copied from this plan (GCE-PLAN-03).

- [ ] **Step 4: Push / PR / tag — only if and when Karsten asks**

Push the branch and open a PR (squash-merge house style) on request; the `v0.6.0` tag + PyPI release is a separate, later step per the project's release convention.

---

## Self-Review (author, against the spec)

- **Spec coverage:** §2.1 (Program/_load_program) → Task 3 steps 3–4; §2.2 (_extract_config → {}) → Task 3 step 3; §2.3 (evaluate rework + __init__ guard) → Task 3 steps 5–6; §2.4 (config validator + field) → Task 2; §2.5 (_build_evaluator wiring + _eval_fingerprint) → Task 4; §4 (secure-by-default, both directions) → Tasks 2 & 3 tests; §5 (lakehouse preservation) → preserved tests kept green in Task 3; §6 (config optional) → Task 3 `test_code_mode_config_optional`; §7 (seed-cache fold, Mapping payload) → Task 4; §8 (version/CHANGELOG/CLAUDE/ADR/stale comment) → Tasks 2 step 3 (comment) & 6; acceptance → Task 5; GCE-SPEC-07 → Task 3 `test_optout_dispatches_lakehouse_shaped_source_unvalidated`. All covered.
- **Placeholder scan:** no TBD/TODO; every code step carries real code; tests carry real assertions.
- **Type consistency:** `allow_unvalidated_code: bool` is spelled identically across `EvolveConfig`, `EvolveEvaluator.__init__`, `_build_evaluator`, and tests; `_eval_fingerprint` uses the `Mapping` payload `{"eval": base, "code_evolution": …}` (never the tuple form); `validate_program(..., code_evolution=True)` matches the untouched sandbox signature.
