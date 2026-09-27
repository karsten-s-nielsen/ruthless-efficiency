"""Per-strategy configs + the discriminated STRATEGY union. Phase 1A registered only `random`;
evolve (1B) and optuna (Phase 2) extend the union without a breaking change. Persistence is
strategy-scoped (spec H1) — added per strategy."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from ruthless._fingerprint import fingerprint
from ruthless.config.common import (
    BackendConfig,
    EvalConfig,
    EvolutionConfig,
    FitnessConfig,
    LLMConfig,
    StoreConfig,
)
from ruthless.config.space import Choice, FloatRange, ParamSpec, grid_plan_size, is_level
from ruthless.strategy import Direction


class RandomConfig(BaseModel):
    kind: Literal["random"]
    metric: str
    direction: Direction = Direction.MINIMIZE
    n_trials: int = 50
    param_space: dict[str, ParamSpec] = {}


class EvolveConfig(BaseModel):
    """EvolveStrategy config ([evolve]). The SINGLE serialised source of truth the OpenEvolve worker
    subprocess uses to rebuild a config-derived RemoteObjective + the evaluator. Consumer-code hooks
    are "module:callable" / "module:ATTR" import-strings (resolved via importlib in both the in-process
    path and the worker), since a ProcessPoolExecutor worker gets no live Python objects."""

    kind: Literal["evolve"]
    description: str = ""
    fitness: FitnessConfig
    evaluation: EvalConfig = EvalConfig()  # single source of truth for epochs/seed
    backend: BackendConfig = BackendConfig(type="local_cuda")
    llm: LLMConfig = LLMConfig()
    evolution: EvolutionConfig = EvolutionConfig()
    entrypoint: str  # "module:callable" -> RemoteRef.entrypoint (consumer's train_and_evaluate)
    remote_package: str | None = None  # PEP-723 install spec -> RemoteRef.package (None for ssh/local)
    seed_programs_dir: str  # dir of seed .py programs the run starts from
    prompt_template_dir: str | None = None  # OpenEvolve prompt templates
    search_space_validator: str | None = None  # "module:callable" -> (config)->(ok, reason)
    validation_profile: str | None = None  # "module:ATTR" -> ValidationProfile; code mode needs this or the opt-out
    pre_validate: str | None = None  # "module:callable" -> (config)->config pre-validation hook
    allow_unvalidated_code: bool = False  # code mode w/o a profile: run evolved code UNSANDBOXED (conscious opt-out)

    @model_validator(mode="after")
    def _validation_required_for_code_evolution(self) -> EvolveConfig:
        # Secure-by-default: a code-evolution run must be AST-screened by a profile OR consciously opted out
        # of it. Fail-closed for every consumer (no lakehouse carve-out); silent omission is rejected.
        if self.evolution.code_evolution and self.validation_profile is None and not self.allow_unvalidated_code:
            raise ValueError(
                "code_evolution=True requires a validation_profile, or an explicit "
                "allow_unvalidated_code=True (runs LLM-generated code unsandboxed)"
            )
        return self


class OptunaConfig(BaseModel):
    """OptunaStrategy config ([optuna]). SQLite store = single-process resume only; concurrent dispatch
    over a backend pool (deferred) would require an RDB (§10/§11)."""

    kind: Literal["optuna"]
    metric: str
    direction: Direction = Direction.MINIMIZE
    n_trials: int = 50
    sampler: Literal["tpe", "random"] = "tpe"
    param_space: dict[str, ParamSpec] = {}
    warm_start: dict[str, Any] = {}  # enqueued as the forced first trial (baseline)
    store: StoreConfig | None = None  # None => in-memory study (no resume)

    @model_validator(mode="after")
    def _warm_start_keys(self) -> OptunaConfig:
        extra = set(self.warm_start) - set(self.param_space)
        if extra:  # a typo'd warm-start key would be silently ignored by Optuna — fail loudly
            raise ValueError(f"warm_start keys {sorted(extra)} are not in param_space")
        return self


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
            raise ValueError(f"FloatRange param(s) {sorted(floats)} not allowed in a grid; use a Choice")
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
            raise ValueError(f"grid has {n} points > max_points={self.max_points}; narrow the space or raise it")
        for name, s in ps.items():  # rule 5
            if isinstance(s, Choice):
                for lvl in s.choices:
                    _assert_usable_level(lvl, name)
        if self.design == "one_at_a_time" and self.baseline is not None:  # rule 6 (None-check narrows for pyright)
            if set(self.baseline) != set(ps):
                raise ValueError(f"baseline keys {sorted(self.baseline)} must equal param_space keys {sorted(ps)}")
            for k, v in self.baseline.items():
                _assert_usable_level(v, k)
                if not is_level(v, ps[k]):
                    raise ValueError(f"baseline[{k!r}]={v!r} is not a level of {k!r}")
        if self.design == "points" and self.points is not None:  # rule 7 (None-check narrows for pyright)
            for i, pt in enumerate(self.points):
                if set(pt) != set(ps):
                    raise ValueError(f"points[{i}] keys {sorted(pt)} must equal param_space keys {sorted(ps)}")
                for k, v in pt.items():
                    _assert_usable_level(v, k)
                    if not is_level(v, ps[k]):
                        raise ValueError(f"points[{i}][{k!r}]={v!r} is not a level of {k!r}")
        return self


# Strategy union — random (1A) + evolve (1B) + optuna (Phase 2) + grid (0.7.0).
StrategyConfig = Annotated[RandomConfig | EvolveConfig | OptunaConfig | GridConfig, Field(discriminator="kind")]
