"""Per-strategy configs + the discriminated STRATEGY union. Phase 1A registered only `random`;
evolve (1B) and optuna (Phase 2) extend the union without a breaking change. Persistence is
strategy-scoped (spec H1) — added per strategy."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from ruthless.config.common import (
    BackendConfig,
    EvalConfig,
    EvolutionConfig,
    FitnessConfig,
    LLMConfig,
    StoreConfig,
)
from ruthless.config.space import ParamSpec
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


# Strategy union — random (1A) + evolve (1B) + optuna (Phase 2).
StrategyConfig = Annotated[RandomConfig | EvolveConfig | OptunaConfig, Field(discriminator="kind")]
