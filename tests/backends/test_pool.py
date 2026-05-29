import threading
import time

import pytest

from ruthless.backends.pool import BackendPool
from ruthless.errors import TransientEvaluationError
from ruthless.result import Candidate


class _Obj:  # minimal Objective; the fake backends ignore it
    def evaluate(self, candidate):
        return {}


_OBJ = _Obj()
_C = Candidate("c", {"x": 1.0})


def _backend(metrics=None, *, available=True, delay=0.0, transient_first=False):
    class _B:
        def __init__(self):
            self.calls = 0

        def evaluate(self, candidate, objective, *, timeout=None):
            self.calls += 1
            if delay:
                time.sleep(delay)
            if transient_first and self.calls == 1:
                raise TransientEvaluationError("flaky")
            return dict(metrics or {"loss": 1.0})

        def available(self):
            return available

    return _B()


def test_single_backend_routes_and_returns():
    b = _backend({"loss": 0.5})
    assert BackendPool([b]).evaluate(_C, _OBJ)["loss"] == 0.5
    assert b.calls == 1


def test_empty_pool_rejected():
    with pytest.raises(ValueError, match="at least one backend"):
        BackendPool([])


def test_available_any_and_none():
    assert BackendPool([_backend(available=False), _backend(available=True)]).available() is True
    assert BackendPool([_backend(available=False)]).available() is False


def test_priority_prefers_first_backend_when_idle():
    first, second = _backend(), _backend()
    pool = BackendPool([first, second])
    pool.evaluate(_C, _OBJ)
    pool.evaluate(_C, _OBJ)
    assert first.calls == 2 and second.calls == 0  # idle pool always re-picks highest priority


def test_two_backends_dispatch_concurrently():
    slow_a, slow_b = _backend(delay=0.3), _backend(delay=0.3)
    pool = BackendPool([slow_a, slow_b])
    start = time.monotonic()
    threads = [threading.Thread(target=lambda: pool.evaluate(_C, _OBJ)) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start
    assert slow_a.calls == 1 and slow_b.calls == 1  # ran on two different backends
    assert elapsed < 0.55  # concurrent (not 0.6s serial)


def test_fast_backend_gets_more_work():
    fast, slow = _backend(delay=0.02), _backend(delay=0.25)
    pool = BackendPool([fast, slow])
    threads = [threading.Thread(target=lambda: pool.evaluate(_C, _OBJ)) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert fast.calls + slow.calls == 5
    assert fast.calls >= 2  # the fast backend re-enters the queue sooner, so it takes more


def test_transient_failure_releases_slot_and_succeeds_on_retry():
    # A backend that raises Transient on its first call still releases its slot; the retry succeeds.
    flaky = _backend({"loss": 0.9}, transient_first=True)
    assert BackendPool([flaky], max_retries=1).evaluate(_C, _OBJ)["loss"] == 0.9
    assert flaky.calls == 2
