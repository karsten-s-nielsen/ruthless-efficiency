import math

from ruthless.backend import ComputeBackend, InProcessBackend
from ruthless.result import Candidate


class Good:
    def evaluate(self, candidate: Candidate):
        return {"loss": candidate.params["x"] ** 2, "aux_ratio": math.nan}  # NaN diagnostic is allowed


def test_inprocess_returns_metrics_including_nonfinite_diagnostics():
    b: ComputeBackend = InProcessBackend()
    assert b.available() is True
    m = b.evaluate(Candidate("c", {"x": 2.0}), Good())
    assert m["loss"] == 4.0
    assert math.isnan(m["aux_ratio"])  # backend does NOT police diagnostics (C-C)


def test_evaluate_accepts_timeout_kw():
    # timeout is on the port now (H-C); InProcessBackend documents-and-ignores it.
    assert InProcessBackend().evaluate(Candidate("c", {"x": 1.0}), Good(), timeout=5.0)["loss"] == 1.0
