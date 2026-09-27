import math

import pytest

from ruthless.backend import InProcessBackend
from ruthless.config import GridConfig
from ruthless.errors import FatalEvaluationError
from ruthless.objective import CachedObjective
from ruthless.result import Candidate
from ruthless.strategies.grid_ import GridSearchStrategy
from ruthless.strategy import SearchStrategy
from ruthless.testing import assert_cache_equivalence


def _cfg(**extra):
    base = {
        "kind": "grid",
        "metric": "loss",
        "design": "cartesian",
        "param_space": {"b": {"kind": "int", "lo": 1, "hi": 3}},
    }
    base.update(extra)
    return GridConfig.model_validate(base)


class _Quad:
    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        b = candidate.params["b"]
        return {"loss": float((b - 2) ** 2), "aux": float(b)}


def test_best_minimize():
    r = GridSearchStrategy(_cfg()).run(_Quad(), backend=InProcessBackend())
    assert r.best is not None
    assert r.best.candidate.params["b"] == 2
    assert r.best.metrics["loss"] == 0.0


def test_best_maximize():
    r = GridSearchStrategy(_cfg(direction="maximize")).run(_Quad(), backend=InProcessBackend())
    assert r.best is not None
    assert r.best.metrics["loss"] == 1.0  # (1-2)^2 == (3-2)^2 == 1; max over {1,0,1}
    assert r.best.candidate.params["b"] == 1  # tie between b=1 and b=3 -> first in order


def test_tie_goes_to_first():
    class _Const:
        def evaluate(self, candidate: Candidate) -> dict[str, float]:
            return {"loss": 5.0}

    r = GridSearchStrategy(_cfg(param_space={"b": {"kind": "int", "lo": 1, "hi": 2}})).run(
        _Const(), backend=InProcessBackend()
    )
    assert r.best is not None
    assert r.best.candidate.id == "g0"
    assert r.best.candidate.params["b"] == 1


def test_history_carries_full_metrics():
    r = GridSearchStrategy(_cfg()).run(_Quad(), backend=InProcessBackend())
    assert len(r.history) == 3
    assert all("loss" in ev.metrics and "aux" in ev.metrics for ev in r.history)


def test_diagnostics_and_provenance():
    r = GridSearchStrategy(_cfg()).run(_Quad(), backend=InProcessBackend())
    assert r.diagnostics == {"design": "cartesian", "n_points": 3, "n_unique": 3, "n_from_store": 0}
    assert r.provenance["strategy"] == "grid"
    assert r.provenance["design"] == "cartesian"
    assert r.provenance["direction"] == "minimize"
    assert "seed" not in r.provenance
    assert "ruthless_version" in r.provenance


def test_nonfinite_scored_metric_raises():
    class _Bad:
        def evaluate(self, candidate: Candidate) -> dict[str, float]:
            return {"loss": math.inf}

    with pytest.raises(FatalEvaluationError):
        GridSearchStrategy(_cfg()).run(_Bad(), backend=InProcessBackend())


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


def test_cached_extra_param_rejected():
    cfg = _cfg(param_space={"b": {"kind": "int", "lo": 1, "hi": 2}, "c": {"kind": "int", "lo": 0, "hi": 1}})
    with pytest.raises(ValueError, match="patch_params"):
        GridSearchStrategy(cfg).run(_Cached(), backend=InProcessBackend())


def test_cached_prepare_once():
    _Cached.prepared = 0
    GridSearchStrategy(_cfg()).run(_Cached(), backend=InProcessBackend())
    assert _Cached.prepared == 1
    assert isinstance(_Cached(), CachedObjective)


def test_cached_equivalence():
    cands = [Candidate(f"g{i}", {"b": v}) for i, v in enumerate([1, 2, 3])]
    assert_cache_equivalence(_Cached(), cands)


def test_history_ids_contiguous_after_dedup():
    # A points design with a duplicate dedups to 2 distinct points; the strategy assigns g0, g1 — contiguous,
    # no gap where the duplicate was dropped (kills an id mutation like f"g{i*2}"). n_points is pre-dedup.
    cfg = GridConfig.model_validate(
        {
            "kind": "grid",
            "metric": "loss",
            "design": "points",
            "param_space": {"b": {"kind": "int", "lo": 1, "hi": 3}},
            "points": [{"b": 1}, {"b": 1}, {"b": 2}],
        }
    )
    r = GridSearchStrategy(cfg).run(_Quad(), backend=InProcessBackend())
    assert [ev.candidate.id for ev in r.history] == ["g0", "g1"]
    assert [ev.candidate.params["b"] for ev in r.history] == [1, 2]
    assert r.diagnostics == {"design": "points", "n_points": 3, "n_unique": 2, "n_from_store": 0}


def test_conforms_to_search_strategy():
    strategy: SearchStrategy = GridSearchStrategy(_cfg())
    assert strategy is not None
