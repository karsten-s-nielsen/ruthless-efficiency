import pytest

from ruthless.backend import InProcessBackend
from ruthless.config import OptunaConfig
from ruthless.strategies.optuna_.strategy import OptunaStrategy


class _Cached:
    patch_params = frozenset({"x"})

    def __init__(self):
        self.prepared = 0
        self.full_calls = 0

    def evaluate(self, candidate):
        self.full_calls += 1
        return {"loss": (candidate.params["x"] - 2.0) ** 2}

    def prepare(self):
        self.prepared += 1
        return {"target": 2.0}

    def evaluate_patch(self, invariant, candidate):
        return {"loss": (candidate.params["x"] - invariant["target"]) ** 2}


def _cfg(params):
    return OptunaConfig.model_validate({"kind": "optuna", "metric": "loss", "n_trials": 30, "param_space": params})


def test_cached_objective_uses_fast_path_and_prepares_once():
    obj = _Cached()
    r = OptunaStrategy(_cfg({"x": {"kind": "float", "lo": -10.0, "hi": 10.0}}), seed=42).run(
        obj, backend=InProcessBackend()
    )
    assert obj.prepared == 1  # prepare() called exactly once
    assert obj.full_calls == 0  # fast path only; full evaluate never called
    assert r.best is not None and abs(r.best.candidate.params["x"] - 2.0) < 1.0


def test_tuning_a_non_patch_param_is_rejected():
    obj = _Cached()  # patch_params = {"x"}
    cfg = _cfg(
        {
            "x": {"kind": "float", "lo": -1.0, "hi": 1.0},
            "y": {"kind": "float", "lo": -1.0, "hi": 1.0},  # y is NOT a patch param
        }
    )
    with pytest.raises(ValueError, match="patch_params"):
        OptunaStrategy(cfg, seed=1).run(obj, backend=InProcessBackend())
