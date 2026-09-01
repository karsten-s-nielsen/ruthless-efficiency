import logging
import math

import pytest

from ruthless.backend import InProcessBackend
from ruthless.config import OptunaConfig
from ruthless.errors import FatalEvaluationError
from ruthless.result import Candidate, ProgressEvent
from ruthless.strategies.optuna_.strategy import OptunaStrategy
from ruthless.strategy import SearchStrategy


class Quadratic:
    def evaluate(self, candidate: Candidate):
        return {"loss": (candidate.params["x"] - 3.0) ** 2}


def _cfg(n=60, **kw):
    return OptunaConfig.model_validate(
        {
            "kind": "optuna",
            "metric": "loss",
            "direction": "minimize",
            "n_trials": n,
            "param_space": {"x": {"kind": "float", "lo": -10.0, "hi": 10.0}},
            **kw,
        }
    )


def test_optuna_finds_minimum():
    r = OptunaStrategy(_cfg(), seed=42).run(Quadratic(), backend=InProcessBackend())
    assert r.best is not None and abs(r.best.candidate.params["x"] - 3.0) < 1.0
    assert len(r.history) == 60


def test_warm_start_is_first_trial():
    r = OptunaStrategy(_cfg(n=5, warm_start={"x": 7.5}), seed=1).run(Quadratic(), backend=InProcessBackend())
    assert r.history[0].candidate.params["x"] == 7.5  # enqueued baseline runs first (trial 0)


def test_warm_start_runs_exactly_n_trials():
    # Regression: a fresh warm-started study must run n_trials total (warm-start = the first trial),
    # not n_trials-1. The enqueued WAITING baseline was double-counted — subtracted from the budget
    # AND consumed by study.optimize. At n_trials=2 this collapsed to just the baseline.
    for n in (2, 5):
        r = OptunaStrategy(_cfg(n=n, warm_start={"x": 7.5}), seed=1).run(Quadratic(), backend=InProcessBackend())
        assert r.diagnostics["n_trials"] == n, f"warm_start n_trials={n} ran {r.diagnostics['n_trials']}"
        assert len(r.history) == n


def test_no_warm_start_runs_exactly_n_trials():
    for n in (2, 5):
        r = OptunaStrategy(_cfg(n=n), seed=1).run(Quadratic(), backend=InProcessBackend())
        assert r.diagnostics["n_trials"] == n
        assert len(r.history) == n


def test_int_and_choice_suggested():
    cfg = OptunaConfig.model_validate(
        {
            "kind": "optuna",
            "metric": "loss",
            "n_trials": 20,
            "param_space": {
                "n": {"kind": "int", "lo": 1, "hi": 4},
                "a": {"kind": "choice", "choices": ["p", "q"]},
            },
        }
    )

    class _Obj:
        def evaluate(self, candidate):
            return {"loss": float(candidate.params["n"])}

    r = OptunaStrategy(cfg, seed=0).run(_Obj(), backend=InProcessBackend())
    assert all(1 <= e.candidate.params["n"] <= 4 for e in r.history)
    assert all(e.candidate.params["a"] in ("p", "q") for e in r.history)


class QuadraticWithAux:
    def evaluate(self, candidate):
        x = candidate.params["x"]
        return {"loss": (x - 3.0) ** 2, "aux": 1.0}


class _Cached:
    patch_params = frozenset({"x"})

    def evaluate(self, candidate):
        return {"loss": (candidate.params["x"] - 3.0) ** 2}

    def prepare(self):
        return {"base": 3.0}

    def evaluate_patch(self, invariant, candidate):
        return {"loss": (candidate.params["x"] - invariant["base"]) ** 2}


def test_observer_fires_once_per_completed_trial():
    events: list[ProgressEvent] = []
    r = OptunaStrategy(_cfg(n=8), seed=42).run(Quadratic(), backend=InProcessBackend(), observer=events.append)
    assert [e.number for e in events] == list(range(8))  # one per trial, study-global numbers, in order
    assert all(e.state == "complete" for e in events)
    assert all("x" in e.candidate.params for e in events)
    assert len(r.history) == 8


def test_observer_event_carries_all_metrics_not_only_scored():
    events: list[ProgressEvent] = []
    OptunaStrategy(_cfg(n=4), seed=1).run(QuadraticWithAux(), backend=InProcessBackend(), observer=events.append)
    assert all("loss" in e.metrics and "aux" in e.metrics for e in events)
    assert all(e.metrics["aux"] == 1.0 for e in events)


def test_observer_none_runs_normally():
    r = OptunaStrategy(_cfg(n=6), seed=99).run(Quadratic(), backend=InProcessBackend(), observer=None)
    assert len(r.history) == 6 and r.best is not None


def test_observer_fires_for_warm_start_trial():
    events: list[ProgressEvent] = []
    OptunaStrategy(_cfg(n=5, warm_start={"x": 7.5}), seed=1).run(
        Quadratic(), backend=InProcessBackend(), observer=events.append
    )
    assert events[0].number == 0 and events[0].candidate.params["x"] == 7.5


class _FatalOnSecondEval:
    def __init__(self):
        self.calls = 0

    def evaluate(self, candidate):
        self.calls += 1
        x = candidate.params["x"]
        return {"loss": math.inf if self.calls == 2 else (x - 3.0) ** 2}


def test_fatal_metric_neither_records_nor_observes_and_propagates():
    events: list[ProgressEvent] = []
    with pytest.raises(FatalEvaluationError):
        OptunaStrategy(_cfg(n=5), seed=3).run(_FatalOnSecondEval(), backend=InProcessBackend(), observer=events.append)
    assert [e.number for e in events] == [0]  # only the completed trial; the aborting one fired nothing
    assert all(e.state == "complete" for e in events)


def test_observer_exception_is_isolated(caplog):
    def boom(event):
        raise ValueError("observer boom")

    with caplog.at_level(logging.WARNING, logger="ruthless.strategies.optuna"):
        r = OptunaStrategy(_cfg(n=5), seed=2).run(Quadratic(), backend=InProcessBackend(), observer=boom)
    assert len(r.history) == 5 and r.best is not None  # search completed despite the raising sink
    assert sum(1 for rec in caplog.records if rec.msg == "observer_failed") == 5


def test_observer_isolated_when_it_raises_on_one_trial_only(caplog):
    seen: list[int] = []

    def flaky(event):
        seen.append(event.number)
        if event.number == 1:
            raise ValueError("boom on trial 1")

    with caplog.at_level(logging.WARNING, logger="ruthless.strategies.optuna"):
        r = OptunaStrategy(_cfg(n=5), seed=8).run(Quadratic(), backend=InProcessBackend(), observer=flaky)
    assert r.diagnostics["n_trials"] == 5 and len(r.history) == 5  # study completed all trials
    assert seen == [0, 1, 2, 3, 4]  # every trial still observed
    assert sum(1 for rec in caplog.records if rec.msg == "observer_failed") == 1  # exactly one logged


def test_observer_fires_on_cached_objective_fast_path():
    events: list[ProgressEvent] = []
    OptunaStrategy(_cfg(n=6), seed=5).run(_Cached(), backend=InProcessBackend(), observer=events.append)
    assert [e.number for e in events] == list(range(6))
    assert all("loss" in e.metrics for e in events)


def test_optuna_strategy_still_conforms_to_search_strategy():
    strat: SearchStrategy = OptunaStrategy(_cfg(n=2))  # widened signature must stay a SearchStrategy (type guard)
    assert isinstance(strat, SearchStrategy)
