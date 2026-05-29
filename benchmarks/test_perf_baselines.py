"""Performance baselines (pytest-benchmark). NOT part of the default test run — `testpaths` is
`tests/`, so these are collected only when invoked explicitly:

    uv run pytest benchmarks/ --benchmark-only

They measure the two hot paths the optimization audit flagged as benchmark-uncovered: the
``RandomSearchStrategy`` trial loop and the ``assert_cache_equivalence`` harness. Run them before and
after a change to a hot path and compare with ``--benchmark-compare`` (see the measure-before-optimize
discipline)."""

from __future__ import annotations

from ruthless import (
    Candidate,
    InProcessBackend,
    RandomConfig,
    RandomSearchStrategy,
    assert_cache_equivalence,
)


class _Quadratic:
    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        return {"loss": (candidate.params["x"] - 3.0) ** 2}


class _CachedQuadratic:
    patch_params = frozenset({"x"})

    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        return {"loss": (candidate.params["x"] - 3.0) ** 2}

    def prepare(self) -> object:
        return 3.0

    def evaluate_patch(self, invariant: object, candidate: Candidate) -> dict[str, float]:
        return {"loss": (candidate.params["x"] - float(invariant)) ** 2}  # type: ignore[arg-type]


def test_random_search_100_trials(benchmark) -> None:
    cfg = RandomConfig.model_validate(
        {
            "kind": "random",
            "metric": "loss",
            "direction": "minimize",
            "n_trials": 100,
            "param_space": {"x": {"kind": "float", "lo": -10.0, "hi": 10.0}},
        }
    )
    backend = InProcessBackend()
    result = benchmark(lambda: RandomSearchStrategy(cfg, seed=42).run(_Quadratic(), backend=backend))
    assert result.best is not None


def test_assert_cache_equivalence_50_candidates(benchmark) -> None:
    candidates = [Candidate(id=f"c{i}", params={"x": float(i)}) for i in range(50)]
    benchmark(lambda: assert_cache_equivalence(_CachedQuadratic(), candidates))
