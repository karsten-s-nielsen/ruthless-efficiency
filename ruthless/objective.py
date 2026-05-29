"""The Objective port — the ONLY thing a consumer must write. Structural (duck-typed) Protocol:
implementers need not inherit it. runtime_checkable isinstance is NAME-only (won't catch a wrong
signature) — used for a shallow CLI guard (cli.py), not a correctness guarantee.

CachedObjective (invariant-prep + per-trial patch, the TC3 pattern) is an Optuna-family extension
that does NOT map to evolve; it lands in Phase 2 with [optuna]."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ruthless.result import Candidate, Metrics


@runtime_checkable
class Objective(Protocol):
    def evaluate(self, candidate: Candidate) -> Metrics: ...


@runtime_checkable
class CachedObjective(Protocol):
    """An Objective whose expensive work is invariant across the tuned params, with a cheap per-trial
    patch (the TC3 invariant-prep / per-trial-patch pattern; Phase 2, [optuna]-family). The consumer
    implements BOTH the full path (`evaluate`, the Objective port) and the fast path (`prepare` once +
    `evaluate_patch` per candidate); `ruthless.testing.assert_cache_equivalence` proves they agree.

    `patch_params` declares the ONLY params a trial may vary — everything else feeds the invariant. A
    param tuned but NOT in `patch_params` would change the invariant yet reuse the cached one (a silent
    wrong score); OptunaStrategy rejects that at construction. This is a pure Protocol — no optuna
    import, so it stays in core."""

    patch_params: frozenset[str]

    def evaluate(self, candidate: Candidate) -> Metrics: ...  # full recompute (Objective port)

    def prepare(self) -> object: ...  # build the expensive invariant once

    def evaluate_patch(self, invariant: object, candidate: Candidate) -> Metrics: ...  # cheap per-trial
