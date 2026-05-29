"""Value types. Candidate is hashable (param values must be hashable; do NOT mutate params after
construction) so Phase 2 can use it as a cache/dedup key (review H-A). The Result returned by a
strategy is the unified surface report.py renders; persistence is strategy-owned (spec H1).
Result is mutable-during-build but should be treated as immutable once returned (review M-C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Metrics = dict[str, float]


@dataclass(frozen=True, eq=False)
class Candidate:
    id: str
    params: dict[str, Any]  # values must be hashable; treat as immutable after construction
    program: str | None = None  # Level-2 candidate source (evolve code-evolution); None for config-only

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


@dataclass
class Result:
    """Treat as immutable once returned by SearchStrategy.run (review M-C)."""

    best: Evaluation | None
    history: list[Evaluation] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
