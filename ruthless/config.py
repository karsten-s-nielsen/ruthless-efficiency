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


class RandomConfig(BaseModel):
    kind: Literal["random"]
    metric: str
    direction: Direction = Direction.MINIMIZE
    n_trials: int = 50
    param_space: dict[str, ParamSpec] = {}


# Strategy union — evolve/optuna append their configs in later plans.
StrategyConfig = Annotated[RandomConfig, Field(discriminator="kind")]


class RuthlessConfig(BaseModel):
    seed: int = 42
    strategy: StrategyConfig

    @classmethod
    def from_yaml(cls, path: str) -> RuthlessConfig:
        with open(path) as f:
            return cls.model_validate(yaml.safe_load(f))
