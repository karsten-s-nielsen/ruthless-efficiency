from ruthless.objective import Objective
from ruthless.result import Candidate


class Quadratic:  # NOT inheriting Objective — duck-typed conformance
    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        return {"loss": (candidate.params["x"] - 3.0) ** 2}


def test_structural_conformance():
    obj: Objective = Quadratic()
    assert obj.evaluate(Candidate("c", {"x": 3.0}))["loss"] == 0.0
    assert isinstance(obj, Objective)  # NOTE: runtime_checkable is name-only — does not verify signatures
