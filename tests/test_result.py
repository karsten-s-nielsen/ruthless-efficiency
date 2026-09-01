import dataclasses

import pytest

from ruthless.result import Candidate, Evaluation, ProgressEvent, Result


def test_candidate_params_are_read_only_after_construction():
    c = Candidate(id="c1", params={"x": 1.0})
    with pytest.raises(TypeError):  # MappingProxyType forbids item assignment
        c.params["x"] = 99.0  # type: ignore[index]
    assert c.params == {"x": 1.0}  # compares equal to a plain dict


def test_candidate_does_not_alias_the_caller_dict():
    source = {"x": 1.0}
    c = Candidate(id="c1", params=source)
    source["x"] = 99.0  # mutating the original must not corrupt the candidate's dedup-key invariant
    assert c.params == {"x": 1.0}
    assert dict(c.params) == {"x": 1.0}  # consumers can still get a plain mutable copy


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


def test_progress_event_holds_its_fields():
    c = Candidate(id="t0", params={"x": 1.0})
    ev = ProgressEvent(number=0, candidate=c, metrics={"loss": 2.0, "aux": 1.0}, state="complete")
    assert ev.number == 0
    assert ev.candidate is c
    assert ev.metrics == {"loss": 2.0, "aux": 1.0}
    assert ev.state == "complete"


def test_progress_event_is_frozen():
    ev = ProgressEvent(number=1, candidate=Candidate(id="t1", params={}), metrics={}, state="complete")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.number = 99  # type: ignore[misc]
