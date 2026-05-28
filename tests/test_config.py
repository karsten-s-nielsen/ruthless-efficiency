import pytest
from pydantic import ValidationError

from ruthless.config import Choice, FloatRange, IntRange, RandomConfig, RuthlessConfig


def test_loads_random_with_mixed_param_space():
    cfg = RuthlessConfig.model_validate(
        {
            "seed": 7,
            "strategy": {
                "kind": "random",
                "n_trials": 50,
                "direction": "minimize",
                "metric": "loss",
                "param_space": {
                    "x": {"kind": "float", "lo": -5.0, "hi": 5.0},
                    "n": {"kind": "int", "lo": 1, "hi": 8},
                    "act": {"kind": "choice", "choices": ["relu", "gelu"]},
                    "lr": {"kind": "float", "lo": 1e-4, "hi": 1e-1, "log": True},
                },
            },
        }
    )
    assert isinstance(cfg.strategy, RandomConfig) and cfg.seed == 7
    assert isinstance(cfg.strategy.param_space["x"], FloatRange)
    assert isinstance(cfg.strategy.param_space["n"], IntRange)
    assert isinstance(cfg.strategy.param_space["act"], Choice)
    lr = cfg.strategy.param_space["lr"]
    assert isinstance(lr, FloatRange) and lr.log is True


def test_unknown_strategy_kind_rejected():
    with pytest.raises(ValidationError):
        RuthlessConfig.model_validate({"strategy": {"kind": "no_such"}})


def test_float_range_bounds_validated():
    with pytest.raises(ValidationError):
        FloatRange.model_validate({"kind": "float", "lo": 5.0, "hi": 1.0})
