"""Cross-wire failure/score contract (core). The remote worker (on a compute node), the compute
backends, and the EvolveEvaluator all speak a tiny shared vocabulary: a per-candidate metrics dict
that may carry a worst-score *failure marker*. Those marker keys used to be magic strings duplicated
across `backends/base.py`, `backends/remote_worker.py`, and `strategies/evolve_/evaluator.py`
(connascence of meaning — a rename meant coordinated edits across modules with no shared definition).

This module is the single source of truth for the marker. It depends only on the standard library, so
it stays in the pure core (no strategies/backends import)."""

from __future__ import annotations

from collections.abc import Mapping

# The combined fitness score OpenEvolve ranks candidates by (higher = better; 0.0 = worst).
COMBINED_SCORE_KEY = "combined_score"
# Set to 1 by a node-side worker when the OBJECTIVE crashed (vs. a transport failure).
ERROR_KEY = "error"
# Carries the node-side traceback text alongside the failure marker (diagnostic, not a score).
ERROR_TEXT_KEY = "_error_text"

# Max chars of a node-side traceback surfaced in a raised error message. Bounds how much remote
# environment detail (paths, config, env) leaks into the orchestrator's logs/exceptions (CWE-209),
# applied consistently by every backend that surfaces a failure marker.
ERROR_TEXT_SURFACE_LIMIT = 300


def worst_score_metrics() -> dict[str, float]:
    """Return a fresh worst-score sentinel dict (`combined_score=0`, `error=1`).

    A node-side worker cannot raise across the wire, and OpenEvolve needs a score per candidate, so a
    crashed candidate is reported with this marker rather than an exception."""
    return {COMBINED_SCORE_KEY: 0.0, ERROR_KEY: 1.0}


def is_failure_marker(metrics: Mapping[str, object]) -> bool:
    """True if a parsed worker metrics dict is actually a node-side objective-failure marker.

    A backend converts this into a raised `FatalEvaluationError` (never records it as a score)."""
    return metrics.get(ERROR_KEY) == 1 or ERROR_TEXT_KEY in metrics
