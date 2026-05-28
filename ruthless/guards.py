"""Degenerate-but-evaluable candidates get a recorded penalty score (steers the sampler away). This
is NOT an error — fatal failures live in ruthless.errors and are never recorded (spec M1)."""

from __future__ import annotations

from ruthless.result import Metrics
from ruthless.strategy import Direction


def penalty_metrics(metric: str, direction: Direction, *, magnitude: float = 1e9) -> Metrics:
    """A finite, deliberately-bad score for the given optimisation direction."""
    return {metric: magnitude if direction is Direction.MINIMIZE else -magnitude}
