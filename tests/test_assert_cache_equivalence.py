import pytest
from hypothesis import given
from hypothesis import strategies as st

from ruthless.result import Candidate
from ruthless.testing import assert_cache_equivalence

_PATCH = frozenset({"a", "b"})


class _Good:  # fast path == full recompute; invariant does NOT depend on a/b (correct)
    patch_params = _PATCH

    def evaluate(self, candidate):
        return {"loss": candidate.params["a"] ** 2 + candidate.params["b"]}

    def prepare(self):
        return {"offset": 0.0}

    def evaluate_patch(self, invariant, candidate):
        return {"loss": candidate.params["a"] ** 2 + candidate.params["b"] + invariant["offset"]}


class _Broken:  # fast path disagrees with full recompute
    patch_params = frozenset({"a"})

    def evaluate(self, candidate):
        return {"loss": candidate.params["a"] ** 2}

    def prepare(self):
        return None

    def evaluate_patch(self, invariant, candidate):
        return {"loss": candidate.params["a"]}  # WRONG


class _OverDeclared:  # 'b' is declared a patch_param but actually feeds the (stale) invariant -> H1 bug
    patch_params = _PATCH

    def evaluate(self, candidate):
        return {"loss": candidate.params["a"] + candidate.params["b"]}  # full sees current b

    def prepare(self):
        return {"b_at_prepare": 0.0}  # invariant froze b=0

    def evaluate_patch(self, invariant, candidate):
        return {"loss": candidate.params["a"] + invariant["b_at_prepare"]}  # ignores current b


def test_equivalence_passes_for_consistent_objective():
    cands = [Candidate(f"c{i}", {"a": float(i), "b": float(-i)}) for i in range(5)]
    assert_cache_equivalence(_Good(), cands)  # no raise


def test_equivalence_raises_for_divergent_objective():
    with pytest.raises(AssertionError, match="loss"):
        assert_cache_equivalence(_Broken(), [Candidate("c", {"a": 3.0})])


def test_over_declared_patch_param_caught_when_varied():
    # M3/H1: 'b' is over-declared (feeds the invariant); both a and b vary so the R5 "exercised" check
    # passes and the real failure is the loss mismatch.
    cands = [Candidate("c0", {"a": 1.0, "b": 0.0}), Candidate("c1", {"a": 2.0, "b": 9.0})]
    with pytest.raises(AssertionError, match="loss"):
        assert_cache_equivalence(_OverDeclared(), cands)


def test_unexercised_patch_param_raises():
    # R5: a patch_param held constant across >= 2 candidates is rejected loudly.
    cands = [Candidate("c0", {"a": 1.0, "b": 0.0}), Candidate("c1", {"a": 1.0, "b": 9.0})]  # a constant
    with pytest.raises(AssertionError, match="not exercised"):
        assert_cache_equivalence(_Good(), cands)


@given(a=st.floats(-1e3, 1e3, allow_nan=False), b=st.floats(-1e3, 1e3, allow_nan=False))
def test_equivalence_property_over_sampled_candidates(a, b):
    # M2: hypothesis sweeps the full range against a correct cached objective (no false positives).
    assert_cache_equivalence(_Good(), [Candidate("c", {"a": a, "b": b})])
