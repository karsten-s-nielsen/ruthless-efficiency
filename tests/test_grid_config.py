import numpy as np
import pytest
from pydantic import ValidationError

from ruthless.config import GridConfig, RuthlessConfig


def _cart(**extra):
    base = {
        "kind": "grid",
        "metric": "loss",
        "design": "cartesian",
        "param_space": {
            "a": {"kind": "choice", "choices": ("x", "y")},
            "b": {"kind": "int", "lo": 1, "hi": 3},
        },
    }
    base.update(extra)
    return base


def test_loads_cartesian_oat_points():
    assert isinstance(RuthlessConfig.model_validate({"strategy": _cart()}).strategy, GridConfig)
    oat = GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x", "b": 1}))
    assert oat.design == "one_at_a_time"
    pts = GridConfig.model_validate(_cart(design="points", points=[{"a": "x", "b": 1}, {"a": "y", "b": 2}]))
    assert pts.points is not None
    assert len(pts.points) == 2


def test_rejects_floatrange():
    with pytest.raises(ValidationError, match="Choice"):
        GridConfig.model_validate(_cart(param_space={"a": {"kind": "float", "lo": 0.0, "hi": 1.0}}))


def test_rejects_empty_param_space():
    with pytest.raises(ValidationError):
        GridConfig.model_validate({"kind": "grid", "metric": "loss", "design": "cartesian", "param_space": {}})


def test_oat_baseline_rules():
    with pytest.raises(ValidationError, match="baseline"):
        GridConfig.model_validate(_cart(design="one_at_a_time"))  # missing baseline
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x"}))  # missing key b
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x", "b": 1, "z": 9}))  # extra key
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x", "b": 9}))  # not a level
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x", "b": 1.0}))  # 1.0 != int 1
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="one_at_a_time", baseline={"a": "x", "b": True}))  # True != int 1


def test_points_rules():
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="points"))  # missing points
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="points", points=[{"a": "x"}]))  # wrong keys
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(design="points", points=[{"a": "x", "b": 99}]))  # not a level


def test_cross_field_exclusivity():
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(baseline={"a": "x", "b": 1}))  # baseline on cartesian
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(points=[{"a": "x", "b": 1}]))  # points on cartesian


def test_size_guard_is_fast_and_bounded():
    big = _cart(param_space={"a": {"kind": "int", "lo": 0, "hi": 10**12}})
    with pytest.raises(ValidationError, match="max_points"):
        GridConfig.model_validate(big)


def test_size_guard_boundary():
    ok = _cart(param_space={"a": {"kind": "int", "lo": 1, "hi": 10}}, max_points=10)
    assert GridConfig.model_validate(ok)
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(param_space={"a": {"kind": "int", "lo": 1, "hi": 11}}, max_points=10))


def test_rejects_unfingerprintable_level():
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(param_space={"a": {"kind": "choice", "choices": (np.int64(3),)}}))


def test_rejects_set_accepts_frozenset():
    with pytest.raises(ValidationError):
        GridConfig.model_validate(_cart(param_space={"a": {"kind": "choice", "choices": ({1, 2},)}}))
    assert GridConfig.model_validate(_cart(param_space={"a": {"kind": "choice", "choices": (frozenset({1, 2}),)}}))
