"""RandomSearchStrategy — minimal built-in SearchStrategy. First real caller of the port (validates
it before any consumer pins it) and the driver of the dependency-free determinism+convergence gate.
A legitimate zero-dependency baseline; evolve/optuna are separate strategies."""

from __future__ import annotations

import numpy as np

from ruthless._logging import get_logger
from ruthless._provenance import code_identity
from ruthless.backend import ComputeBackend
from ruthless.config import Choice, FloatRange, IntRange, ParamSpec, RandomConfig
from ruthless.errors import classify_metric
from ruthless.objective import Objective
from ruthless.result import Candidate, Evaluation, Result
from ruthless.strategy import Direction

_log = get_logger("strategies.random")


def _sample(spec: ParamSpec, rng: np.random.Generator):
    if isinstance(spec, FloatRange):
        if spec.log:
            return float(np.exp(rng.uniform(np.log(spec.lo), np.log(spec.hi))))
        return float(rng.uniform(spec.lo, spec.hi))
    if isinstance(spec, IntRange):
        return int(rng.integers(spec.lo, spec.hi + 1))  # inclusive hi
    if isinstance(spec, Choice):
        return spec.choices[int(rng.integers(0, len(spec.choices)))]
    raise TypeError(f"unsupported param spec {type(spec).__name__}")


class RandomSearchStrategy:
    """Seeded random search over a :class:`~ruthless.config.RandomConfig` param space.

    Samples ``n_trials`` candidates from the configured param space with a numpy RNG seeded by
    ``seed`` (deterministic for a fixed seed + numpy version), evaluates each via the given backend,
    and returns the best by the configured metric/direction. The zero-dependency baseline strategy.

    Args:
        config: Strategy configuration (metric, direction, n_trials, param_space).
        seed: RNG seed for reproducible sampling.
    """

    def __init__(self, config: RandomConfig, *, seed: int = 42) -> None:
        self._cfg = config
        self._seed = seed
        self._rng = np.random.default_rng(seed)

    def run(self, objective: Objective, *, backend: ComputeBackend) -> Result:
        cfg = self._cfg
        history: list[Evaluation] = []
        best: Evaluation | None = None
        better = (lambda a, b: a < b) if cfg.direction is Direction.MINIMIZE else (lambda a, b: a > b)

        for i in range(cfg.n_trials):
            params = {name: _sample(spec, self._rng) for name, spec in cfg.param_space.items()}
            candidate = Candidate(id=f"r{i}", params=params)
            metrics = backend.evaluate(candidate, objective)
            classify_metric(metrics[cfg.metric], candidate_id=candidate.id, metric=cfg.metric)  # scored only (C-C)
            ev = Evaluation(candidate=candidate, metrics=metrics, ok=True)
            history.append(ev)
            if best is None or better(metrics[cfg.metric], best.metrics[cfg.metric]):
                best = ev
                _log.info("new_best", extra={"trial": i, cfg.metric: metrics[cfg.metric]})

        return Result(
            best=best,
            history=history,
            diagnostics={"n_trials": cfg.n_trials},
            provenance={
                "strategy": "random",
                "seed": self._seed,
                "direction": cfg.direction.value,
                **code_identity(),
            },
        )
