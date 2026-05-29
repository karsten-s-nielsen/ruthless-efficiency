import pytest
from pydantic import ValidationError

from ruthless.config import OptunaConfig, RuthlessConfig, StoreConfig
from ruthless.strategy import Direction


def test_loads_optuna_with_param_space_and_store():
    cfg = RuthlessConfig.model_validate(
        {
            "seed": 7,
            "strategy": {
                "kind": "optuna",
                "metric": "loss",
                "direction": "minimize",
                "n_trials": 100,
                "sampler": "tpe",
                "param_space": {
                    "x": {"kind": "float", "lo": -5.0, "hi": 5.0},
                    "k3": {"kind": "float", "lo": 0.1, "hi": 5.0, "log": True},
                },
                "warm_start": {"x": 0.0, "k3": 1.0},
                "store": {"kind": "sqlite", "path": "results/study.db"},
            },
        }
    )
    assert isinstance(cfg.strategy, OptunaConfig)
    assert cfg.strategy.direction is Direction.MINIMIZE
    assert isinstance(cfg.strategy.store, StoreConfig)
    assert cfg.strategy.store.kind == "sqlite" and cfg.strategy.warm_start["k3"] == 1.0


def test_optuna_defaults_in_memory_store():
    cfg = OptunaConfig.model_validate({"kind": "optuna", "metric": "loss", "param_space": {}})
    assert cfg.store is None and cfg.sampler == "tpe" and cfg.n_trials == 50


def test_warm_start_key_not_in_param_space_rejected():
    with pytest.raises(ValidationError, match="warm_start"):
        OptunaConfig.model_validate(
            {
                "kind": "optuna",
                "metric": "loss",
                "param_space": {"x": {"kind": "float", "lo": 0.0, "hi": 1.0}},
                "warm_start": {"typo_key": 0.5},  # not a param_space key
            }
        )
