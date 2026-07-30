"""Optional intra-objective parallel map over work-units. NOT the candidate-dispatch path (that is
the backend). A consumer's Objective may call this internally.

GIL caveat: the default "thread" executor only scales for work that releases the GIL
(numpy/pandas/IO). For CPU-bound pure-Python work-units, pass executor="process".

Failure contract: every unit is ALWAYS attempted, so `workers` never changes which units ran. Unit
failures are aggregated into a `WorkUnitMapError` (default) or returned via `on_error="collect"`; a
dead pool propagates `BrokenExecutor` unwrapped."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Literal, TypeVar, cast, overload

from ruthless.errors import OptimizationError

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True)
class UnitFailure:
    """One work-unit that raised. ``index`` indexes into the caller's ``items``."""

    index: int
    exception: BaseException

    def __str__(self) -> str:
        return f"unit {self.index}: {type(self.exception).__name__}: {self.exception}"


class WorkUnitMapError(OptimizationError):
    """One or more work-units raised. Carries EVERY failure AND the partial results.

    Deliberately NOT a Transient/FatalEvaluationError. A work-unit is a sub-step INSIDE one objective
    evaluation, not an evaluation verdict, so classifying it as fatal-or-transient would be a category
    error and would collide with the backend retry contract (``BackendPool`` retries
    ``TransientEvaluationError`` specifically, so a sibling class is structurally un-retryable). It
    subclasses ``OptimizationError`` so ``except OptimizationError`` still catches it.

    NOTE: this is not the only exception ``map_work_units`` can raise — a dead pool propagates
    ``concurrent.futures.BrokenExecutor`` unwrapped, because that voids the attempted-every-unit
    guarantee and so cannot honestly be reported as a per-unit failure.

    TYPING of ``results``: it is ``list[object | None]`` and cannot be narrower. ``except
    WorkUnitMapError as exc`` erases any type parameter, so making this class generic would not give a
    caller back the element type. If you want typed partial results, use ``on_error="collect"``, which
    returns ``list[R | None]`` directly; if you prefer to catch, cast explicitly::

        except WorkUnitMapError as exc:
            partial = cast("list[int | None]", exc.results)

    Both routes return identical values."""

    def __init__(self, failures: Sequence[UnitFailure], results: Sequence[object | None], n_items: int) -> None:
        self.failures: list[UnitFailure] = list(failures)
        self.results: list[object | None] = list(results)
        self.n_items = n_items
        shown = "; ".join(str(f) for f in self.failures[:5])
        if len(self.failures) > 5:
            shown += f"; ... (+{len(self.failures) - 5} more)"
        super().__init__(f"{len(self.failures)}/{n_items} work-units failed: {shown}")


def _run_all(
    fn: Callable[[T], R], items: Sequence[T], workers: int, executor: Literal["thread", "process"]
) -> tuple[list[R | None], list[UnitFailure]]:
    """Attempt EVERY unit. Never raises for a unit failure; ``failures`` is sorted by index.

    Attempting everything unconditionally is what makes ``workers`` stop affecting which units ran — see
    the module docstring and spec §1.4. ``BrokenExecutor`` is the one exception that propagates."""
    n = len(items)
    results: list[R | None] = [None] * n
    failures: list[UnitFailure] = []
    if workers <= 1 or n <= 1:
        for i, x in enumerate(items):
            try:
                results[i] = fn(x)
            except Exception as exc:  # noqa: BLE001 - per-unit isolation IS this function's contract
                failures.append(UnitFailure(index=i, exception=exc))
        return results, failures
    pool_cls = ThreadPoolExecutor if executor == "thread" else ProcessPoolExecutor
    with pool_cls(max_workers=workers) as pool:
        index_of = {pool.submit(fn, x): i for i, x in enumerate(items)}
        for fut in as_completed(index_of):
            i = index_of[fut]
            try:
                results[i] = fut.result()
            except BrokenExecutor:
                raise  # pool-level death: the attempted-every-unit guarantee is void, do not collect
            except Exception as exc:  # noqa: BLE001 - as above
                failures.append(UnitFailure(index=i, exception=exc))
    failures.sort(key=lambda f: f.index)  # as_completed order is nondeterministic; index order is not
    return results, failures


@overload
def map_work_units(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    workers: int = ...,
    executor: Literal["thread", "process"] = ...,
    on_error: Literal["raise"] = ...,
) -> list[R]: ...
@overload
def map_work_units(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    workers: int = ...,
    executor: Literal["thread", "process"] = ...,
    on_error: Literal["collect"],
) -> tuple[list[R | None], list[UnitFailure]]: ...
def map_work_units(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    workers: int = 4,
    executor: Literal["thread", "process"] = "thread",
    on_error: Literal["raise", "collect"] = "raise",
) -> list[R] | tuple[list[R | None], list[UnitFailure]]:
    """Map ``fn`` over ``items`` in parallel, preserving input order.

    EVERY unit is always attempted, at every ``workers`` value and under both executors. That is
    deliberate: work units are consumer code carrying consumer side effects, so a ``workers`` value that
    changed *which* units ran would let a performance knob decide which of the caller's writes happened.

    Cost of that guarantee: a systematic failure now costs a full pass. The serial path used to
    short-circuit at the first bad unit, which is what you want when debugging a shared root cause; it no
    longer does.

    GIL caveat: the default ``executor="thread"`` only scales for work that releases the GIL
    (numpy/pandas/IO). For CPU-bound pure-Python work-units, pass ``executor="process"`` (note the
    usual process-pool constraints — ``fn`` and ``items`` must be picklable).

    Args:
        fn: Callable applied to each item.
        items: Input sequence.
        workers: Max parallel workers (``<= 1`` runs serially). Affects speed only, never which units run.
        executor: ``"thread"`` (default, GIL-bound) or ``"process"`` (CPU-bound).
        on_error: ``"raise"`` (default) returns ``list[R]`` and raises `WorkUnitMapError` if any unit
            failed — the error carries every failure AND the partial results. ``"collect"`` returns
            ``(results, failures)`` with ``None`` in each failed slot; it raises only if the pool itself
            dies (``concurrent.futures.BrokenExecutor``), because that voids the attempted-every-unit
            guarantee and so cannot be reported as a per-unit failure. Unit failures are returned, never
            raised.

    Raises:
        WorkUnitMapError: ``on_error="raise"`` and at least one unit failed.
        concurrent.futures.BrokenExecutor: the pool died (either ``on_error`` value)."""
    results, failures = _run_all(fn, items, workers, executor)
    if on_error == "collect":
        return results, failures
    if failures:
        raise WorkUnitMapError(failures, results, len(items)) from failures[0].exception
    return cast("list[R]", results)
