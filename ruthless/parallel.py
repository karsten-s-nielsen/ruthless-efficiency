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
    """Map fn over items in parallel, preserving input order."""
    if workers <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    pool_cls = ThreadPoolExecutor if executor == "thread" else ProcessPoolExecutor
    with pool_cls(max_workers=workers) as pool:
        return list(pool.map(fn, items))
