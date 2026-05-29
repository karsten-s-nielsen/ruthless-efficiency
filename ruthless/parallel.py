"""Optional intra-objective parallel map over work-units. NOT the candidate-dispatch path (that is
the backend). A consumer's Objective may call this internally.

GIL caveat: the default "thread" executor only scales for work that releases the GIL
(numpy/pandas/IO). For CPU-bound pure-Python work-units, pass executor="process"."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Literal, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def map_work_units(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    workers: int = 4,
    executor: Literal["thread", "process"] = "thread",
) -> list[R]:
    """Map ``fn`` over ``items`` in parallel, preserving input order.

    Returns a list aligned to ``items``. Falls back to a serial map when ``workers <= 1`` or there is
    at most one item.

    GIL caveat: the default ``executor="thread"`` only scales for work that releases the GIL
    (numpy/pandas/IO). For CPU-bound pure-Python work-units, pass ``executor="process"`` (note the
    usual process-pool constraints — ``fn`` and ``items`` must be picklable).

    Args:
        fn: Callable applied to each item.
        items: Input sequence.
        workers: Max parallel workers (``<= 1`` runs serially).
        executor: ``"thread"`` (default, GIL-bound) or ``"process"`` (CPU-bound)."""
    if workers <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    pool_cls = ThreadPoolExecutor if executor == "thread" else ProcessPoolExecutor
    with pool_cls(max_workers=workers) as pool:
        return list(pool.map(fn, items))
