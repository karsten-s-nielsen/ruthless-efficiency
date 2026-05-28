import math

import pytest

from ruthless.errors import (
    FatalEvaluationError,
    OptimizationError,
    TransientEvaluationError,
    classify_metric,
)


def test_classify_metric_passes_finite():
    classify_metric(0.42, candidate_id="c1", metric="score")  # no raise


@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan])
def test_classify_metric_raises_on_nonfinite(bad):
    with pytest.raises(FatalEvaluationError) as exc:
        classify_metric(bad, candidate_id="c1", metric="score")
    assert "c1" in str(exc.value) and "score" in str(exc.value)


def test_hierarchy():
    assert issubclass(FatalEvaluationError, OptimizationError)
    assert issubclass(TransientEvaluationError, OptimizationError)
