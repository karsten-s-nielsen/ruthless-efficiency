from ruthless.result import Candidate, Evaluation, Result


def test_candidate_is_hashable_and_value_equal():
    a = Candidate(id="c1", params={"x": 1.0, "y": 2.0})
    b = Candidate(id="c1", params={"y": 2.0, "x": 1.0})  # same id+params, different insertion order
    assert hash(a) == hash(b)  # really hashable; order-independent
    assert a == b
    assert {a, b} == {a}  # usable as a set/dict key (Phase 2 dedup)


def test_result_tracks_best_and_history():
    e0 = Evaluation(candidate=Candidate("c0", {"x": 0.0}), metrics={"score": 1.0}, ok=True)
    e1 = Evaluation(candidate=Candidate("c1", {"x": 1.0}), metrics={"score": 2.0}, ok=True)
    r = Result(best=e1, history=[e0, e1], diagnostics={}, provenance={"seed": 42})
    assert r.best is not None
    assert r.best.candidate.id == "c1" and len(r.history) == 2 and r.provenance["seed"] == 42
