"""ComputeBackend port + the in-process backend. A backend is the INTER-candidate dispatch path
(one evaluation → one compute resource). It returns the objective's metrics verbatim — it does NOT
inspect metric values; the strategy validates its own SCORED metric (review C-C). `timeout` is part
of the port from day one (review H-C); InProcessBackend documents-and-ignores it (only the remote
backends in Plan 1B enforce per-candidate timeout + the transient-retry contract)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ruthless.objective import Objective
from ruthless.result import Candidate, Metrics


@runtime_checkable
class ComputeBackend(Protocol):
    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics: ...
    def available(self) -> bool: ...


class InProcessBackend:
    """The default core backend: calls ``objective.evaluate(candidate)`` in the current process.

    For pure/CPU objectives that need no remote dispatch. ``timeout`` is accepted for port
    compatibility and ignored (there is no in-process cancellation); the remote backends in the
    ``[backends]`` extra enforce it.
    """

    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics:
        # timeout ignored in-process (no cross-process cancellation here); enforced by remote backends in 1B.
        return objective.evaluate(candidate)

    def available(self) -> bool:
        return True
