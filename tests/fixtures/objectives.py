from ruthless.result import Candidate


class _Quadratic:
    def evaluate(self, candidate: Candidate):
        return {"loss": (candidate.params["x"] - 3.0) ** 2}


quadratic = _Quadratic()
