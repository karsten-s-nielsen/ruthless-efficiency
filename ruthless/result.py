"""Value types. Candidate is hashable (param values must be hashable; do NOT mutate params after
construction) so Phase 2 can use it as a cache/dedup key (review H-A). The Result returned by a
strategy is the unified surface report.py renders; persistence is strategy-owned (spec H1).
Result is mutable-during-build but should be treated as immutable once returned (review M-C)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

Metrics = dict[str, float]


@dataclass(frozen=True, eq=False)
class Candidate:
    id: str
    params: Mapping[str, Any]  # values must be hashable; READ-ONLY after construction (dedup-key invariant)
    program: str | None = None  # Level-2 candidate source (evolve code-evolution); None for config-only

    def __post_init__(self) -> None:
        # Defensively copy + freeze params (review H-A): the hash/dedup-key invariant must not be
        # corruptible by a later mutation of the dict the caller passed in. Construct from a plain
        # dict; consumers that need a mutable copy do `dict(candidate.params)`.
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))

    def _key(self) -> tuple[str, frozenset, str | None]:
        return (self.id, frozenset(self.params.items()), self.program)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Candidate) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())


@dataclass(frozen=True)
class Evaluation:
    candidate: Candidate
    metrics: Metrics
    ok: bool  # False = penalty/degenerate (recorded); fatal failures are never recorded


@dataclass(frozen=True)
class ProgressEvent:
    """One observation of a completed candidate evaluation, handed to an Observer. Neutral across
    strategies: it names no strategy-specific concept. ``number`` is the STUDY-GLOBAL trial number — it
    matches ``Candidate.id`` (``t{number}``) and the returned ``Result.history``, and does NOT reset on
    resume (a resumed run observes continued numbers such as 20..49, never a fresh 0..29). ``metrics``
    carries every recorded metric (the scored one plus any auxiliaries), so a sink need not know which
    key the strategy optimises. ``state`` is a neutral lowercase string (e.g. "complete"), never a
    backend's own state enum."""

    number: int
    candidate: Candidate
    metrics: Metrics
    state: str


@dataclass
class Result:
    """Treat as immutable once returned by SearchStrategy.run (review M-C)."""

    best: Evaluation | None
    history: list[Evaluation] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
