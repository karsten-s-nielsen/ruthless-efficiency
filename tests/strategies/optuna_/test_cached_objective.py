from ruthless.objective import CachedObjective
from ruthless.result import Candidate


class _SumCached:  # NOT inheriting the Protocol — structural
    patch_params = frozenset({"a", "b"})

    def evaluate(self, candidate):  # full recompute
        return {"loss": float(candidate.params["a"] + candidate.params["b"])}

    def prepare(self):  # invariant = a constant offset
        return {"offset": 10.0}

    def evaluate_patch(self, invariant, candidate):
        return {"loss": float(candidate.params["a"] + candidate.params["b"])}


def test_cached_objective_structural_conformance():
    obj: CachedObjective = _SumCached()
    assert isinstance(obj, CachedObjective)
    inv = obj.prepare()
    c = Candidate("c", {"a": 1.0, "b": 2.0})
    assert obj.evaluate_patch(inv, c)["loss"] == 3.0 == obj.evaluate(c)["loss"]
    assert obj.patch_params == {"a", "b"}
