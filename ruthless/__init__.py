"""Ruthless Efficiency — general optimisation/search substrate.

This module is the curated public API: import the supported surface from `ruthless` directly
(`from ruthless import Candidate, RandomConfig, RandomSearchStrategy, InProcessBackend`). Deep
submodule paths (e.g. `ruthless.strategies.random_.strategy`) are implementation detail and may move
before `1.0`. The optuna/evolve strategies and the compute backends live behind their extras and are
imported from their own namespaces (`ruthless.strategies.optuna_`, `ruthless.strategies.evolve_`,
`ruthless.backends`) so that `import ruthless` stays dependency-light (core only)."""

from __future__ import annotations

from ruthless._fingerprint import fingerprint, fingerprint_model
from ruthless._version import __version__ as __version__  # re-export; not in __all__ (dunder)
from ruthless.backend import ComputeBackend, InProcessBackend
from ruthless.config import (
    Choice,
    EvolveConfig,
    FloatRange,
    GridConfig,
    IntRange,
    OptunaConfig,
    RandomConfig,
    RuthlessConfig,
)
from ruthless.errors import (
    FatalEvaluationError,
    OptimizationError,
    TransientEvaluationError,
    classify_metric,
)
from ruthless.guards import penalty_metrics
from ruthless.objective import CachedObjective, Objective
from ruthless.remote import RemoteObjective, RemoteRef
from ruthless.report import render_json, render_summary_md
from ruthless.result import Candidate, Evaluation, Metrics, ProgressEvent, Result
from ruthless.strategies.grid_ import GridSearchStrategy
from ruthless.strategies.random_.strategy import RandomSearchStrategy
from ruthless.strategy import Direction, Observer, SearchStrategy
from ruthless.testing import assert_cache_equivalence

__all__ = [
    "CachedObjective",
    # value types
    "Candidate",
    "Choice",
    "ComputeBackend",
    "Direction",
    "Evaluation",
    "EvolveConfig",
    "FatalEvaluationError",
    "FloatRange",
    "GridConfig",
    # built-in strategy (core; no extra required)
    "GridSearchStrategy",
    "InProcessBackend",
    "IntRange",
    "Metrics",
    # ports
    "Objective",
    "Observer",
    # errors + guards
    "OptimizationError",
    "OptunaConfig",
    "ProgressEvent",
    "RandomConfig",
    # built-in strategy
    "RandomSearchStrategy",
    "RemoteObjective",
    "RemoteRef",
    "Result",
    # config surface
    "RuthlessConfig",
    "SearchStrategy",
    "TransientEvaluationError",
    "assert_cache_equivalence",
    "classify_metric",
    # cache identity — digest stability is a compatibility contract (ADR-002)
    "fingerprint",
    "fingerprint_model",
    "penalty_metrics",
    # reporting + cache-equivalence harness
    "render_json",
    "render_summary_md",
]
