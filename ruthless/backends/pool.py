"""BackendPool — priority-ordered, concurrent inter-candidate dispatch over the 1A ComputeBackend
port. Ports the lakehouse pool (queue.PriorityQueue; fast backends re-enter sooner so they take more
work; 1h acquire deadlock guard) and adds the transient-retry contract (1A H-C/M-E): a
TransientEvaluationError releases the backend and retries on the next available one up to
`max_retries`; a FatalEvaluationError surfaces immediately; transient exhaustion re-raises the last."""

from __future__ import annotations

import queue

from ruthless._logging import get_logger
from ruthless.backend import ComputeBackend
from ruthless.errors import TransientEvaluationError
from ruthless.objective import Objective
from ruthless.result import Candidate, Metrics

_log = get_logger("backends.pool")
_ACQUIRE_TIMEOUT = 3600  # seconds — deadlock guard waiting for an idle backend


class BackendPool:
    def __init__(self, backends: list[ComputeBackend], *, max_retries: int = 2) -> None:
        if not backends:
            raise ValueError("BackendPool requires at least one backend")
        self._backends = list(backends)
        self._max_retries = max_retries
        self._priority: dict[int, int] = {id(b): i for i, b in enumerate(self._backends)}
        self._available: queue.PriorityQueue[tuple[int, int, ComputeBackend]] = queue.PriorityQueue()
        for b in self._backends:
            self._available.put((self._priority[id(b)], id(b), b))

    def _acquire(self, tried: set[int]) -> tuple[int, int, ComputeBackend]:
        """Acquire a backend, preferring one not yet tried THIS call (so a transient retry goes to a
        different backend), falling back to a tried one when it is the only one available."""
        skipped: list[tuple[int, int, ComputeBackend]] = []
        chosen: tuple[int, int, ComputeBackend] | None = None
        while True:
            try:
                item = self._available.get_nowait()
            except queue.Empty:
                break
            if item[1] not in tried:
                chosen = item
                break
            skipped.append(item)
        for s in skipped:
            self._available.put(s)
        if chosen is not None:
            return chosen
        # No untried backend idle right now: block for any backend (a tried one freeing up, or a busy untried one).
        try:
            return self._available.get(timeout=_ACQUIRE_TIMEOUT)
        except queue.Empty as exc:
            raise TransientEvaluationError(f"no backend available within {_ACQUIRE_TIMEOUT}s") from exc

    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics:
        last: TransientEvaluationError | None = None
        tried: set[int] = set()
        for attempt in range(self._max_retries + 1):
            pri, bid, backend = self._acquire(tried)
            try:
                result = backend.evaluate(candidate, objective, timeout=timeout)
            except TransientEvaluationError as exc:  # retryable: prefer a different backend next attempt
                last = exc
                tried.add(bid)
                _log.info("transient_retry", extra={"attempt": attempt, "error": str(exc)})
                self._available.put((pri, bid, backend))
                continue
            except BaseException:  # success-path-or-fatal: return the slot, then propagate (Fatal surfaces)
                self._available.put((pri, bid, backend))
                raise
            else:
                self._available.put((pri, bid, backend))
                return result
        # Loop exhausted: only reached after at least one TransientEvaluationError (success/fatal exit above).
        raise last if last is not None else TransientEvaluationError("BackendPool made no attempts")

    def available(self) -> bool:
        return any(b.available() for b in self._backends)
