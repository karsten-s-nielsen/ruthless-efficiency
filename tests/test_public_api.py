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
    "ProgressEvent",
    "Result",
    "Metrics",
    "Direction",
    # ports
    "Objective",
    "Observer",
    "CachedObjective",
    "SearchStrategy",
    "ComputeBackend",
    "RemoteObjective",
    "RemoteRef",
    "InProcessBackend",
    # built-in strategy (core; no extra required)
    "RandomSearchStrategy",
    "GridSearchStrategy",
    # config surface
    "RuthlessConfig",
    "RandomConfig",
    "OptunaConfig",
    "EvolveConfig",
    "GridConfig",
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


def test_grid_is_core_and_pulls_no_extras() -> None:
    code = (
        "import ruthless, sys; ruthless.GridSearchStrategy;"
        " assert 'optuna' not in sys.modules and 'openevolve' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603 - fixed argv, no shell


def test_optuna_pkg_import_is_lazy() -> None:
    # Importing the optuna_ package (for adopt_legacy_store / OptunaStrategy) must not import optuna at
    # module load; optuna is imported lazily inside run()/adopt_legacy_store().
    code = "import sys, ruthless.strategies.optuna_ as m; m.adopt_legacy_store; assert 'optuna' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603 - fixed argv, no shell


def test_core_observer_types_pull_no_optuna() -> None:
    # Constructing/using the new core observer types must not import optuna: they are pure core. Checked
    # in a clean subprocess so an extra imported by another test cannot mask a regression. (mlflow is
    # never a ruthless dependency, so the meaningful guard is optuna-absence.)
    code = (
        "import sys; from ruthless import ProgressEvent, Observer, Candidate; "
        "ProgressEvent(number=0, candidate=Candidate(id='t0', params={}), metrics={}, state='complete'); "
        "assert 'optuna' not in sys.modules, 'core observer types must not import optuna'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603 - fixed argv, no shell
