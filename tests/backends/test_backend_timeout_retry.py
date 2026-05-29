import pytest

from ruthless.backends.pool import BackendPool
from ruthless.errors import FatalEvaluationError, TransientEvaluationError
from ruthless.result import Candidate


class _Obj:  # minimal Objective; the fake backends ignore it
    def evaluate(self, candidate):
        return {}


_C, _OBJ = Candidate("c", {"x": 1.0}), _Obj()


def _flaky(seq):
    """Backend that raises/returns per a script list (exception instances or metrics dicts)."""
    it = iter(seq)

    class _B:
        def evaluate(self, candidate, objective, *, timeout=None):
            x = next(it)
            if isinstance(x, Exception):
                raise x
            return x

        def available(self):
            return True

    return _B()


def test_transient_retries_on_next_backend_then_succeeds():
    b1 = _flaky([TransientEvaluationError("ssh timeout")])
    b2 = _flaky([{"loss": 0.3}])
    assert BackendPool([b1, b2], max_retries=2).evaluate(_C, _OBJ)["loss"] == 0.3


def test_transient_exhaustion_surfaces():
    pool = BackendPool(
        [_flaky([TransientEvaluationError("t")]), _flaky([TransientEvaluationError("t")])],
        max_retries=1,
    )
    with pytest.raises(TransientEvaluationError):
        pool.evaluate(_C, _OBJ)


def test_fatal_surfaces_immediately_without_retry():
    b1 = _flaky([FatalEvaluationError("broken")])
    b2 = _flaky([{"loss": 0.0}])
    with pytest.raises(FatalEvaluationError):
        BackendPool([b1, b2], max_retries=3).evaluate(_C, _OBJ)
