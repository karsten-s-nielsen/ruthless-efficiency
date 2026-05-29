"""Layered config: a common block + a discriminated STRATEGY union, and a discriminated PARAM-SPACE
union (review H-B: int/choice/log must not force a breaking config change at Phase 2). Phase 1A
registers only the `random` strategy. Persistence is strategy-scoped (spec H1) — added per strategy."""

from __future__ import annotations

from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from ruthless.strategy import Direction


class FloatRange(BaseModel):
    kind: Literal["float"]
    lo: float
    hi: float
    log: bool = False  # log-uniform sampling (cf. Optuna suggest_float(log=True))

    @model_validator(mode="after")
    def _bounds(self) -> FloatRange:
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
    def _bounds(self) -> IntRange:
        if self.lo > self.hi:
            raise ValueError(f"IntRange lo {self.lo} must be <= hi {self.hi}")
        return self


class Choice(BaseModel):
    kind: Literal["choice"]
    choices: list[Any]

    @model_validator(mode="after")
    def _nonempty(self) -> Choice:
        if not self.choices:
            raise ValueError("Choice requires at least one option")
        return self


ParamSpec = Annotated[FloatRange | IntRange | Choice, Field(discriminator="kind")]


_VALID_BACKEND_TYPES = frozenset({"local_cuda", "docker", "hf_jobs", "remote_ssh"})


class BackendConfig(BaseModel):
    """Compute-backend selection (Plan 1B, `[backends]`). `type` is a single backend name or a
    comma-separated list (→ a priority-ordered BackendPool). A value type in core config; it does NOT
    import the `ruthless.backends` package (keeps the import-linter contract). `create_backend`
    interprets it."""

    type: str
    device: str = "cuda:0"
    docker_image: str | None = None
    hf_flavor: str | None = None
    ssh_host: str | None = None
    ssh_user: str | None = None
    ssh_remote_dir: str | None = None
    ssh_python_path: str | None = None

    @model_validator(mode="after")
    def _valid_types(self) -> BackendConfig:
        types = [t.strip() for t in self.type.split(",") if t.strip()]
        if not types:
            raise ValueError("BackendConfig.type must name at least one backend")
        unknown = [t for t in types if t not in _VALID_BACKEND_TYPES]
        if unknown:
            raise ValueError(f"Unknown backend type(s) {unknown}; valid: {sorted(_VALID_BACKEND_TYPES)}")
        return self


class FitnessConfig(BaseModel):
    primary: str
    secondary: str | None = None
    combined_weights: dict[str, float] = {}
    minimize: bool = False

    @model_validator(mode="after")
    def _weights(self) -> FitnessConfig:
        if self.combined_weights:
            total = sum(self.combined_weights.values())
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"combined_weights must sum to 1.0, got {total}")
            if self.primary not in self.combined_weights:
                raise ValueError("primary must be in combined_weights when weights are given")
        return self


class EvolutionConfig(BaseModel):
    iterations: int = 150
    population_size: int = 200
    num_islands: int = 3
    migration_interval: int = 30
    parallel_evaluations: int = 1
    diff_based: bool = True
    early_stopping_patience: int = 40
    checkpoint_interval: int = 5
    code_evolution: bool = False


class LLMModelConfig(BaseModel):
    name: str
    weight: float
    api_base: str
    api_key_env: str


class LLMConfig(BaseModel):
    models: list[LLMModelConfig] = []
    temperature: float = 0.7
    max_tokens: int = 4096

    @model_validator(mode="after")
    def _weights(self) -> LLMConfig:
        if self.models:
            total = sum(m.weight for m in self.models)
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"LLM model weights must sum to 1.0, got {total}")
        return self


class EvalConfig(BaseModel):
    # The lakehouse `dataset` default ("luxury-lakehouse/...") is DROPPED — domain; the consumer's
    # train_and_evaluate / RemoteRef owns data. epochs/seed here are the single source of truth.
    epochs: int = 5
    timeout_seconds: int = 900
    seed: int = 42


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
    validation_profile: str | None = None  # "module:ATTR" -> a ValidationProfile (required if code_evolution)
    pre_validate: str | None = None  # "module:callable" -> (config)->config pre-validation hook

    @model_validator(mode="after")
    def _profile_required_for_code_evolution(self) -> EvolveConfig:
        if self.evolution.code_evolution and not self.validation_profile:
            raise ValueError("validation_profile is required when evolution.code_evolution is True")
        return self


# Strategy union — optuna appends its config in Phase 2.
StrategyConfig = Annotated[RandomConfig | EvolveConfig, Field(discriminator="kind")]


class RuthlessConfig(BaseModel):
    seed: int = 42
    strategy: StrategyConfig

    @classmethod
    def from_yaml(cls, path: str) -> RuthlessConfig:
        with open(path) as f:
            return cls.model_validate(yaml.safe_load(f))
