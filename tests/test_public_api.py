"""The curated top-level public API. These imports are the supported surface; deep submodule paths
(`ruthless.strategies.random_.strategy`, etc.) are implementation detail. Pinning the surface here
makes an accidental removal a test failure (Hyrum's Law: the first consumer will import these)."""

from __future__ import annotations

import subprocess
import sys

import ruthless

_EXPECTED_PUBLIC = {
    # value types
    "Candidate",
    "Evaluation",
    "Result",
    "Metrics",
    "Direction",
    # ports
    "Objective",
    "CachedObjective",
    "SearchStrategy",
    "ComputeBackend",
    "RemoteObjective",
    "RemoteRef",
    "InProcessBackend",
    # built-in strategy (core; no extra required)
    "RandomSearchStrategy",
    # config surface
    "RuthlessConfig",
    "RandomConfig",
    "OptunaConfig",
    "EvolveConfig",
    "FloatRange",
    "IntRange",
    "Choice",
    # errors + guards
    "OptimizationError",
    "TransientEvaluationError",
    "FatalEvaluationError",
    "classify_metric",
    "penalty_metrics",
    # reporting + cache-equivalence harness
    "render_json",
    "render_summary_md",
    "assert_cache_equivalence",
    # cache identity (public since 0.4.0 — digest stability is a compatibility contract, see ADR-002)
    "fingerprint",
    "fingerprint_model",
    # metadata
    "__version__",
}


def test_all_is_declared_and_complete() -> None:
    assert hasattr(ruthless, "__all__")
    assert set(ruthless.__all__) == _EXPECTED_PUBLIC - {"__version__"}


def test_every_public_name_is_importable_from_the_top_level() -> None:
    for name in _EXPECTED_PUBLIC:
        assert hasattr(ruthless, name), f"ruthless.{name} is missing from the public API"


def test_from_ruthless_import_star_exposes_only_all() -> None:
    ns: dict[str, object] = {}
    exec("from ruthless import *", ns)  # noqa: S102 - controlled, tests the public surface
    exported = {k for k in ns if not k.startswith("__")}
    assert exported == set(ruthless.__all__)


def test_top_level_import_does_not_require_optional_extras() -> None:
    # `import ruthless` must work on the lean (core-only) install: it must not transitively import
    # optuna or openevolve (those live behind the [optuna]/[evolve] extras). Checked in a clean
    # subprocess so an extra imported by another test in this process cannot mask a regression.
    code = "import ruthless, sys; assert 'optuna' not in sys.modules and 'openevolve' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603 - fixed argv, no shell
