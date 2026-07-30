"""Tests for the private core cache-identity primitive (spec §2.3, §3).

Every collision pair here was measured against the pre-fix implementation; they are regression tests,
not hypotheticals."""

import pytest
from pydantic import BaseModel

from ruthless._fingerprint import fingerprint, fingerprint_model


def test_fingerprint_is_deterministic():
    payload = {"epochs": 5, "seed": 42}
    assert fingerprint(payload) == fingerprint(payload) == fingerprint(dict(payload))


def test_fingerprint_length_is_configurable():
    assert len(fingerprint({"a": 1})) == 16
    assert len(fingerprint({"a": 1}, length=8)) == 8


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ({"k": 1}, {"k": "1"}),
        ({"k": 1}, {"k": 1.0}),
        ({"k": 1}, {"k": True}),
        ({"k": None}, {"k": "None"}),
    ],
)
def test_type_tags_prevent_cross_type_collision(a, b):
    assert fingerprint(a) != fingerprint(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ({"cfg": {1: "x"}}, {"cfg": {"1": "x"}}),
        ({"p": {1: 0.5, 2: 0.7}}, {"p": {"1": 0.5, "2": 0.7}}),
        ({"cfg": {1.0: "x"}}, {"cfg": {"1.0": "x"}}),
        ({"cfg": {True: "x"}}, {"cfg": {1: "x"}}),
    ],
)
def test_nested_mapping_keys_are_type_tagged(a, b):
    """F1 regression. The pre-fix code used a bare `str(k)`, which collided all four of these. The
    last pair passed pre-fix only by the accident that `str(True) == "True"` — it must now hold by
    construction."""
    assert fingerprint(a) != fingerprint(b)


def test_separator_collision_is_impossible():
    """The §2.2 regression: the old `f"{a}:{b}"` scheme collided these two."""
    assert fingerprint({"a": "1:2", "b": "3"}) != fingerprint({"a": "1", "b": "2:3"})


def test_key_order_does_not_change_digest():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    assert fingerprint({"c": {"a": 1, "b": 2}}) == fingerprint({"c": {"b": 2, "a": 1}})


def test_nested_containers_are_supported():
    assert fingerprint({"k": [1, 2]}) != fingerprint({"k": (1, 2)})
    assert fingerprint({"k": {1, 2}}) != fingerprint({"k": {1, 3}})
    assert fingerprint({"k": {2, 1}}) == fingerprint({"k": {1, 2}})  # sets are order-insensitive
    assert fingerprint({"k": {}}) != fingerprint({"k": []})


def test_unsupported_value_raises_type_error():
    """Fail-closed. A `str()` fallback is exactly how two distinct objects acquire one digest."""
    with pytest.raises(TypeError, match="unsupported type 'object'"):
        fingerprint({"k": object()})


def test_unsupported_key_raises_type_error():
    """Falls out of routing keys through _canon -> _tag. Claimed so a refactor cannot lose it."""
    with pytest.raises(TypeError, match="unsupported type 'object'"):
        fingerprint({"k": {object(): 1}})


def test_equal_but_distinct_digest_cases_are_deliberate():
    """Spec §2.3 consequences 1 and 2: these pairs compare EQUAL in Python but digest differently. That
    is the safe direction — an unnecessary cache MISS, never a stale HIT."""
    assert {"k": -0.0} == {"k": 0.0}
    assert fingerprint({"k": -0.0}) != fingerprint({"k": 0.0})
    assert {"cfg": {True: "x"}} == {"cfg": {1: "x"}}
    assert fingerprint({"cfg": {True: "x"}}) != fingerprint({"cfg": {1: "x"}})


# --- fingerprint_model: the exclusion-set invalidation scope (§3) ----------------------


class _Cfg(BaseModel):
    epochs: int = 5
    timeout_seconds: int = 900
    seed: int = 42


class _CfgPlusOne(BaseModel):
    """_Cfg with ONE field added - the scenario §3's fail-closed design exists for."""

    epochs: int = 5
    timeout_seconds: int = 900
    seed: int = 42
    learning_rate: float = 0.01


def test_fingerprint_model_is_deterministic():
    assert fingerprint_model(_Cfg()) == fingerprint_model(_Cfg())


def test_included_field_changes_digest():
    assert fingerprint_model(_Cfg(epochs=5)) != fingerprint_model(_Cfg(epochs=6))
    assert fingerprint_model(_Cfg(seed=1)) != fingerprint_model(_Cfg(seed=2))


def test_excluded_field_does_not_change_digest():
    ex = frozenset({"timeout_seconds"})
    assert fingerprint_model(_Cfg(timeout_seconds=1), exclude=ex) == fingerprint_model(
        _Cfg(timeout_seconds=999), exclude=ex
    )


def test_excluding_a_field_changes_the_digest_of_the_same_model():
    """Sanity: the exclusion is actually applied, not silently ignored."""
    assert fingerprint_model(_Cfg()) != fingerprint_model(_Cfg(), exclude=frozenset({"timeout_seconds"}))


def test_new_model_field_changes_digest():
    """THE §3 contract. A field added later is INCLUDED by default, so the worst case of forgetting to
    revisit an exclusion list is an unnecessary recompute (safe), never a stale reuse (wrong)."""
    assert fingerprint_model(_Cfg()) != fingerprint_model(_CfgPlusOne())


def test_fingerprint_model_rejects_unknown_exclusion():
    """Closes the stale-exclusion-NAME gap: rename or delete a field and an inclusion-list design fails
    silently, whereas this raises."""
    with pytest.raises(ValueError, match=r"non-existent field\(s\) \['timeout'\]"):
        fingerprint_model(_Cfg(), exclude=frozenset({"timeout"}))


def test_fingerprint_model_reports_known_fields_in_the_error():
    with pytest.raises(ValueError, match="known fields:"):
        fingerprint_model(_Cfg(), exclude=frozenset({"nope"}))
