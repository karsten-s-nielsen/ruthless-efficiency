"""Param-space discriminated union (review H-B: int/choice/log must not force a breaking config
change at Phase 2). `FloatRange` / `IntRange` / `Choice` are dispatched on their `kind` literal.
`Choice.choices` is a tuple — a param space is fixed once configured, so the options are an immutable,
hashable value (matches `Candidate`'s treat-as-immutable contract)."""

from __future__ import annotations

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
