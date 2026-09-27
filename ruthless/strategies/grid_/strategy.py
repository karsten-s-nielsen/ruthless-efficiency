"""GridSearchStrategy — a zero-dependency baseline strategy over a discrete grid. Owns its loop (spec C1),
returns a Result. Deterministic (no RNG). Optional fingerprint-keyed sqlite resume via GridStore."""

from __future__ import annotations

from ruthless._fingerprint import fingerprint
from ruthless._logging import get_logger
from ruthless._provenance import code_identity
from ruthless.backend import ComputeBackend
from ruthless.config import GridConfig
from ruthless.config.space import grid_plan_size
from ruthless.errors import classify_metric
from ruthless.objective import CachedObjective, Objective
from ruthless.result import Candidate, Evaluation, Result
from ruthless.strategies.grid_.plan import enumerate_points
from ruthless.strategies.grid_.store import GridStore
from ruthless.strategy import Direction

_log = get_logger("strategies.grid")


class GridSearchStrategy:
    """Exhaustive/structured grid search over a :class:`~ruthless.config.GridConfig`. Deterministic; no seed."""

    def __init__(self, config: GridConfig) -> None:
        self._cfg = config

    def run(self, objective: Objective, *, backend: ComputeBackend) -> Result:
        cfg = self._cfg
        plan = enumerate_points(cfg)
        better = (lambda a, b: a < b) if cfg.direction is Direction.MINIMIZE else (lambda a, b: a > b)

        cached: CachedObjective | None = objective if isinstance(objective, CachedObjective) else None
        if cached is not None:
            extra = set(cfg.param_space) - cached.patch_params
            if extra:  # same rule as OptunaStrategy: a non-patch param would reuse a stale invariant
                raise ValueError(f"param_space keys {sorted(extra)} are not in objective.patch_params")
        invariant: object | None = None
        prepared = False

        store = GridStore(cfg) if cfg.store is not None else None
        history: list[Evaluation] = []
        best: Evaluation | None = None
        n_from_store = 0
        try:
            for i, params in enumerate(plan):
                candidate = Candidate(id=f"g{i}", params=params)
                fp = fingerprint(params)
                metrics = store.get(fp) if store is not None else None
                if metrics is None:
                    if cached is not None:
                        if not prepared:
                            invariant = cached.prepare()  # lazy: zero prepare() on a fully-resumed run
                            prepared = True
                        metrics = cached.evaluate_patch(invariant, candidate)
                    else:
                        metrics = backend.evaluate(candidate, objective)
                    classify_metric(metrics[cfg.metric], candidate_id=candidate.id, metric=cfg.metric)
                    if store is not None:
                        store.put(fp, metrics)  # durable before the next point
                else:
                    n_from_store += 1
                ev = Evaluation(candidate=candidate, metrics=metrics, ok=True)
                history.append(ev)
                if best is None or better(metrics[cfg.metric], best.metrics[cfg.metric]):
                    best = ev
                    _log.info("new_best", extra={"point": i, cfg.metric: metrics[cfg.metric]})
        finally:
            if store is not None:
                store.close()

        return Result(
            best=best,
            history=history,
            diagnostics={
                "design": cfg.design,
                "n_points": grid_plan_size(cfg.design, cfg.param_space, cfg.points),
                "n_unique": len(history),
                "n_from_store": n_from_store,
            },
            provenance={
                "strategy": "grid",
                "design": cfg.design,
                "direction": cfg.direction.value,
                **code_identity(),
            },
        )
