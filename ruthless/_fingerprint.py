"""Private core cache-identity primitive: a deterministic, collision-resistant digest over declared
inputs, plus a model-scoped wrapper whose invalidation scope is a declared EXCLUSION set.

Private (`_`-prefixed, absent from `ruthless.__all__`) for the same reason as `_logging` and `_io`: it is
shared across the core and the strategies without committing a `1.0` public surface. Promotion to a
public `fingerprint` module stays purely additive if a second real caller appears.

Existing callers: `strategies/evolve_/strategy.py` (seed-result cache identity)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from pydantic import BaseModel


def _tag(value: object) -> object:
    """Type-tagged, JSON-serialisable form of `value`. Structural, so no separator can collide."""
    if isinstance(value, bool):  # MUST precede int - isinstance(True, int) is True
        return ["bool", value]
    if isinstance(value, int):
        return ["int", value]
    if isinstance(value, float):
        return ["float", repr(value)]  # repr round-trips; keeps nan/inf/-0.0 distinguishable
    if isinstance(value, str):
        return ["str", value]
    if value is None:
        return ["none", None]
    if isinstance(value, Mapping):
        # Keys go through _canon too: a bare str(k) collides {1: x} with {"1": x}.
        return ["map", sorted((_canon(k), _tag(v)) for k, v in value.items())]
    if isinstance(value, (list, tuple)):
        return ["list" if isinstance(value, list) else "tuple", [_tag(v) for v in value]]
    if isinstance(value, (set, frozenset)):
        return ["set", sorted(_canon(v) for v in value)]
    raise TypeError(f"fingerprint: unsupported type {type(value).__name__!r}; extend _tag deliberately")


def _canon(value: object) -> str:
    """The single canonicalisation path - used by `fingerprint`, by mapping keys, and by set members, so
    no two positions can disagree about how a value serialises."""
    return json.dumps(_tag(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(payload: Mapping[str, object], *, length: int = 16) -> str:
    """Deterministic, collision-resistant hex digest over a mapping of declared inputs.

    Type-tagged in both the value and the key position; structural rather than concatenated;
    order-insensitive; and fail-closed on an unsupported type (raising rather than falling back to
    `str()`, which is exactly how two distinct objects acquire one digest).

    Three deliberate consequences, all erring toward an unnecessary cache MISS rather than a stale HIT:
    `-0.0` and `0.0` digest differently despite comparing equal; two mappings that compare equal can
    digest differently (`{True: "x"} == {1: "x"}` in Python, but the keys tag differently); and
    extending `_tag` to a new type is an explicit change with a test rather than an accident."""
    return hashlib.sha256(_canon(dict(payload)).encode("utf-8")).hexdigest()[:length]


def fingerprint_model(model: BaseModel, *, exclude: frozenset[str] = frozenset(), length: int = 16) -> str:
    """Fingerprint ALL of `model`'s fields except those named in `exclude`.

    Declare what determines the cached artifact's CONTENT, not what CONSUMES it. Anything recomputed
    downstream on every run is excluded by construction.

    Fail-closed: a field ADDED to the model later is INCLUDED unless someone explicitly excludes it, so
    forgetting to revisit this call costs a recompute, never a stale reuse. An inclusion list would have
    the opposite (silent, wrong) failure direction.

    Raises ValueError if `exclude` names a field the model does not have - otherwise a renamed or deleted
    field leaves a silently-ineffective exclusion behind.

    LIMITATION, stated deliberately: this checks that exclusions EXIST, not that they are CORRECT. An
    author can exclude a field that does matter and get a fingerprint that never changes. This converts a
    silent omission into a visible, reviewable, wrong line - it does not prove the scope. Pin the
    reasoning behind each exclusion with a test and cross-reference it from the exclusion comment."""
    fields = set(type(model).model_fields)
    unknown = exclude - fields
    if unknown:
        raise ValueError(
            f"exclude names non-existent field(s) {sorted(unknown)} on {type(model).__name__}; "
            f"known fields: {sorted(fields)}"
        )
    payload = {k: v for k, v in model.model_dump().items() if k not in exclude}
    return fingerprint(payload, length=length)
