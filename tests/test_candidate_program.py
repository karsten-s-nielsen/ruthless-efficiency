from ruthless.result import Candidate


def test_candidate_program_defaults_none_and_is_backward_compatible():
    c = Candidate("c0", {"x": 1.0})
    assert c.program is None  # existing 2-arg construction still works


def test_candidate_program_participates_in_identity():
    a = Candidate("c1", {"x": 1.0}, program="def f(): return 1")
    b = Candidate("c1", {"x": 1.0}, program="def f(): return 1")
    c = Candidate("c1", {"x": 1.0}, program="def f(): return 2")
    assert a == b and hash(a) == hash(b)
    assert a != c  # different source => different candidate
    assert {a, b, c} == {a, c}
