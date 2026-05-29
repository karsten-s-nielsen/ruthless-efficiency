"""Consumer-facing test harness: prove a CachedObjective's fast path (prepare + evaluate_patch)
equals its full recompute (evaluate) for sampled candidates. The substrate cannot test consumer
correctness — the consumer calls this in its own suite (spec §8/H1). Pure: no optuna import."""

from __future__ import annotations

import math
from collections.abc import Sequence

from ruthless.objective import CachedObjective
from ruthless.result import Candidate


def assert_cache_equivalence(
    objective: CachedObjective, candidates: Sequence[Candidate], *, rtol: float = 1e-9, atol: float = 1e-12
) -> None:
    """Raise AssertionError if the fast path diverges from the full recompute for any candidate.

    IMPORTANT (H1): `candidates` MUST collectively vary EVERY param in `objective.patch_params` across
    its range. An over-declared patch_param (one that actually affects the invariant) is only caught
    when candidates exercise it. The contract is ENFORCED: with >= 2 candidates, every patch_param must
    take >= 2 distinct values across `candidates`, else this raises — so an over-declared patch_param
    can't slip through by being held constant."""
    cands = list(candidates)
    if len(cands) >= 2:
        for pp in objective.patch_params:
            values = {c.params.get(pp) for c in cands}
            if len(values) < 2:
                raise AssertionError(
                    f"patch_param {pp!r} is not exercised: all candidates share value {next(iter(values))!r}. "
                    f"assert_cache_equivalence requires candidates to vary every patch_param across its range."
                )
    invariant = objective.prepare()
    for c in cands:
        full = objective.evaluate(c)
        fast = objective.evaluate_patch(invariant, c)
        if full.keys() != fast.keys():
            raise AssertionError(f"metric keys differ for {c.id}: {sorted(full)} vs {sorted(fast)}")
        for k in full:
            a, b = full[k], fast[k]
            if math.isnan(a) and math.isnan(b):
                continue  # both paths agree the metric is NaN (e.g. a diagnostic) — not a mismatch
            if not math.isclose(a, b, rel_tol=rtol, abs_tol=atol):
                raise AssertionError(f"cache mismatch for {c.id} metric {k!r}: full={a!r} != patch={b!r}")
