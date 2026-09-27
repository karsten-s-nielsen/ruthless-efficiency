import pytest

from ruthless.config import Choice, FloatRange, IntRange
from ruthless.config.space import grid_plan_size, is_level, level_count, levels


def _choice(*xs):
    return Choice(kind="choice", choices=tuple(xs))


def test_levels_choice_and_intrange():
    assert levels(_choice("a", "b")) == ("a", "b")
    assert levels(IntRange(kind="int", lo=2, hi=5)) == (2, 3, 4, 5)


def test_levels_floatrange_raises():
    with pytest.raises(TypeError):
        levels(FloatRange(kind="float", lo=0.0, hi=1.0))


def test_level_count_is_arithmetic_for_intrange():
    assert level_count(IntRange(kind="int", lo=0, hi=10**12)) == 10**12 + 1
    assert level_count(_choice("a", "b", "c")) == 3


def test_is_level_type_strict():
    c = _choice(1, 2, 3)
    assert is_level(2, c)
    assert not is_level(2.0, c)
    assert not is_level(True, c)
    r = IntRange(kind="int", lo=0, hi=4)
    assert is_level(3, r)
    assert not is_level(3.0, r)
    assert not is_level(True, r)
    assert not is_level(5, r)


def test_grid_plan_size_by_design():
    ps = {"a": _choice("x", "y"), "b": IntRange(kind="int", lo=1, hi=3)}
    assert grid_plan_size("cartesian", ps, None) == 6
    assert grid_plan_size("one_at_a_time", ps, None) == 1 + 1 + 2
    assert grid_plan_size("points", ps, [{"a": "x", "b": 1}, {"a": "y", "b": 2}]) == 2
