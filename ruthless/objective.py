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
