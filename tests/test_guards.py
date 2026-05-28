import math

from ruthless.guards import penalty_metrics
from ruthless.strategy import Direction


def test_penalty_minimize_is_large_and_finite():
    m = penalty_metrics("loss", Direction.MINIMIZE, magnitude=1e9)
    assert m["loss"] == 1e9 and math.isfinite(m["loss"])  # recordable, not an error


def test_penalty_maximize_is_small():
    assert penalty_metrics("score", Direction.MAXIMIZE, magnitude=1e9)["score"] == -1e9
