from ruthless.result import Candidate, ProgressEvent, Result
from ruthless.strategy import Direction, Observer, SearchStrategy


class FakeStrategy:  # NOT inheriting SearchStrategy — structural
    def run(self, objective, *, backend) -> Result:
        return Result(best=None)


def test_direction_values():
    assert Direction.MINIMIZE.value == "minimize" and Direction.MAXIMIZE.value == "maximize"


def test_strategy_structural_conformance():
    s: SearchStrategy = FakeStrategy()
    assert s.run(objective=None, backend=None).best is None
    assert isinstance(s, SearchStrategy)


def test_plain_callable_satisfies_observer():
    seen_numbers: list[int] = []

    def obs(e: ProgressEvent) -> None:  # param NAMED 'e', not 'event' — guards the positional-only '/'
        seen_numbers.append(e.number)

    typed: Observer = obs  # conforms ONLY because Observer.__call__ is positional-only (pyright guard)
    ev = ProgressEvent(number=3, candidate=Candidate(id="t3", params={}), metrics={}, state="complete")
    typed(ev)
    assert seen_numbers == [3]

    # a bound method also conforms (positional-only) — a second pyright guard for the '/'
    collected: list[ProgressEvent] = []
    appender: Observer = collected.append
    appender(ev)
    assert collected == [ev]
