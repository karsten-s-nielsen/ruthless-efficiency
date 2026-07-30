import concurrent.futures
import os
from pathlib import Path

import pytest

from ruthless.errors import FatalEvaluationError, OptimizationError, TransientEvaluationError
from ruthless.parallel import UnitFailure, WorkUnitMapError, _run_all, map_work_units


def _square(n: int) -> int:
    return n * n


def _touch_marker(item: tuple[str, int]) -> int:
    """Record 'this unit ran' in a way that crosses the process boundary (spec §1.7.1)."""
    marker_dir, i = item
    Path(marker_dir, f"{i}.done").write_text("")
    if i == 3:
        raise ValueError(f"unit {i} is bad")
    return i * 10


def _suicide(x: int) -> int:
    """Hard-kill the worker to produce a genuinely dead pool (spec §1.7.2, verified py3.10/win32)."""
    if x == 2:
        os._exit(1)
    return x * 10


def test_thread_map_preserves_order():
    assert map_work_units(_square, [1, 2, 3, 4], workers=2, executor="thread") == [1, 4, 9, 16]


def test_process_map_preserves_order():
    assert map_work_units(_square, [1, 2, 3], workers=2, executor="process") == [1, 4, 9]


# --- error taxonomy -------------------------------------------------------------------


def test_work_unit_map_error_is_an_optimization_error():
    """Pins spec §8.2: WorkUnitMapError sits under OptimizationError but is deliberately OUTSIDE the
    Transient/Fatal evaluation taxonomy, so BackendPool (which retries TransientEvaluationError
    specifically, pool.py:75) can never retry it."""
    assert issubclass(WorkUnitMapError, OptimizationError)
    assert not issubclass(WorkUnitMapError, TransientEvaluationError)
    assert not issubclass(WorkUnitMapError, FatalEvaluationError)


def test_work_unit_map_error_message_and_attributes():
    failures = [UnitFailure(index=1, exception=ValueError("bad")), UnitFailure(index=3, exception=KeyError("k"))]
    exc = WorkUnitMapError(failures, [10, None, 30, None], 4)
    assert exc.failures == failures
    assert exc.results == [10, None, 30, None]
    assert exc.n_items == 4
    assert "2/4 work-units failed" in str(exc)
    assert "unit 1: ValueError: bad" in str(exc)


def test_work_unit_map_error_truncates_a_long_failure_list():
    failures = [UnitFailure(index=i, exception=ValueError(f"e{i}")) for i in range(8)]
    exc = WorkUnitMapError(failures, [None] * 8, 8)
    assert "(+3 more)" in str(exc)
    assert len(exc.failures) == 8  # truncation is display-only, never data loss


# --- _run_all: attempt every unit, deterministically ----------------------------------


@pytest.mark.parametrize("executor", ["thread", "process"])
@pytest.mark.parametrize("workers", [1, 4])
def test_attempted_set_is_independent_of_workers(tmp_path, executor, workers):
    """THE core determinism test (spec §1.4). Every unit is attempted at every `workers`, under BOTH
    executors — so `workers` can no longer decide which of the caller's side effects happened."""
    marker_dir = tmp_path / f"{executor}-{workers}"
    marker_dir.mkdir()
    items = [(str(marker_dir), i) for i in range(8)]
    results, failures = _run_all(_touch_marker, items, workers, executor)
    assert sorted(int(p.stem) for p in marker_dir.glob("*.done")) == list(range(8))
    assert [f.index for f in failures] == [3]
    assert results == [0, 10, 20, None, 40, 50, 60, 70]


def test_failures_are_ordered_by_index():
    """as_completed yields in COMPLETION order, so without the sort the failure list would be
    nondeterministic even though `results` is not."""

    def flaky(i: int) -> int:
        if i in (0, 5):
            raise ValueError(f"bad {i}")
        return i

    _, failures = _run_all(flaky, list(range(8)), 4, "thread")
    assert [f.index for f in failures] == [0, 5]


def test_run_all_does_not_raise_for_unit_failures():
    def always_bad(i: int) -> int:
        raise RuntimeError(f"bad {i}")

    results, failures = _run_all(always_bad, [1, 2, 3], 2, "thread")
    assert results == [None, None, None]
    assert len(failures) == 3
    assert all(isinstance(f.exception, RuntimeError) for f in failures)


def test_broken_pool_propagates_instead_of_becoming_unit_failures():
    """A dead pool voids the attempted-every-unit guarantee, so it must NOT be reported as N
    independent unit failures. Assert on the EXCEPTION TYPE ONLY — how much work completed before the
    pool died is timing-dependent (spec §1.7.2)."""
    with pytest.raises(concurrent.futures.BrokenExecutor):
        _run_all(_suicide, list(range(6)), 4, "process")


# --- the public surface: on_error ------------------------------------------------------


def _flaky(i: int) -> int:
    if i == 3:
        raise ValueError(f"unit {i} is bad")
    return i * 10


def test_raise_path_aggregates_every_failure():
    def two_bad(i: int) -> int:
        if i in (1, 4):
            raise ValueError(f"bad {i}")
        return i

    with pytest.raises(WorkUnitMapError) as ei:
        map_work_units(two_bad, list(range(6)), workers=4)
    assert [f.index for f in ei.value.failures] == [1, 4]
    assert "2/6 work-units failed" in str(ei.value)


def test_raise_path_carries_partial_results():
    """Before this change every completed result was discarded and unrecoverable (spec §1.1)."""
    with pytest.raises(WorkUnitMapError) as ei:
        map_work_units(_flaky, list(range(6)), workers=4)
    assert ei.value.results == [0, 10, 20, None, 40, 50]


def test_original_exception_is_recoverable():
    with pytest.raises(WorkUnitMapError) as ei:
        map_work_units(_flaky, list(range(6)), workers=4)
    original = ei.value.failures[0].exception
    assert isinstance(original, ValueError) and "unit 3 is bad" in str(original)
    assert ei.value.__cause__ is original  # chained, so the traceback stays useful


def test_collect_returns_aligned_results_and_failures():
    results, failures = map_work_units(_flaky, list(range(6)), workers=4, on_error="collect")
    assert results == [0, 10, 20, None, 40, 50]
    assert [f.index for f in failures] == [3]


def test_collect_with_no_failures_returns_empty_failures():
    results, failures = map_work_units(_square, [1, 2, 3], workers=2, on_error="collect")
    assert results == [1, 4, 9]
    assert failures == []


def test_collect_path_can_still_raise_on_pool_death():
    """F3: the `collect` return type invites 'never raises'. A dead pool still propagates, and that is
    the failure mode a collect caller is least prepared for. Exception TYPE only — see §1.7.2."""
    with pytest.raises(concurrent.futures.BrokenExecutor) as ei:
        map_work_units(_suicide, list(range(6)), workers=4, executor="process", on_error="collect")
    assert not isinstance(ei.value, WorkUnitMapError)
