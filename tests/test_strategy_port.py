from ruthless.result import Result
from ruthless.strategy import Direction, SearchStrategy


class FakeStrategy:  # NOT inheriting SearchStrategy — structural
    def run(self, objective, *, backend) -> Result:
        return Result(best=None)


def test_direction_values():
    assert Direction.MINIMIZE.value == "minimize" and Direction.MAXIMIZE.value == "maximize"


def test_strategy_structural_conformance():
    s: SearchStrategy = FakeStrategy()
    assert s.run(objective=None, backend=None).best is None
    assert isinstance(s, SearchStrategy)
