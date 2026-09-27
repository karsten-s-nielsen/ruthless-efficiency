"""Param-space discriminated union (review H-B: int/choice/log must not force a breaking config
change at Phase 2). `FloatRange` / `IntRange` / `Choice` are dispatched on their `kind` literal.
`Choice.choices` is a tuple — a param space is fixed once configured, so the options are an immutable,
hashable value (matches `Candidate`'s treat-as-immutable contract)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


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
    choices: tuple[Any, ...]

    @model_validator(mode="after")
    def _nonempty(self) -> Choice:
        if not self.choices:
            raise ValueError("Choice requires at least one option")
        return self


ParamSpec = Annotated[FloatRange | IntRange | Choice, Field(discriminator="kind")]


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
