"""Layered config surface, assembled here. A common block (`ruthless.config.common`) + a
discriminated PARAM-SPACE union (`ruthless.config.space`) + a discriminated STRATEGY union
(`ruthless.config.strategies`), with `RuthlessConfig` as the top-level assembly point.

Split from a single module into a package (one reason-to-change per submodule) without moving the
public surface: every name still imports from `ruthless.config` (e.g. `from ruthless.config import
RandomConfig`). Phase 1A registered only `random`; evolve/optuna extend the strategy union later
without a breaking change."""

from __future__ import annotations

import yaml
from pydantic import BaseModel

from ruthless.config.common import (
    BackendConfig,
    EvalConfig,
    EvolutionConfig,
    FitnessConfig,
    LLMConfig,
    LLMModelConfig,
    StoreConfig,
)
from ruthless.config.space import Choice, FloatRange, IntRange, ParamSpec
from ruthless.config.strategies import EvolveConfig, OptunaConfig, RandomConfig, StrategyConfig


class RuthlessConfig(BaseModel):
    seed: int = 42
    strategy: StrategyConfig

    @classmethod
    def from_yaml(cls, path: str) -> RuthlessConfig:
        with open(path) as f:
            return cls.model_validate(yaml.safe_load(f))


__all__ = [
    "BackendConfig",
    "Choice",
    "EvalConfig",
    "EvolutionConfig",
    "EvolveConfig",
    "FitnessConfig",
    "FloatRange",
    "IntRange",
    "LLMConfig",
    "LLMModelConfig",
    "OptunaConfig",
    "ParamSpec",
    "RandomConfig",
    "RuthlessConfig",
    "StoreConfig",
    "StrategyConfig",
]
