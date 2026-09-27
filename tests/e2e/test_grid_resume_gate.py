import datetime as dt
from enum import Enum
from pathlib import PurePosixPath

import numpy as np
import pytest

from ruthless.backend import InProcessBackend
from ruthless.config import GridConfig
from ruthless.errors import FatalEvaluationError
from ruthless.objective import CachedObjective
from ruthless.result import Candidate
from ruthless.strategies.grid_ import GridSearchStrategy


class _Color(Enum):
    RED = 1
    BLUE = 2


def _cfg(tmp_path, *, objective_id="obj-v1", **extra):
    base = {
        "kind": "grid",
        "metric": "loss",
        "design": "cartesian",
        "param_space": {"b": {"kind": "int", "lo": 1, "hi": 4}},
        "store": {"kind": "sqlite", "path": str(tmp_path / "g.db"), "objective_id": objective_id},
    }
    base.update(extra)
    return GridConfig.model_validate(base)


class _Counting:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        self.calls += 1
        return {"loss": float(candidate.params["b"])}


class _RaiseAtK:
    def __init__(self, k: int) -> None:
        self.k = k
        self.seen = 0

    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        self.seen += 1
        if self.seen > self.k:
            raise FatalEvaluationError("boom")
        return {"loss": float(candidate.params["b"])}


def _snapshot(result):
    assert result.best is not None
    history = [(ev.candidate.id, dict(ev.candidate.params), ev.metrics) for ev in result.history]
    best = (result.best.candidate.id, dict(result.best.candidate.params), result.best.metrics)
    return history, best


def test_full_resume_zero_evaluations(tmp_path):
    cfg = _cfg(tmp_path)
    fresh = GridSearchStrategy(cfg).run(_Counting(), backend=InProcessBackend())
    obj = _Counting()
    resumed = GridSearchStrategy(cfg).run(obj, backend=InProcessBackend())
    assert obj.calls == 0
    assert resumed.diagnostics["n_from_store"] == 4
    assert len(resumed.history) == 4
    # resumed history (ids/params/metrics) AND best must equal the fresh run (a store hit must still
    # update best; a resumed best of None would slip past a len-only check).
    assert _snapshot(resumed) == _snapshot(fresh)


def test_partial_resume_after_abort(tmp_path):
    cfg = _cfg(tmp_path)
    with pytest.raises(FatalEvaluationError):
        GridSearchStrategy(cfg).run(_RaiseAtK(2), backend=InProcessBackend())  # 2 stored, then abort
    obj = _Counting()
    r = GridSearchStrategy(cfg).run(obj, backend=InProcessBackend())
    assert r.diagnostics["n_from_store"] == 2
    assert obj.calls == 2
    assert len(r.history) == 4


def test_objective_id_change_raises(tmp_path):
    GridSearchStrategy(_cfg(tmp_path, objective_id="v1")).run(_Counting(), backend=InProcessBackend())
    with pytest.raises(ValueError, match="different grid"):
        GridSearchStrategy(_cfg(tmp_path, objective_id="v2")).run(_Counting(), backend=InProcessBackend())


def test_path_and_max_points_change_do_not_raise(tmp_path):
    GridSearchStrategy(_cfg(tmp_path, max_points=100)).run(_Counting(), backend=InProcessBackend())
    GridSearchStrategy(_cfg(tmp_path, max_points=200)).run(_Counting(), backend=InProcessBackend())
    other = GridConfig.model_validate(
        {
            **_cfg(tmp_path).model_dump(),
            "store": {"kind": "sqlite", "path": str(tmp_path / "g2.db"), "objective_id": "obj-v1"},
        }
    )
    GridSearchStrategy(other).run(_Counting(), backend=InProcessBackend())


def test_tag_typed_levels_roundtrip(tmp_path):
    cfg = GridConfig.model_validate(
        {
            "kind": "grid",
            "metric": "loss",
            "design": "cartesian",
            "param_space": {
                "c": {
                    "kind": "choice",
                    "choices": (_Color.RED, PurePosixPath("/x"), dt.datetime(2020, 1, 1), frozenset({1, 2})),
                }
            },
            "store": {"kind": "sqlite", "path": str(tmp_path / "tag.db"), "objective_id": "v1"},
        }
    )

    class _Obj:
        def evaluate(self, candidate: Candidate) -> dict[str, float]:
            return {"loss": 1.0}

    r1 = GridSearchStrategy(cfg).run(_Obj(), backend=InProcessBackend())
    r2 = GridSearchStrategy(cfg).run(_Obj(), backend=InProcessBackend())
    assert len(r1.history) == 4
    assert r2.diagnostics["n_from_store"] == 4


def test_numpy_aux_metric_roundtrip(tmp_path):
    class _Obj:
        def evaluate(self, candidate: Candidate) -> dict[str, float]:
            return {"loss": float(candidate.params["b"]), "aux": np.float32(0.5)}  # type: ignore  # numpy aux

    cfg = _cfg(tmp_path)
    GridSearchStrategy(cfg).run(_Obj(), backend=InProcessBackend())
    r = GridSearchStrategy(cfg).run(_Obj(), backend=InProcessBackend())
    assert r.history[0].metrics["aux"] == 0.5


def test_cached_full_resume_zero_prepare(tmp_path):
    class _Cached:
        patch_params = frozenset({"b"})
        prepared = 0

        def evaluate(self, candidate: Candidate) -> dict[str, float]:
            return {"loss": float(candidate.params["b"])}

        def prepare(self) -> dict[str, int]:
            _Cached.prepared += 1
            return {"inv": 1}

        def evaluate_patch(self, invariant: object, candidate: Candidate) -> dict[str, float]:
            return {"loss": float(candidate.params["b"])}

    assert isinstance(_Cached(), CachedObjective)
    cfg = _cfg(tmp_path)
    GridSearchStrategy(cfg).run(_Cached(), backend=InProcessBackend())
    _Cached.prepared = 0
    GridSearchStrategy(cfg).run(_Cached(), backend=InProcessBackend())
    assert _Cached.prepared == 0
