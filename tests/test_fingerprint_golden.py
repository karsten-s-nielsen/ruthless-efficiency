"""Golden digest table — the pinned bytes of ruthless's cache-identity primitive.

WHY THIS FILE EXISTS. `tests/test_fingerprint.py` is entirely RELATIONAL: every assertion there is
`a != b` or `a == a`. That catches a collision but not a *shift* — a `_tag` change can move every
digest in the codebase while leaving every relation intact. Consumers persist these digests as cache
keys, so a shift silently orphans their caches and triggers a full recompute with nothing reporting
it. Only pinned bytes catch that.

THIS FILE IS THE SINGLE SOURCE OF TRUTH FOR PINNED DIGESTS. No `.md` file may quote one — a spec is a
historical document and would drift, or worse, be lifted back into this table on the assumption it had
been checked.

READ BEFORE EDITING A VALUE. Changing any digest below is a BREAKING change under `ruthless`'s
stability contract (see `ruthless.fingerprint`'s docstring and ADR-002), including when it falls out of
a correctness fix. Editing this table is deliberately the friction that makes such a change visible.

COVERAGE OF `_tag` BRANCHES IS A REVIEW OBLIGATION, NOT AN AUTOMATED ONE. `test_every_case_is_pinned`
proves every payload here has a pinned digest, but nothing proves every `_tag` branch has a payload —
so a new branch can land with no case and this table stays green while the new type goes unguarded
indefinitely. Any change extending `_tag` must add a payload here in the same commit, and a reviewer
must check that it did.

FIXTURE NAMES ARE PART OF THE DIGEST. `_tag` tags an enum by its CLASS NAME, so renaming `_Colour`,
`_Shade`, `_Level` or `_Name` below changes those digests. Rename them only with the same care as an
algorithm change.

PATH FLAVOURS ARE ALWAYS EXPLICIT. Never write a bare `Path` into `_PAYLOADS`: it resolves to the
platform-native flavour at construction time, so a value pinned on Windows would disagree with the
Linux runner for any input containing a backslash or a drive letter. `PurePosixPath`/`PureWindowsPath`
keep every pinned byte platform-independent by construction. The one place a `Path` annotation is
allowed is `_Rich.out_dir`, whose value is a forward-slash literal that `as_posix()` normalises
identically on both platforms.

PYTHON FLOOR IS 3.10. `enum.StrEnum` is 3.11+; `_Name` below is the 3.10-compatible equivalent.
"""

from __future__ import annotations

import datetime as dt
import enum
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
from pydantic import BaseModel

from ruthless import fingerprint, fingerprint_model
from ruthless.config.common import EvalConfig


class _Colour(enum.Enum):
    RED = "red"


class _Shade(enum.Enum):
    RED = "red"  # same VALUE as _Colour.RED, different class


class _Level(enum.IntEnum):
    ONE = 1


class _Name(str, enum.Enum):
    """3.10-compatible stand-in for `enum.StrEnum` — a member IS a `str`, which is the trap."""

    A = "a"


class _Cfg(BaseModel):
    epochs: int = 5
    timeout_seconds: int = 900
    seed: int = 42


class _Rich(BaseModel):
    out_dir: Path = Path("runs/a")  # forward-slash literal ONLY — see module docstring
    colour: _Colour = _Colour.RED
    started: dt.date = dt.date(2026, 7, 30)


_PAYLOADS: dict[str, Mapping[str, object]] = {
    # --- scalars ---------------------------------------------------------------
    "int-positive": {"v": 1},
    "int-negative": {"v": -7},
    "int-zero": {"v": 0},
    "bool-true": {"v": True},
    "bool-false": {"v": False},
    "float-one": {"v": 1.0},
    "float-zero": {"v": 0.0},
    "float-negative-zero": {"v": -0.0},
    "float-nan": {"v": float("nan")},
    "float-inf": {"v": float("inf")},
    "float-negative-inf": {"v": float("-inf")},
    "str-simple": {"v": "a"},
    "str-empty": {"v": ""},
    "str-non-ascii": {"v": "café"},  # pins the ensure_ascii=True escaping path
    "none": {"v": None},
    # --- paths (flavour always explicit) ---------------------------------------
    "path-posix-slash": {"v": PurePosixPath("a/b")},
    "path-windows-slash": {"v": PureWindowsPath("a/b")},
    "path-windows-backslash": {"v": PureWindowsPath("a\\b")},
    "path-posix-backslash": {"v": PurePosixPath("a\\b")},
    # --- enums (class name is inside the digest) -------------------------------
    "enum-colour-red": {"v": _Colour.RED},
    "enum-shade-red": {"v": _Shade.RED},
    "enum-intenum-one": {"v": _Level.ONE},
    "enum-strenum-a": {"v": _Name.A},
    # --- dates and times -------------------------------------------------------
    "date-plain": {"v": dt.date(2026, 7, 30)},
    "datetime-naive": {"v": dt.datetime(2026, 7, 30, 12, 0, 0)},  # deliberately naive
    "datetime-aware-utc": {"v": dt.datetime(2026, 7, 30, 12, 0, 0, tzinfo=dt.timezone.utc)},
    # --- containers ------------------------------------------------------------
    "list-two": {"v": [1, 2]},
    "tuple-two": {"v": (1, 2)},
    "set-two": {"v": {1, 2}},
    "frozenset-two": {"v": frozenset({1, 2})},
    "list-empty": {"v": []},
    "dict-empty": {"v": {}},
    "mapping-nested": {"v": {"a": 1, "b": {"c": 2}}},
    # --- mapping keys (every key goes through _canon too) ----------------------
    "mapping-key-int": {"v": {1: "x"}},
    "mapping-key-str": {"v": {"1": "x"}},
    "mapping-key-bool": {"v": {True: "x"}},
    "mapping-key-float": {"v": {1.0: "x"}},
    "mapping-key-path": {"v": {PurePosixPath("a"): 1}},
    "mapping-key-enum": {"v": {_Colour.RED: 1}},
    # --- a realistic multi-key payload -----------------------------------------
    "multi-key": {"epochs": 5, "seed": 42, "carrier": "v1"},
}

_MODEL_CASES: dict[str, Callable[[], str]] = {
    "model-plain": lambda: fingerprint_model(_Cfg()),
    "model-excluded": lambda: fingerprint_model(_Cfg(), exclude=frozenset({"timeout_seconds"})),
    "model-rich-path-enum-date": lambda: fingerprint_model(_Rich()),
    # Evolve's REAL seed-cache payload. Imported from core config, never from the strategy package —
    # that is what lets the lean Windows CI leg carry this case (spec §3.4).
    "evolve-seed-cache": lambda: fingerprint_model(EvalConfig(), exclude=frozenset({"timeout_seconds"})),
}

# Do NOT hand-edit to make a test pass — see the module docstring.
_EXPECTED: dict[str, str] = {
    "int-positive": "0c929d97a64c891f",
    "int-negative": "666a691c7b39bc6c",
    "int-zero": "1cd1b9cbe9478735",
    "bool-true": "a8fcf1affab4cf0c",
    "bool-false": "7494ab4acfa58085",
    "float-one": "f37efdd1b8806641",
    "float-zero": "ae83e851ac842ebe",
    "float-negative-zero": "7e9ac9e62ccecc18",
    "float-nan": "13cbf964a363d406",
    "float-inf": "d1e134518c6fbf9a",
    "float-negative-inf": "5e816133d9dc8c00",
    "str-simple": "f42c6de6de351b46",
    "str-empty": "470385cb2413b369",
    "str-non-ascii": "0fb906e302e160dd",
    "none": "baaaa7d62549a8eb",
    "path-posix-slash": "880052445f7d5299",
    "path-windows-slash": "880052445f7d5299",
    "path-windows-backslash": "880052445f7d5299",
    "path-posix-backslash": "95d25f1363afcb75",
    "enum-colour-red": "9dbc3e18044c79b2",
    "enum-shade-red": "f104d481f49f4aea",
    "enum-intenum-one": "a2e00aec81e9f7e8",
    "enum-strenum-a": "828ae0ad4d696608",
    "date-plain": "9f7a00ad70ed8659",
    "datetime-naive": "f9fb318344d7b13f",
    "datetime-aware-utc": "0ec2f9bf59a86b45",
    "list-two": "1c965d1626690236",
    "tuple-two": "05abd685e9ed77ea",
    "set-two": "1321294bffb96f99",
    "frozenset-two": "1321294bffb96f99",
    "list-empty": "7a4bce6457996197",
    "dict-empty": "6c4110ba588f7ab7",
    "mapping-nested": "0d4a646c178d4a81",
    "mapping-key-int": "075068145f46dd25",
    "mapping-key-str": "4d2124d3691899e5",
    "mapping-key-bool": "c7ccb8f39dc44ed1",
    "mapping-key-float": "49c6ae1a18600342",
    "mapping-key-path": "a042f068256ae792",
    "mapping-key-enum": "ecb95191dbee61b2",
    "multi-key": "40c98877efa2b714",
}

_EXPECTED_MODELS: dict[str, str] = {
    "model-plain": "e0648b716dfd0e89",
    "model-excluded": "2b4352d2feda9981",
    "model-rich-path-enum-date": "af8794b2b12aa9db",
    "evolve-seed-cache": "2b4352d2feda9981",
}


_BREAKING = """
GOLDEN DIGEST CHANGED for case {case!r}.

This digest is a PERSISTED CACHE KEY in consumer storage. Changing it is a BREAKING change, not an
additive one — regardless of motive, INCLUDING a correctness fix. See `ruthless.fingerprint`'s
docstring and ADR-002.

If the change is intended:
  1. It takes the MINOR slot under 0.x, never a patch.
  2. The CHANGELOG entry MUST state that it invalidates existing caches.
  3. Only then update this table.

Regenerating this value to make CI green is not a test fix. It silently orphans every consumer cache
keyed on the old digest, and each of them then recomputes from scratch with nothing reporting it.
"""


@pytest.mark.parametrize("case", sorted(_PAYLOADS))
def test_golden_digest_is_unchanged(case: str) -> None:
    assert fingerprint(_PAYLOADS[case]) == _EXPECTED[case], _BREAKING.format(case=case)


@pytest.mark.parametrize("case", sorted(_MODEL_CASES))
def test_golden_model_digest_is_unchanged(case: str) -> None:
    assert _MODEL_CASES[case]() == _EXPECTED_MODELS[case], _BREAKING.format(case=case)


def test_every_case_is_pinned() -> None:
    """A payload added without a pinned digest is an unguarded branch, so it fails here rather than
    passing silently."""
    assert set(_PAYLOADS) == set(_EXPECTED)
    assert set(_MODEL_CASES) == set(_EXPECTED_MODELS)


def test_subclass_order_pairs_are_pinned_on_both_sides() -> None:
    """Spec §3.3. `test_fingerprint.py` asserts these as INEQUALITIES, which a `_tag` reordering can
    satisfy while moving both sides — the relation survives and every consumer digest shifts. This
    asserts over the PINNED table, so it documents that both sides carry a literal; the golden tests
    above are what detect the shift."""
    assert _EXPECTED["enum-intenum-one"] != _EXPECTED["int-positive"]  # IntEnum member IS an int
    assert _EXPECTED["enum-strenum-a"] != _EXPECTED["str-simple"]  # str-enum member IS a str
    assert _EXPECTED["bool-true"] != _EXPECTED["int-positive"]  # isinstance(True, int)
    assert _EXPECTED["datetime-naive"] != _EXPECTED["date-plain"]  # datetime subclasses date


def test_path_flavours_agree_on_the_same_logical_path() -> None:
    """The cross-platform guarantee, stated as an equality over pinned bytes: `_tag` normalises via
    `as_posix()`, so the same LOGICAL path digests identically whichever flavour produced it. The
    Windows CI leg is what proves this holds on both runners."""
    assert _EXPECTED["path-posix-slash"] == _EXPECTED["path-windows-slash"]
    assert _EXPECTED["path-windows-backslash"] == _EXPECTED["path-posix-slash"]
    assert _EXPECTED["path-posix-backslash"] != _EXPECTED["path-posix-slash"]


def test_length_truncates_the_same_digest() -> None:
    """`length` truncates one hexdigest; it does not select a different hash. Pinned against the
    table so a change to either behaviour is caught."""
    assert fingerprint(_PAYLOADS["int-positive"], length=8) == _EXPECTED["int-positive"][:8]
    assert len(fingerprint(_PAYLOADS["int-positive"], length=8)) == 8
