import math

import pytest

from ruthless.backend import InProcessBackend
from ruthless.config import RandomConfig
from ruthless.errors import FatalEvaluationError
from ruthless.result import Candidate
from ruthless.strategies.random_.strategy import RandomSearchStrategy


class Quadratic:
    def evaluate(self, candidate: Candidate):
        return {"loss": (candidate.params["x"] - 3.0) ** 2, "aux": math.nan}  # NaN diagnostic OK


class BrokenScore:
    def evaluate(self, candidate: Candidate):
        return {"loss": math.nan}


def _cfg(n=200):
    return RandomConfig.model_validate(
        {
            "kind": "random",
            "metric": "loss",
            "direction": "minimize",
            "n_trials": n,
            "param_space": {"x": {"kind": "float", "lo": -10.0, "hi": 10.0}},
        }
    )


def test_finds_minimum_and_ignores_nan_diagnostic():
    r = RandomSearchStrategy(_cfg(), seed=42).run(Quadratic(), backend=InProcessBackend())
    assert r.best is not None and abs(r.best.candidate.params["x"] - 3.0) < 0.5 and len(r.history) == 200


def test_result_provenance_carries_code_identity():
    """Captured at RUN time, not render time: render_json may be called later from a different tree."""
    r = RandomSearchStrategy(_cfg(5), seed=42).run(Quadratic(), backend=InProcessBackend())
    assert r.provenance["ruthless_version"]
    assert r.provenance["ruthless_git_state"] in {"clean", "dirty", "unknown"}
    assert r.provenance["strategy"] == "random"  # pre-existing keys survive the spread


def test_deterministic_under_fixed_seed():
    a = RandomSearchStrategy(_cfg(50), seed=42).run(Quadratic(), backend=InProcessBackend())
    b = RandomSearchStrategy(_cfg(50), seed=42).run(Quadratic(), backend=InProcessBackend())
    assert a.best is not None and b.best is not None
    assert a.best.candidate.params == b.best.candidate.params and a.best.metrics == b.best.metrics


def test_nonfinite_scored_metric_raises():
    with pytest.raises(FatalEvaluationError):
        RandomSearchStrategy(_cfg(1), seed=1).run(BrokenScore(), backend=InProcessBackend())


def test_int_and_choice_sampling():
    cfg = RandomConfig.model_validate(
        {
            "kind": "random",
            "metric": "loss",
            "n_trials": 30,
            "param_space": {
                "n": {"kind": "int", "lo": 1, "hi": 3},
                "a": {"kind": "choice", "choices": ["p", "q"]},
            },
        }
    )

    class _Obj:
        def evaluate(self, candidate):
            return {"loss": float(candidate.params["n"])}

    r = RandomSearchStrategy(cfg, seed=0).run(_Obj(), backend=InProcessBackend())
    assert all(1 <= e.candidate.params["n"] <= 3 for e in r.history)
    assert all(e.candidate.params["a"] in ("p", "q") for e in r.history)
