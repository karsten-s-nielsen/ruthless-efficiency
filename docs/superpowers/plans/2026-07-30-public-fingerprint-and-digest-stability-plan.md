# Public `fingerprint` API + digest-stability contract — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote `fingerprint`/`fingerprint_model` to ruthless's public API, and make the digest a
written, test-enforced compatibility contract so a future `_tag` edit cannot silently orphan a
consumer's persisted cache.

**Architecture:** The two functions are re-exported from `ruthless/__init__.py` while their module
stays `_fingerprint.py` (a public module of that name would shadow the re-exported function). A new
golden-digest table pins one payload per `_tag` branch as literals in test source. The stability rule
is written into the `fingerprint` docstring, ADR-002 and CLAUDE.md. `pydantic` is pinned `<3` because
`fingerprint_model` digests `model_dump()` output. A Windows CI leg mirroring `core-lean` closes the
cross-platform axis.

**Tech Stack:** Python 3.10, pydantic v2, pytest, ruff, pyright, import-linter, hatchling, uv.

**Spec:** `docs/superpowers/specs/2026-07-30-public-fingerprint-and-digest-stability-design.md` (rev 3,
two silly-kicks review rounds incorporated). Section references below (§N) point at that spec.

## Global Constraints

- **Target release `0.4.0`.** Minor, not patch — the public API gains two names.
- **ONE commit for the whole branch.** Project convention: never commit docs alone; a single
  branch/commit/PR bundles plan + code + docs after the gate passes. The per-task "Commit" step of the
  usual TDD loop is therefore **deliberately absent** from Tasks 1–7; Task 8 is the only commit.
- **No commit without explicit user approval**, and the commit needs a one-shot
  `!touch ~/.claude-git-approval` from the user first. Push, PR and tag are not gated.
- **No git worktrees** — project convention. Work on a feature branch in this repo.
- **Python floor is 3.10.** `enum.StrEnum` is 3.11+ and MUST NOT be used; use `class X(str, enum.Enum)`.
- **Never write a bare `Path` into the golden table** (§3.2). Use `PurePosixPath`/`PureWindowsPath`
  explicitly. The one exception is a pydantic model field *annotated* `Path`, whose value must be a
  forward-slash literal.
- **No digest literal in any `.md` file.** `tests/test_fingerprint_golden.py` is the single source of
  truth for pinned bytes (§5.1).
- **Local quality gate, all five, before declaring work done:**
  `uv run ruff check ruthless tests` · `uv run ruff format --check ruthless tests` · `uv run pyright` ·
  `uv run lint-imports` · `uv run pytest -v`

## File map

| File | Action | Responsibility |
|---|---|---|
| `ruthless/__init__.py` | Modify | Re-export the two functions; two `__all__` entries |
| `ruthless/_fingerprint.py` | Modify (docstrings only) | Module docstring correction + the stability contract on `fingerprint` |
| `tests/test_public_api.py` | Modify | Two entries in `_EXPECTED_PUBLIC` |
| `tests/test_fingerprint_golden.py` | Create | The golden digest table — the single source of truth for pinned bytes |
| `tests/test_docs_no_digest_literals.py` | Create | Makes the "no digest literal in any `.md`" constraint executable (Task 3A, added during execution) |
| `docs/superpowers/specs/2026-07-29-parallel-error-model-and-cache-identity.md` | Modify | Paraphrase out its two *current*-algorithm digests, so Task 3A's exclusion set needs only the inert rejected-algorithm one |
| `tests/strategies/evolve/test_evolve_strategy.py` | Modify | One assertion pinning `_SEED_CACHE_EXCLUDE` |
| `docs/adr/ADR-002-cache-identity-and-code-provenance.md` | Modify | Record the promotion + the stability contract |
| `CLAUDE.md` | Modify | Cache-identity convention gains the contract line |
| `pyproject.toml` | Modify | `pydantic>=2,<3` |
| `uv.lock` | Modify (automatic) | `uv run` regenerates the `requires-dist` entry for pydantic. Tracked in git — **must be committed alongside `pyproject.toml`**. A lockfile that disagrees with the manifest is the actual bug; do not revert it. |
| `.github/workflows/ci.yml` | Modify | Add the `core-lean-windows` job |
| `ruthless/_version.py` | Modify | `0.3.1` → `0.4.0` |
| `CHANGELOG.md` | Modify | New `[0.4.0]` section |

---

### Task 0: Branch

- [ ] **Step 1: Create the feature branch**

```bash
git checkout -b feat/public-fingerprint-digest-stability
```

- [ ] **Step 2: Confirm a clean baseline**

Run: `git status --porcelain && uv run pytest -q`
Expected: no output from `git status` except the two untracked doc files (spec + this plan), and
pytest reports **224 passed**. Record that number — later tasks add to it.

---

### Task 1: Promote `fingerprint` / `fingerprint_model` to the public API

Implements §1.

**Files:**
- Modify: `tests/test_public_api.py` (the `_EXPECTED_PUBLIC` set)
- Modify: `ruthless/__init__.py`
- Modify: `ruthless/_fingerprint.py` (module docstring only)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `from ruthless import fingerprint, fingerprint_model`. Signatures are **unchanged**:
  `fingerprint(payload: Mapping[str, object], *, length: int = 16) -> str` and
  `fingerprint_model(model: BaseModel, *, exclude: frozenset[str] = frozenset(), length: int = 16) -> str`.
  Task 3 imports both from the top-level package (not from `ruthless._fingerprint`) — that import path
  is itself part of what Task 3 tests.

- [ ] **Step 1: Write the failing test**

In `tests/test_public_api.py`, add two entries to `_EXPECTED_PUBLIC`. Place them in their own
commented group immediately after the `"assert_cache_equivalence"` line inside the
`# reporting + cache-equivalence harness` group, so the set keeps its existing grouped shape:

```python
    # cache identity (public since 0.4.0 — digest stability is a compatibility contract, see ADR-002)
    "fingerprint",
    "fingerprint_model",
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: **FAIL**. `test_all_is_declared_and_complete` fails on the set comparison, and
`test_every_public_name_is_importable_from_the_top_level` fails with
`ruthless.fingerprint is missing from the public API`.

- [ ] **Step 3: Add the re-export**

In `ruthless/__init__.py`, add the import as the **first** line of the import block — immediately
**before** the `_version` line, not after it. The block is sorted alphabetically by module and
`_fingerprint` sorts before `_version` (`f` < `v`):

```python
from ruthless._fingerprint import fingerprint, fingerprint_model
from ruthless._version import __version__ as __version__  # re-export; not in __all__ (dunder)
from ruthless.backend import ComputeBackend, InProcessBackend
```

`I` (isort) is in this repo's ruff `select`, so the wrong order is not cosmetic — it fails
`ruff check` with `I001 Import block is un-sorted or un-formatted` at Step 7, two steps after Steps
4–6 have already reported green. Both orderings were run through this repo's own ruff to confirm.

Then add both names to `__all__`. The list is alphabetically sorted with group comments, so insert
`"fingerprint"` and `"fingerprint_model"` between `"classify_metric"` and `"penalty_metrics"`:

```python
    "classify_metric",
    # cache identity — digest stability is a compatibility contract (ADR-002)
    "fingerprint",
    "fingerprint_model",
    "penalty_metrics",
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: **PASS**, 4 tests.

- [ ] **Step 5: Verify the import-linter contract still holds**

Run: `uv run lint-imports`
Expected: **PASS**, 3 contracts kept. `ruthless._fingerprint` has not moved, so `core-isolation` is
unaffected — this step proves it rather than assuming it.

- [ ] **Step 6: Correct the module docstring**

`ruthless/_fingerprint.py`'s docstring currently asserts the module is "absent from
`ruthless.__all__`", which Step 3 just made false. Replace the whole docstring (lines 1–8) with:

```python
"""Core cache-identity primitive: a deterministic, collision-resistant digest over declared inputs,
plus a model-scoped wrapper whose invalidation scope is a declared EXCLUSION set.

**Public functions, private module.** `fingerprint` and `fingerprint_model` are re-exported from
`ruthless` and listed in `ruthless.__all__` (since 0.4.0), but this module keeps its `_` prefix
deliberately. A public `ruthless/fingerprint.py` would collide with the re-exported FUNCTION name:
`import ruthless.fingerprint` anywhere in the process rebinds that attribute on the package from the
function to the module, so `from ruthless import fingerprint` would yield different objects depending
on unrelated import order. Keeping the module private makes that impossible, and matches
`__init__.py`'s rule that the curated top-level namespace is the supported surface while submodule
paths are implementation detail.

**The digest is a compatibility contract, not an implementation detail** — see `fingerprint` below and
ADR-002. Consumers persist it as a cache key.

Callers: `ruthless.strategies.evolve_.strategy` (seed-result cache identity), plus external consumers
via the public re-export."""
```

- [ ] **Step 7: Run the full gate**

Run: `uv run ruff check ruthless tests && uv run ruff format --check ruthless tests && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: all five pass. Test count unchanged at **224** (the two new names extend an existing set, they
do not add test functions).

---

### Task 2: Write the digest-stability contract

Implements §2. Documentation only — no test, because the contract governs human decisions about
release semantics. Task 3 is what makes it enforceable.

**Files:**
- Modify: `ruthless/_fingerprint.py` (the `fingerprint` docstring)
- Modify: `docs/adr/ADR-002-cache-identity-and-code-provenance.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: Task 1's promotion (the docstring text refers to the functions as public).
- Produces: the canonical wording of the contract. Task 3's failure message and Task 7's CHANGELOG
  entry both point at it; keep the three consistent.

- [ ] **Step 1: Add the contract to `fingerprint`'s docstring**

In `ruthless/_fingerprint.py`, append these two paragraphs to `fingerprint`'s docstring, after the
existing "Three deliberate consequences..." paragraph and before the closing `"""`:

```python
    STABILITY CONTRACT. This digest is a PERSISTED CACHE KEY in consumer storage. Any change that
    alters the digest of a payload that already fingerprinted is BREAKING, not additive - regardless of
    motive, including a correctness fix. It takes the minor slot under 0.x, and its CHANGELOG entry
    must state explicitly that it invalidates existing caches. Extending `_tag` to a new type is
    additive ONLY IF every already-supported payload digests identically, which is what
    `tests/test_fingerprint_golden.py` proves.

    The guarantee is over the LOGICAL VALUE, not over how the caller constructed it. `Path(str)` in
    particular parses per-platform - a backslash is a separator on Windows and an ordinary character on
    POSIX - so a caller spanning platforms must pass `PurePosixPath` or normalise before fingerprinting.
    Constructing the value is the caller's responsibility; digesting it identically everywhere is ours.
```

- [ ] **Step 2: Record the promotion and the contract in ADR-002**

In `docs/adr/ADR-002-cache-identity-and-code-provenance.md`, the paragraph ending
`"Promotion to a public module stays purely additive."` (around line 39–40) is now outdated. Replace
that trailing sentence with:

```markdown
Promotion happened in 0.4.0: `fingerprint` and `fingerprint_model` are re-exported from `ruthless` and
listed in `__all__`, on the trigger this project wrote down — a second real caller. The **module**
stays `_`-prefixed, because a public `ruthless/fingerprint.py` would shadow the re-exported function
name (`import ruthless.fingerprint` rebinds the package attribute from the function to the module).

**Digest stability is now a compatibility contract.** The digest is a persisted cache key in consumer
storage, so any change altering an existing payload's digest is breaking, not additive — regardless of
motive, including a correctness fix. It takes the minor slot under `0.x` and its CHANGELOG entry must
say it invalidates existing caches. There is no carve-out: a carve-out is the loophole every future
digest change would be argued into, and it buys the consumer nothing, since an orphaned cache is
equally silent whether the digest moved for a good reason or a careless one. The enforcement is
`tests/test_fingerprint_golden.py`, and the point of pinning bytes rather than relations is to
manufacture a reviewable moment: changing a digest means editing that table.

The guarantee is over the logical value. `Path(str)` parses per-platform, so construction is the
caller's responsibility; digesting identically everywhere is ours. `pydantic` is pinned `<3` because
`fingerprint_model` digests `model_dump()` output, which places pydantic's serialisation inside the
digest's blast radius — the same reasoning that already pins `numpy<3` for the determinism gate.
```

- [ ] **Step 3: Add the contract line to CLAUDE.md**

In `CLAUDE.md`, find the `**Cache identity is a declared EXCLUSION set, never an inclusion list.**`
bullet under "Key conventions". Append to the end of that bullet:

```markdown
  **Digest bytes are a compatibility contract.** `fingerprint`/`fingerprint_model` are public since
  0.4.0 and consumers persist the digest as a cache key, so any change altering an already-supported
  payload's digest is BREAKING (minor slot, CHANGELOG must say it invalidates caches) — including a
  correctness fix. `tests/test_fingerprint_golden.py` pins one payload per `_tag` branch as literals;
  it is the single source of truth for pinned bytes, and no `.md` file may quote a digest. The
  guarantee is over the logical VALUE — `Path(str)` parses per-platform, so construction is the
  caller's problem. `pydantic` is pinned `<3` because `fingerprint_model` digests `model_dump()`.
```

- [ ] **Step 4: Verify formatting**

Run: `uv run ruff check ruthless tests && uv run ruff format --check ruthless tests`
Expected: **PASS**. (Docstring edits can trip line-length; ruff's limit for this repo is configured in
`pyproject.toml` — wrap to fit rather than adding a `noqa`.)

---

### Task 3: The golden digest corpus

Implements §3, §3.2, §3.3, §3.4, §3.5.

**Files:**
- Create: `tests/test_fingerprint_golden.py`
- Modify: `tests/strategies/evolve/test_evolve_strategy.py`

**Interfaces:**
- Consumes: `from ruthless import fingerprint, fingerprint_model` (Task 1).
- Produces: `_PAYLOADS`, `_EXPECTED`, `_MODEL_CASES`, `_EXPECTED_MODELS` at module level in
  `tests/test_fingerprint_golden.py`. Task 4 imports `_PAYLOADS` and `_MODEL_CASES` by file path to
  re-verify them against published wheels.

**On generating the pinned values.** The digests cannot be written by hand, and they are not
placeholders: they are the *current shipped implementation's output*, and the table's purpose is
future regression, not present correctness. The legitimate process is therefore generate → pin →
**independently verify against the published wheel** (Task 4). Step 4 below generates from the same
`_PAYLOADS` object the test consumes, so the generator and the test cannot drift.

- [ ] **Step 1: Create the test file with payloads and an empty expectation table**

Create `tests/test_fingerprint_golden.py`:

```python
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

# Filled by Step 4. Do NOT hand-edit to make a test pass — see the module docstring.
_EXPECTED: dict[str, str] = {}
_EXPECTED_MODELS: dict[str, str] = {}
```

- [ ] **Step 2: Append the tests to the same file**

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_fingerprint_golden.py -q`
Expected: **FAIL** — every golden case raises `KeyError` on the empty `_EXPECTED`/`_EXPECTED_MODELS`,
and `test_every_case_is_pinned` fails on the set comparison. This confirms the harness is wired to the
tables before any value exists.

- [ ] **Step 4: Generate the pinned values**

Write this generator to the scratchpad (it loads the test module **by path**, so it does not depend on
`tests/` being an importable package):

```python
# scratchpad/gen_golden.py
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("_golden", Path("tests/test_fingerprint_golden.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["_golden"] = mod
spec.loader.exec_module(mod)

from ruthless import fingerprint  # noqa: E402

print("_EXPECTED: dict[str, str] = {")
for name, payload in mod._PAYLOADS.items():
    print(f"    {name!r}: {fingerprint(payload)!r},")
print("}")
print()
print("_EXPECTED_MODELS: dict[str, str] = {")
for name, make in mod._MODEL_CASES.items():
    print(f"    {name!r}: {make()!r},")
print("}")
```

Run: `uv run python scratchpad/gen_golden.py`
Expected: two complete dict literals covering all 40 payload cases and all 4 model cases.

- [ ] **Step 5: Paste the generated tables into the test file**

Replace the two empty dicts from Step 1 with the generator's output verbatim. Keep the
`# Filled by Step 4. Do NOT hand-edit...` comment above them.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_fingerprint_golden.py -v`
Expected: **PASS**, 48 tests (40 parametrized payload cases + 4 parametrized model cases + 4 named
tests).

- [ ] **Step 7: Prove the failure message actually fires**

Temporarily corrupt one value (change the last hex character of `_EXPECTED["int-positive"]`), then run:
`uv run pytest tests/test_fingerprint_golden.py -k int-positive`
Expected: **FAIL**, and the output contains "BREAKING change" and "invalidates existing caches".
**Revert the corruption** and re-run to confirm PASS. A failure message nobody has seen is a failure
message nobody has tested.

- [ ] **Step 8: Pin `_SEED_CACHE_EXCLUDE` in the evolve suite**

The golden table reproduces evolve's seed-cache payload by *restating* its exclusion set. If evolve's
set changes, the golden case would keep passing while no longer representing production. Add to
`tests/strategies/evolve/test_evolve_strategy.py`:

```python
def test_seed_cache_exclude_matches_the_golden_table():
    """`tests/test_fingerprint_golden.py`'s "evolve-seed-cache" case restates this exclusion set so it
    can pin the real payload without importing the strategy package (which would need the [evolve]
    extra and would drop the case from the lean Windows CI leg). Restating means the two can drift, so
    this pins them together."""
    from ruthless.strategies.evolve_.strategy import _SEED_CACHE_EXCLUDE

    assert _SEED_CACHE_EXCLUDE == frozenset({"timeout_seconds"})
```

- [ ] **Step 9: Run the full gate**

Run: `uv run ruff check ruthless tests && uv run ruff format --check ruthless tests && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: all five pass. Test count **224 + 48 + 1 = 273** at this point; Task 3A adds the last 9,
taking the suite to **282**.

---

### Task 3A: Enforce "no digest literal in any `.md`" as a test

> **Added during execution** (self-review defect 10). The rule is a Global Constraint of this plan and a
> sentence in `CLAUDE.md`, and no task made it executable. A rule enforced only by whoever happens to be
> editing is the same failure mode that let 0.3.1 ship an unverified "purely additive" claim — so it is
> pinned, not asserted, exactly like everything else in this release.

**Files:**
- Create: `tests/test_docs_no_digest_literals.py`

**Interfaces:**
- Consumes: nothing from `ruthless`. Standard library plus pytest only, so it runs in the lean
  `core-lean` / `core-lean-windows` legs. It is a repository-hygiene test: it needs the source tree,
  not an installed package.
- Produces: no code surface.

- [ ] **Step 1: Write the guard**

Walk every `.md` under the repo root (pruned by a `_SKIP_DIRS` frozenset) and fail on any digest-shaped
literal not in a declared exclusion set. Resolve the repo root from `__file__`, never `os.getcwd()`, so
the answer does not depend on where pytest was invoked.

**The regex is the whole design, and the naive form is wrong.** `\b[0-9a-f]{16}\b` false-positives
twice on `README.md`'s own quick-start output line — once on the 16-digit mantissa of the `x` value, and
once on the 15 digits plus the `e` of the `loss` value's exponent form. `\b` does not help, because `.`
is a non-word character, so a digit run after a decimal point *starts* on a word boundary. A guard that
flags the README's own example is a guard the next person deletes. Use lookarounds instead:

```python
_DIGEST_RE = re.compile(r"(?<![\w.])[0-9a-f]{16}(?![\w.])")
```

A hex run preceded or followed by a word character **or a dot** is part of a longer token — a number, an
identifier, a filename — and is not a digest. Pin both README strings as regression cases so a future
"simplification" back to `\b` fails loudly.

Keep the two offending substrings in the **test file's** docstring, never in a `.md`. Quoted whole, each
float is safe (the leading `.` suppresses the match); quoted as the bare fragment the naive regex would
have matched, each is digest-shaped and this guard flags it. That is the guard working, not a bug — but
it means the guard cannot be explained in Markdown using its own counter-examples verbatim.

- [ ] **Step 2: Declare the exclusion set, fail-closed**

Key it on `(repo-relative POSIX path, digest value)` so adding a *new* literal to an already-listed file
still fails. Same shape and same discipline as `fingerprint_model(exclude=...)` and
`_SEED_CACHE_EXCLUDE`: every entry carries the reason it is safe, and a test asserts each entry is still
present so a stale exclusion fails rather than sitting there exempting nothing.

Exactly **one** entry is justified: the digest in `docs/superpowers/specs/2026-07-29-...md` §0.3/§2.3.1
that is a **rejected-algorithm** value — the measured rev-1 collision the fix exists to close. No shipped
`_tag` can produce it, and lifting it into the golden table would fail that table's own assertion
immediately. That inertness is the entire basis of the exemption. The same spec's two *current*-algorithm
digests are exactly the liftable kind this guard exists to stop; **paraphrase those out of the spec**
("the two digests differ") rather than exempting them — its argument survives intact without them.

- [ ] **Step 3: State the gaps in the docstring**

The guard recognises the default 16-char digest, so `length != 16`, a digest terminated by a sentence
period, and anything under `_SKIP_DIRS` fall outside it. Say so — a guard that reads as total coverage
is worse than one whose limits are written down.

- [ ] **Step 4: Gate the staleness check on being in a source checkout**

The sdist ships `tests/` but **excludes `/docs/superpowers` and `/CLAUDE.md`** (see
`[tool.hatch.build.targets.sdist]`), and every exclusion entry lives under that dropped tree. So in an
unpacked sdist `test_every_exclusion_is_still_present` fails on a *packaging* decision, not a stale
entry — a red suite inside a published artifact, which downstream packagers do run at build time. Skip
that one test when `_REPO_ROOT / "CLAUDE.md"` is absent; `CLAUDE.md` is on the same `exclude` list, so
"absent" means precisely "not a source checkout". Leave the scan and the regex tests running — both are
meaningful anywhere.

Verify **both** directions, because a skip that fires in the repo would silently retire the check:

```bash
uv run pytest tests/test_docs_no_digest_literals.py -v          # 9 passed, 0 skipped
uv build --sdist && tar xzf dist/*.tar.gz -C <tmp> && (cd <tmp>/ruthless_efficiency-0.4.0 && pytest -q ...)
```

Expected: **9 passed / 0 skipped** in the checkout; the sdist's lean run goes from `1 failed, 181
passed` to green with one skip.

- [ ] **Step 5: Run it**

Run: `uv run pytest -q tests/test_docs_no_digest_literals.py`
Expected: **9 passed** (1 scan + 3 README-float regression pins + 4 genuine-digest pins + 1 per
exclusion entry). Then re-run the whole gate; the suite is now **282**.

Any `.md` edit in a later task must re-run this file — it is possible to trip your own guard. It
happened during `/final-review`: prose explaining the regex quoted the README float's bare mantissa,
which in isolation is digest-shaped.

---

### Task 4: Verify the pinned bytes against the published wheels

Implements §7. This is what makes Task 3's generate-then-pin legitimate: it proves the literals match
what consumers actually installed, not merely what this working tree emits.

**Files:** none modified. Scratchpad only; the output goes in the PR body.

**Interfaces:**
- Consumes: `_PAYLOADS` and `_MODEL_CASES` from `tests/test_fingerprint_golden.py`, plus the pinned
  `_EXPECTED`/`_EXPECTED_MODELS` filled in Task 3.
- Produces: a pass/fail report for the PR. No code artifact.

- [ ] **Step 1: Write the cross-version verifier**

**Why the shim below is necessary, and why it is honest.** The golden test module does
`from ruthless import fingerprint, fingerprint_model` — the public path, which is the point of Task 1.
But that path does **not exist** in published 0.3.0 or 0.3.1, so loading the module against those
wheels would die with `ImportError` before a single digest was compared. The shim binds the two names
onto the `ruthless` package from `ruthless._fingerprint`, where they lived in 0.3.x. This verifies the
*algorithm's bytes* across versions, which is the claim being checked; it does not pretend the public
API existed then, and `tests/test_public_api.py` is what covers the surface.

```python
# scratchpad/verify_published.py
import importlib.util
import sys
from pathlib import Path

import ruthless
from ruthless import _fingerprint as _fp
from ruthless import __version__

# Published 0.3.x kept these private. Bind them so the golden module's public-path import resolves.
for _name in ("fingerprint", "fingerprint_model"):
    if not hasattr(ruthless, _name):
        setattr(ruthless, _name, getattr(_fp, _name))

spec = importlib.util.spec_from_file_location("_golden", Path("tests/test_fingerprint_golden.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["_golden"] = mod
spec.loader.exec_module(mod)

# NO SKIP LIST, deliberately. An earlier draft filtered out the payload prefixes believed to have
# raised under 0.3.0; that filter was derived from the belief under test and would have hidden the
# only two real mismatches. A raise is an OUTCOME to classify, never a reason to exclude a case.
raised, identical, differs = [], [], []

for name, payload in mod._PAYLOADS.items():
    try:
        got = _fp.fingerprint(payload)
    except Exception as exc:
        raised.append((name, type(exc).__name__))
        continue
    (identical if got == mod._EXPECTED[name] else differs).append((name, got, mod._EXPECTED[name]))

for name, make in mod._MODEL_CASES.items():
    try:
        got = make()
    except Exception as exc:
        raised.append((name, type(exc).__name__))
        continue
    (identical if got == mod._EXPECTED_MODELS[name] else differs).append(
        (name, got, mod._EXPECTED_MODELS[name])
    )

total = len(mod._PAYLOADS) + len(mod._MODEL_CASES)
print(f"=== ruthless=={__version__} vs the 0.4.0 golden table: {total} cases ===")
print(f"RAISED     : {len(raised)}   {sorted(n for n, _ in raised)}")
print(f"NON-RAISING: {len(identical) + len(differs)}")
print(f"  IDENTICAL: {len(identical)}")
print(f"  DIFFERS  : {len(differs)}   {sorted(n for n, _, _ in differs)}")
for name, got, pinned in differs:
    print(f"    DIFFERS {name}: pinned={pinned} published={got}")
```

- [ ] **Step 2: Verify against published 0.3.1**

Run: `uv run --isolated --no-project --with "ruthless-efficiency==0.3.1" --with pytest python scratchpad/verify_published.py`
Expected: **44 cases, 0 raised, 44 identical, 0 differ.**

(`--with pytest` is required: the golden module imports `pytest` at module scope for
`@pytest.mark.parametrize`, and the ephemeral env would otherwise have only ruthless's runtime deps.)

This is the load-bearing check: **the pinned literals are the bytes on PyPI.** If it reports a
mismatch, STOP — either the working tree diverges from the release, or a payload is non-deterministic.
Do not adjust the table to match; diagnose first.

- [ ] **Step 3: Verify against published 0.3.0 — the WHOLE table, no skip list**

> **CORRECTED AFTER EXECUTION. Do not reinstate the skip list.** This step originally reused the
> `POST_030` prefix filter from Step 1 and pinned `ruthless==0.3.0: checked=27 skipped=17 mismatches=0`.
> Both the method and the expected numbers were wrong, and the way they were wrong is the finding: the
> skip list was derived from the belief under test, so it could not falsify it. See the note after the
> counts below. Delete `POST_030` and the `only_030_safe` branch from the Step 1 script rather than
> reasoning about which prefixes are safe.

Recompute **every** case under 0.3.0 and classify each as *raised* / *identical* / *differs* — a
`TypeError` is data, not a reason to exclude the case:

```python
raised, identical, differs = [], [], []
for name, payload in mod._PAYLOADS.items():
    try:
        got = _fp.fingerprint(payload)
    except Exception as exc:
        raised.append((name, type(exc).__name__))
        continue
    (identical if got == mod._EXPECTED[name] else differs).append(name)
# ...same for mod._MODEL_CASES via _EXPECTED_MODELS...
```

Run: `uv run --isolated --no-project --with "ruthless-efficiency==0.3.0" --with pytest python scratchpad/verify_published.py`

Expected, exactly — **44 cases, 12 raised, 32 digested, 30 identical, 2 differ**, the two being
`enum-intenum-one` and `enum-strenum-a`.

**Check every number, not just the mismatch count.** A mismatch count of zero is vacuously true if
everything was skipped or excluded — the same non-vacuity trap Step 7 of Task 3 and Step 1 of Task 6
each guard against. Here the trap already sprang once, which is why the skip list is gone.

**Why the original premise was false, and why it matters.** 0.3.0 had no `enum` branch *at all*, so only
*plain* `Enum` raised. An `IntEnum` member fell through to the `int` branch and a `str`-subclassing
`Enum` member to the `str` branch: both digested successfully, and identically to the bare `int`/`str`
value they wrap — the exact subclass-shadowing collision the golden table now pins on both sides. 0.3.1's
new `enum` branch moved both. A skip list matching the prefix `enum-` skips precisely those two cases and
reports a clean run.

So **0.3.1 was not purely additive**: two payload shapes were cache-invalidating in a release published
as a patch. Task 8's `[0.4.0]` entry states this, and adds a correction block to the `[0.3.1]` entry. Do
not soften either — the claim was made in good faith and was still wrong, which is the argument for the
no-carve-out rule.

- [ ] **Step 4: Record the result**

Copy both command outputs into a scratchpad note for the PR body. Task 8 pastes them in.

---

### Task 5: Pin `pydantic<3`

Implements §4.

**Files:**
- Modify: `pyproject.toml` (the `dependencies` line)

**Interfaces:**
- Consumes: Task 3's `model-rich-path-enum-date` and `evolve-seed-cache` cases, which are what would
  detect a pydantic-induced digest shift.
- Produces: no code surface. Task 8's CHANGELOG entry mentions the pin.

- [ ] **Step 1: Apply the pin**

In `pyproject.toml`, replace the `dependencies` line and extend the comment above it. The existing
comment explains the `numpy` pin; the new sentence explains pydantic's on the same footing:

```toml
# numpy pinned <3 so the RandomSearch RNG stream stays stable for the determinism gate (review H-D).
# pydantic pinned <3 for the same class of reason: `fingerprint_model` digests `model_dump()` output,
# so pydantic's python-mode serialisation of Path/Enum sits INSIDE the digest's blast radius. An
# unpinned major could move every consumer's persisted cache key with nothing in ruthless changing.
dependencies = ["pydantic>=2,<3", "numpy>=1.24,<3", "pyyaml>=6"]
```

- [ ] **Step 2: Verify the environment still resolves and the pin is live**

Run: `uv run python -c "import pydantic; print(pydantic.VERSION)"`
Expected: a `2.x` version prints.

Run: `uv pip install -e ".[dev]" --dry-run`
Expected: resolves without conflict.

- [ ] **Step 3: Run the full gate**

Run: `uv run ruff check ruthless tests && uv run ruff format --check ruthless tests && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: all five pass, **282** tests.

---

### Task 6: Add the Windows CI leg

Implements §5.2.

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: Task 3's golden test, which must be importable under the `[dev]` extra alone. It is —
  `EvalConfig` is core config, not the evolve strategy package (§3.4).
- Produces: a third CI job named `core-lean-windows`.

- [ ] **Step 1: Prove the leg would pass, locally, before writing it**

This box IS Windows, so `core-lean`'s exact pytest invocation can be run here first:

```bash
uv run pytest -q --ignore=tests/backends --ignore=tests/strategies/evolve --ignore=tests/e2e/test_evolve_orchestration_gate.py --ignore=tests/strategies/optuna_ --ignore=tests/e2e/test_optuna_resume_gate.py
```

Expected: **PASS**, and the golden tests are among those collected (confirm with
`... --collect-only -q | grep fingerprint_golden`). If the golden file were excluded by that ignore
list, the whole Windows leg would be theatre — check rather than assume.

- [ ] **Step 2: Add the job**

Append to `.github/workflows/ci.yml`, after the `core-lean` job. Action SHAs are copied from the
existing jobs verbatim — do not bump them here, that is a separate concern:

```yaml
  core-lean-windows:
    # The cross-platform leg for cache identity. `fingerprint` digests are PERSISTED CACHE KEYS in
    # consumer storage, and consumers span Windows and Linux, so a platform-dependent digest would
    # orphan their caches silently. A Linux-only CI can never observe that. Mirrors `core-lean`
    # (lean [dev] install, core test subset) rather than matrixing the full `test` job: matrixing
    # would install openevolve/docker/huggingface_hub on Windows and turn any fingerprint change into
    # a third-party Windows-compatibility exercise.
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0
      - run: uv python install 3.10
      - run: uv venv --python 3.10
      - run: uv pip install -e ".[dev]"
      - run: uv run pytest -v --ignore=tests/backends --ignore=tests/strategies/evolve --ignore=tests/e2e/test_evolve_orchestration_gate.py --ignore=tests/strategies/optuna_ --ignore=tests/e2e/test_optuna_resume_gate.py
```

- [ ] **Step 3: Validate the YAML parses**

Run: `uv run python -c "import yaml,pathlib; d=yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text()); print(sorted(d['jobs']))"`
Expected: `['core-lean', 'core-lean-windows', 'test']`

---

### Task 7: Release mechanics for 0.4.0

Implements §6.

**Files:**
- Modify: `ruthless/_version.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: every preceding task (the CHANGELOG describes all of them).
- Produces: `__version__ == "0.4.0"`.

- [ ] **Step 1: Bump the single version line**

In `ruthless/_version.py`, change the last line:

```python
__version__ = "0.4.0"
```

That is the entire source change for the release — `pyproject.toml` reads it via
`[tool.hatch.version] path`, and `__init__.py` re-exports it.

- [ ] **Step 2: Add the CHANGELOG section**

Insert directly below the `# Changelog` preamble, above `## [0.3.1]`:

```markdown
## [0.4.0] - 2026-07-30

Minor rather than patch: the public API gains two names. **This release does not invalidate existing
caches** — the digest algorithm is untouched, and every previously-supported payload digests
identically (now enforced by a golden table rather than a one-off check).

### Added
- `fingerprint` and `fingerprint_model` are now part of the public API (`from ruthless import
  fingerprint`). They were private through 0.3.x pending a second real caller; that trigger has fired.
  Signatures are unchanged. The **module** stays `ruthless/_fingerprint.py`: a public
  `ruthless/fingerprint.py` would shadow the re-exported function, because `import ruthless.fingerprint`
  rebinds that attribute on the package from the function to the module.
- **Digest stability is now a stated compatibility contract.** The digest is a persisted cache key in
  consumer storage, so any change altering an already-supported payload's digest is **breaking, not
  additive** — regardless of motive, including a correctness fix. It takes the minor slot under `0.x`
  and its entry here must say it invalidates existing caches. There is no carve-out. Stated on
  `fingerprint`, in ADR-002 and in CLAUDE.md.
- `tests/test_fingerprint_golden.py` pins one payload per `_tag` branch as literals in test source —
  the enforcement behind the contract above, and the single source of truth for pinned bytes. The
  existing suite was entirely relational (`a != b`), which catches a collision but not a *shift*: a
  `_tag` change can move every digest while leaving every relation intact. The four subclass-order
  traps (`IntEnum`/`int`, str-enum/`str`, `bool`/`int`, `datetime`/`date`) are pinned on **both** sides
  for exactly that reason. (Four pairs, from three `_tag` branch-order rules — the enum rule covers
  both `IntEnum`-vs-`int` and str-enum-vs-`str`. Do not "correct" four to three.) Verified against the
  published 0.3.1 wheel: **44 of 44 cases match**, so this release moves no digest. Running the same
  table against published **0.3.0** — all 44 cases, no skip list — established that **0.3.1 was not
  purely additive**: 12 cases raised, 32 digested, of which 30 byte-identical and **2 differ**
  (`IntEnum`, str-`Enum`). Record that, and add a correction block to the `[0.3.1]` entry.

  > **Report all four numbers (44 / 12 / 30 / 2), and do not reintroduce a skip list.** The earlier
  > draft of Task 4 filtered the payloads believed to have raised under 0.3.0 and expected a clean
  > `checked=27 skipped=17 mismatches=0`; the filter matched the prefix `enum-` and so removed exactly
  > the two cases that carry the finding. See Task 4 Step 3.

### Changed
- `pydantic` is pinned `<3`. `fingerprint_model` digests `model_dump()` output, so pydantic's
  python-mode serialisation of `Path`/`Enum` sits inside the digest's blast radius: an unpinned major
  could move every consumer's persisted cache key with nothing in ruthless changing. Same class of
  guarantee as the existing `numpy<3` pin for the determinism gate.
- CI gains a `core-lean-windows` job. Consumers of the digest span Windows and Linux while ruthless's
  CI was Linux-only, so a platform-dependent digest could not be observed here. The digest guarantee is
  over the **logical value** — `Path(str)` parses per-platform, so constructing the value stays the
  caller's responsibility, now stated in `fingerprint`'s docstring.
```

- [ ] **Step 3: Verify version consistency**

Run: `uv run python -c "import ruthless; print(ruthless.__version__)"`
Expected: `0.4.0`

Run: `uv run python -c "import importlib.metadata as m; print(m.version('ruthless-efficiency'))"`
Expected: `0.4.0` — but see below, because **either answer can be correct here** and you must record
which you got rather than treating one as failure.

`importlib.metadata.version()` reads dist metadata written at **install** time, so an editable install
keeps reporting the version the code had when it was installed.

The precise rule, established by observing BOTH cases during this cycle: `uv run` auto-rebuilds the
editable install when **uv's own inputs** change — a `pyproject.toml` edit triggers it, which is why
Task 5's dependency pin appeared in `importlib.metadata.requires()` with no manual reinstall. An edit
to `ruthless/_version.py` is an ordinary source change under an editable install and is **invisible to
uv**, so it does NOT trigger a rebuild. Expect `0.3.1` here.

Run `uv pip install -e ".[dev,backends,evolve,optuna]"`, then check again — it must now report
`0.4.0`. The reinstall log showing `- 0.3.1 / + 0.4.0` is direct proof that hatchling's
`dynamic = ["version"]` wiring still reads `_version.py`, which is the mechanism making that file the
single source of truth for both the runtime and the built wheel. Record which case occurred.

Worth doing rather than skipping: `ruthless.__version__` is read from source and moves the instant you
edit `_version.py`; `importlib.metadata` reads recorded metadata. Confirming they agree is what proves
the hatchling `dynamic = ["version"]` wiring still works — the mechanism that makes `_version.py` the
single source of truth for both the runtime and the built wheel.

---

### Task 8: Final review, commit, PR, release

**Files:** none beyond what previous tasks changed.

- [ ] **Step 1: Run the full gate one last time**

Run: `uv run ruff check ruthless tests && uv run ruff format --check ruthless tests && uv run pyright && uv run lint-imports && uv run pytest -v`
Expected: all five pass, **282** tests.

- [ ] **Step 2: Run `/final-review`**

The mandatory pre-commit quality gate for every work cycle. It also regenerates the C4 diagram at
`docs/c4/architecture.html`. Surface every issue it raises; fix rather than downgrade.

- [ ] **Step 3: Ask for the commit approval gate**

Commits require a one-shot approval. Ask the user to run:

```
!touch ~/.claude-git-approval
```

Do not proceed to Step 4 until they confirm.

- [ ] **Step 4: Commit — one commit for the whole branch**

```bash
git add -A
git commit -F- <<'EOF'
feat(fingerprint)!: public fingerprint API + digest-stability contract (release 0.4.0)

Promote `fingerprint`/`fingerprint_model` to the public API on the trigger this
project wrote down — a second real caller. Signatures unchanged; the module stays
`_fingerprint.py` because a public `ruthless/fingerprint.py` would shadow the
re-exported function name.

Make digest stability a stated, enforced compatibility contract. The digest is a
persisted cache key in consumer storage, so a shift orphans consumer caches
silently and triggers a full recompute with nothing reporting it. The existing
suite was entirely relational, which catches a collision but not a shift.

- Golden table pinning one payload per `_tag` branch as literals in test source,
  including both sides of all three subclass-order traps. Verified against the
  published 0.3.1 wheel, and the 0.3.0-supported subset against published 0.3.0.
- Contract stated on `fingerprint`, in ADR-002 and CLAUDE.md: any change altering
  an already-supported payload's digest is breaking, not additive — including a
  correctness fix. No carve-out.
- Pin `pydantic<3`: `fingerprint_model` digests `model_dump()` output, so
  pydantic's serialisation of Path/Enum is inside the digest's blast radius.
- Add a `core-lean-windows` CI job. Consumers span two platforms; CI spanned one.

This release does not invalidate existing caches.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSMU6x3y9fALYqtZeY897v
EOF
```

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin feat/public-fingerprint-digest-stability
```

Open the PR with `gh pr create`. The body must include Task 4's two verification outputs verbatim, and
end with:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01PSMU6x3y9fALYqtZeY897v
```

- [ ] **Step 6: Wait for CI, including the new Windows leg**

Run: `gh pr checks --watch`
Expected: `test`, `core-lean` and `core-lean-windows` all green. Note that `gh pr checks --watch` can
exit 0 *before* checks register — re-run it once after a few seconds and confirm all three jobs are
actually listed, rather than trusting the first exit code.

- [ ] **Step 7: Merge, tag, publish**

Squash-merge (project convention), then:

```bash
git checkout main && git pull
git tag v0.4.0 && git push origin v0.4.0
```

The `v*` tag triggers `publish.yml` (OIDC).

- [ ] **Step 8: Verify the published release**

Run: `uv run --isolated --no-project --with "ruthless-efficiency==0.4.0" python -c "from ruthless import fingerprint, fingerprint_model; import ruthless; print(ruthless.__version__)"`
Expected: `0.4.0`, and both imports succeed from the published wheel — the actual thing silly-kicks is
blocked on.

PyPI's JSON API is CDN-cached and lags a publish, so if this 404s, wait and retry rather than assuming
the publish failed. Confirm in the Actions tab that `publish.yml` succeeded.

- [ ] **Step 9: Report back to silly-kicks**

State: both asks are shipped in 0.4.0; the signature is `fingerprint(payload: Mapping[str, object], *,
length=16)` as they expected; **`pydantic` is now pinned `<3`**, which constrains their resolution too;
and the digest guarantee is over the logical value, so `Path(str)` construction remains their side's
responsibility — which they had already committed to normalising.

---

## Self-review

**Spec coverage.** §1 → Task 1. §2 → Task 2. §3/§3.2/§3.3/§3.5 → Task 3 Steps 1–7. §3.4 → Task 3
Steps 1 and 8. §4 → Task 5. §5.2 → Task 6 (both remedies: the CI leg here, the contract sentence in
Task 2 Step 1). §6 → Task 7. §7 → Task 4. §8's non-goals are respected: no version constant, no
signature change, no other private module promoted, no consumer-side work.

**Placeholders.** None. The golden digests are the one thing not literally written in this plan, and
that is deliberate and stated: they are generated from the shipped implementation (Task 3 Step 4) and
then independently verified against the published wheel (Task 4), because hand-writing a sha256 prefix
is not possible and copying one into a `.md` would violate the spec's single-source-of-truth rule.

**Type consistency.** `_PAYLOADS`/`_EXPECTED`/`_MODEL_CASES`/`_EXPECTED_MODELS` are named identically
in Task 3 (definition), Task 3's tests, and Task 4's verifier. `_SEED_CACHE_EXCLUDE` matches the symbol
in `ruthless/strategies/evolve_/strategy.py`. Job name `core-lean-windows` matches between Task 6's
YAML and Task 8 Step 6. Test count 224 → 273 (Task 3) → **282** (Task 3A) is consistent across Tasks 3,
3A, 5 and 8.

**Four defects this self-review caught, recorded so the same traps are not re-introduced:**

1. **Task 4's verifier could not have run at all.** The golden module imports
   `from ruthless import fingerprint, fingerprint_model` — a path that does not exist in published
   0.3.0 or 0.3.1 — so loading it against those wheels would have raised `ImportError` before
   comparing a single digest. Fixed with an explicit, documented shim.
2. **`--with pytest` was missing** from both published-wheel commands. The golden module imports
   `pytest` at module scope, and an ephemeral `--no-project` env carries only ruthless's runtime deps.
3. **`# noqa: DTZ001` would have failed the lint gate.** `DTZ` is not in this repo's ruff `select`, but
   `RUF` is — and `RUF100` flags unused `noqa`. The existing `test_fingerprint.py` writes its naive
   datetime with a plain comment; this plan now matches.
4. **Test counts were wrong** (49/274 rather than 48/273) — the named-test count was miscounted. The
   224 baseline was confirmed by `pytest --collect-only`, not from memory.

All four are the same class of error: a plausible-looking instruction that had never been executed.
The plan's own verification steps (Task 3 Step 7's deliberate corruption, Task 6 Step 1's local
Windows dry-run) exist for the same reason.

**Four more from the silly-kicks plan review, all fixed above:**

5. **Task 1 Step 3 named the wrong import position** — "after the `_version` line", when `_fingerprint`
   sorts *before* `_version` (`f` < `v`). `I` is in this repo's ruff `select`, so following the
   instruction literally failed `ruff check` with `I001` at Step 7, two steps after Steps 4–6 reported
   green. Both orderings were then run through this repo's ruff via `--stdin-filename`: the plan's
   order errored, the corrected order passed. This landed in Task 1 — the one task with no
   execute-it-first step of its own.
6. **Task 4's verifier under-counted `skipped`** by 4: the model cases were skipped wholesale without
   touching the counter, in a script whose entire purpose is accounting for what was and was not
   checked.
7. **Task 4 Step 3 had no expected counts**, so `mismatches=0` could pass vacuously — a `POST_030` typo
   that skipped everything would have read as success. Pinning `checked=27 skipped=17` fixed the
   vacuity but **not the underlying defect** — see 9 below, which retired the skip list entirely.
8. **Task 7 Step 3's parenthetical was optimistic.** `importlib.metadata.version()` reads install-time
   metadata, so an editable install reports the old version until reinstall. The step now expects
   `0.3.1` first and explains why the two version mechanisms disagree.

**Two more found during execution — the class of defect no review round caught:**

9. **Task 4's skip list was derived from the belief it was testing.** `POST_030` excluded every payload
   whose type was *believed* to raise under 0.3.0, including the prefix `enum-`. But 0.3.0 had no `enum`
   branch at all, so only *plain* `Enum` raised: `IntEnum` and str-`Enum` members fell through to the
   `int`/`str` branches, digested successfully, and digested *identically to the bare value they wrap*.
   The filter removed exactly the two cases proving 0.3.1 was **not** purely additive. Defects 6 and 7
   both refined the accounting of a skip list that should not have existed. The fix is structural: run
   the whole corpus, classify each case as raised/identical/differs, and treat a raise as data.
   **Generalisable: a verification that excludes cases on the strength of the hypothesis under test
   cannot falsify that hypothesis.**
10. **The plan omitted a file that ships in its own commit.** `tests/test_docs_no_digest_literals.py`
    (9 tests) was written during execution to enforce the "no digest in any `.md`" rule that the plan
    states only as a Global Constraint. A constraint enforced solely by whoever is editing is the same
    failure mode as 0.3.1's unverified "purely additive" claim, so it became a test — but no task
    introduces it, and the plan's arithmetic never counted it. Corrected in Task 3A below.
