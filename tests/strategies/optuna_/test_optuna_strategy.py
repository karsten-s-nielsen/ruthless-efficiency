from ruthless.backend import InProcessBackend
from ruthless.config import OptunaConfig
from ruthless.result import Candidate
from ruthless.strategies.optuna_.strategy import OptunaStrategy


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
