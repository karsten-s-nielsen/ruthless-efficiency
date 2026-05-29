"""OptunaStrategy — resumable Bayesian/sampler calibration on the SearchStrategy port. Owns its loop
via study.optimize; resume = create_study(load_if_exists=True) + a remaining-trials guard (spec C3:
no lost/dup trials + monotone growth + converge; NOT trajectory-identity). Maps the 1A ParamSpec
union to trial.suggest_*; validates only the scored metric; reconstructs best + history from the
study so they span the whole store on resume."""

from __future__ import annotations

from typing import Any

from ruthless._logging import get_logger
from ruthless.backend import ComputeBackend
from ruthless.config import Choice, FloatRange, IntRange, OptunaConfig, ParamSpec
from ruthless.errors import classify_metric
from ruthless.objective import CachedObjective, Objective
from ruthless.result import Candidate, Evaluation, Result

_log = get_logger("strategies.optuna")


def _suggest(trial: Any, name: str, spec: ParamSpec) -> Any:
    if isinstance(spec, FloatRange):
        return trial.suggest_float(name, spec.lo, spec.hi, log=spec.log)
    if isinstance(spec, IntRange):
        return trial.suggest_int(name, spec.lo, spec.hi)
    if isinstance(spec, Choice):
        return trial.suggest_categorical(name, spec.choices)
    raise TypeError(f"unsupported param spec {type(spec).__name__}")


class OptunaStrategy:
    """Resumable Bayesian/sampler calibration over an :class:`~ruthless.config.OptunaConfig` space.

    Drives an Optuna study (TPE or random sampler) via ``study.optimize``. With a SQLite store it is
    resumable (single-process): a remaining-trials guard avoids lost/duplicate trials and ``best`` +
    ``history`` are reconstructed from the whole store. If the objective is a
    :class:`~ruthless.objective.CachedObjective`, the invariant is prepared once and the fast
    ``evaluate_patch`` path is used; tuning a param outside ``patch_params`` is rejected.

    Args:
        config: Strategy configuration (metric, direction, n_trials, sampler, param_space, store).
        seed: Sampler seed (note: Optuna does not persist sampler RNG across resume).
    """

    def __init__(self, config: OptunaConfig, *, seed: int = 42) -> None:
        self._cfg = config
        self._seed = seed

    def run(self, objective: Objective, *, backend: ComputeBackend) -> Result:
        import optuna
        from optuna.samplers import RandomSampler, TPESampler
        from optuna.trial import TrialState

        cfg = self._cfg
        cached_obj: CachedObjective | None = objective if isinstance(objective, CachedObjective) else None
        invariant: object | None = None
        if cached_obj is not None:
            extra = set(cfg.param_space) - cached_obj.patch_params
            if extra:  # H1/M5: tuning a non-patch param would change the cached invariant -> wrong score
                raise ValueError(f"param_space keys {sorted(extra)} are not in objective.patch_params")
            invariant = cached_obj.prepare()

        sampler = TPESampler(seed=self._seed) if cfg.sampler == "tpe" else RandomSampler(seed=self._seed)
        direction = cfg.direction.value  # "minimize"/"maximize" (matches random_/strategy.py)
        storage = f"sqlite:///{cfg.store.path}" if cfg.store else None
        study = optuna.create_study(
            study_name=cfg.store.path if cfg.store else "ruthless-optuna",
            storage=storage,
            sampler=sampler,
            direction=direction,
            load_if_exists=True,
        )
        if cfg.warm_start and len(study.trials) == 0:  # enqueue the baseline ONLY on a fresh study
            study.enqueue_trial(cfg.warm_start)

        def _objective(trial: Any) -> float:
            params = {name: _suggest(trial, name, spec) for name, spec in cfg.param_space.items()}
            candidate = Candidate(id=f"t{trial.number}", params=params)
            metrics = (
                cached_obj.evaluate_patch(invariant, candidate)
                if cached_obj is not None
                else backend.evaluate(candidate, objective)
            )
            # A non-finite SCORED metric raises FatalEvaluationError; Optuna does not catch it
            # (default catch=()) so it propagates out of run() and aborts the study. The aborted trial
            # is recorded FAILED and permanently consumes an n_trials slot (not retried on resume).
            classify_metric(metrics[cfg.metric], candidate_id=candidate.id, metric=cfg.metric)
            for k, v in metrics.items():
                trial.set_user_attr(k, v)  # persisted -> lets resume reconstruct history (B1)
            return metrics[cfg.metric]

        remaining = max(0, cfg.n_trials - len(study.trials))
        if remaining:
            study.optimize(_objective, n_trials=remaining)

        # best + history span the WHOLE store (reconstructed from study.trials, NOT this process). All
        # reconstructed Evaluations are ok=True (Optuna doesn't persist the 1A `ok` flag; filter by metric).
        def _to_eval(t: Any) -> Evaluation:
            return Evaluation(
                candidate=Candidate(id=f"t{t.number}", params=dict(t.params)),
                metrics=dict(t.user_attrs),
                ok=True,
            )

        # Single post-optimize snapshot reused for both the COMPLETE filter and the total count (each
        # `study.trials`/`get_trials` is a storage round-trip; on a resumed SQLite study that reloads
        # every persisted trial). NOTE: the two PRE-optimize reads are deliberately NOT collapsed —
        # they straddle `enqueue_trial`, so reading once would change the warm-start trial count.
        all_trials = study.get_trials(deepcopy=False)
        completed = [t for t in all_trials if t.state == TrialState.COMPLETE]
        history = [_to_eval(t) for t in completed]
        best: Evaluation | None = _to_eval(study.best_trial) if completed else None
        return Result(
            best=best,
            history=history,
            diagnostics={"n_trials": len(all_trials), "n_complete": len(completed), "sampler": cfg.sampler},
            provenance={
                "strategy": "optuna",
                "seed": self._seed,
                "direction": direction,
                "storage": storage,
                "study_name": study.study_name,
            },
        )
