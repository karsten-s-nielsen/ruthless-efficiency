"""Error taxonomy. FATAL eval failures (crash/timeout/inf-or-NaN on the SCORED metric) are never
recorded as a valid score — they are surfaced (and, for remote backends in Plan 1B, retried when
transient). DEGENERATE-but-valid candidates are a separate concept handled by ruthless.guards (a
recorded penalty score).

NOTE (review M-E): the *who-retries-transient-with-bounded-backoff* contract is owned by the remote
backends in Plan 1B; Phase 1A only defines the taxonomy + the scored-metric finiteness check."""

from __future__ import annotations

import math


class OptimizationError(Exception):
    """Base class for all ruthless errors."""


class TransientEvaluationError(OptimizationError):
    """A retryable failure (e.g. backend timeout, transient network error). Retry contract: Plan 1B."""


class FatalEvaluationError(OptimizationError):
    """A non-retryable evaluation failure. Surfaced with the candidate key; never recorded as a score."""


def classify_metric(value: float, *, candidate_id: str, metric: str) -> None:
    """Raise FatalEvaluationError if the SCORED metric is inf/NaN (a broken evaluation, not a score).

    Callers pass ONLY the optimisation target metric here — diagnostic/auxiliary metrics are allowed
    to be non-finite (review C-C)."""
    if not math.isfinite(value):
        msg = f"non-finite scored metric {metric}={value!r} for candidate {candidate_id} (broken evaluation)"
        raise FatalEvaluationError(msg)
