# Phases & scope — history and rationale

> Class-2 context for the header and the `## Key Phase-2 conventions` of [AGENTS.md](../../AGENTS.md).
> AGENTS.md keeps the current status + the enforceable invariants; this file holds the phase-by-phase
> history and the *why*, moved verbatim from the pre-restructure `CLAUDE.md`.

## Overview (phase history)

A general optimisation/search substrate: a pure hexagonal core + pluggable search strategies +
pluggable compute backends. Ships at `0.7.0` (`0.x` — API unstable). **Phase 1A** delivered the core
ports + built-in `RandomSearchStrategy` (determinism gate). **Phase 1B (library side)** adds the
optional `[backends]` extra (`BackendPool` + `local_cuda`/`remote_ssh`/`hf_jobs`/`docker`, with the
per-candidate timeout + transient-retry contract) and the `[evolve]` extra (`EvolveStrategy`, a thin
adapter over OpenEvolve, + the AST sandbox). Since `0.6.0` `EvolveStrategy` also runs a **general
code-evolution mode** (`evolution.code_evolution=True` evolves an arbitrarily-named function; the evolved
source is always handed to the entrypoint via `program_path` and the `config = {…}` dict is optional) —
the hardcoded `custom_embed`/`custom_layers` name-detection is **gone from core**, and validation is
**secure-by-default**: a code run requires a `validation_profile` **or** an explicit
`EvolveConfig.allow_unvalidated_code=True` opt-out. **Phase 2 (library side)** adds the `[optuna]` extra
(`OptunaStrategy` — resumable Bayesian/sampler calibration; `CachedObjective` invariant-prep /
per-trial-patch port + `ruthless.testing.assert_cache_equivalence`). The consumer migrations (lakehouse
evolve, and **silly-kicks adopting `ruthless[optuna]`** for its own calibrations) run in those repos,
not here.

## Scope map

- **Phase 1A (done):** core ports + value types + config + reporting + observability +
  `RandomSearchStrategy` + the determinism/convergence gate.
- **Plan 1B — library side (done):** `[backends]` (`BackendPool` + `local_cuda`/`remote_ssh`/`hf_jobs`/
  `docker`, timeout + transient-retry contract, `RemoteObjective`/`RemoteRef`) and `[evolve]`
  (`EvolveStrategy` over OpenEvolve + the AST sandbox). **Part C (lakehouse consumer migration)** is
  pending and runs in the lakehouse repo (behind its hard-gate).
- **Phase 2 — library side (done):** `[optuna]` (`OptunaStrategy` — resumable SQLite study, warm-start,
  C3 resume contract; `CachedObjective` + `ruthless.testing.assert_cache_equivalence`). Group-scoring
  was **deferred** (consumer runs CV in its own `score_fn`). **Consumer adoption pending:** silly-kicks
  installs `ruthless[optuna]` and owns its parameter objectives (the first real consumer); lakehouse
  evolve + TC3 migrations later.

## Key Phase-2 conventions

- **`CachedObjective`** (core Protocol, no optuna dep): full `evaluate` + `prepare()` (invariant, once)
  + `evaluate_patch(invariant, candidate)` + `patch_params`. `OptunaStrategy` uses the fast path and
  rejects tuning any param not in `patch_params` (H1/M5). `assert_cache_equivalence` proves fast==full
  and ENFORCES that candidates vary every patch_param.
- **OptunaStrategy resume (C3):** no lost/dup trials + monotone growth + converge — NOT trajectory
  identity (Optuna doesn't persist sampler RNG). `best`/`history` are reconstructed from `study.trials`
  so they span the whole store on resume. SQLite store = single-process only.
- **OptunaStrategy observer (0.5.0):** `run(..., observer=None)` accepts a neutral `Observer`
  (`(ProgressEvent) -> None`; both are public core types). It fires once per completed trial via
  `study.optimize(callbacks=...)`. `ProgressEvent.number` is the study-global trial number (does NOT
  reset on resume); a raising observer is logged-and-isolated (never aborts the search); the core
  imports no sink (`state` is a neutral `str`, not Optuna's `TrialState`). Optuna-only by design — a
  port-level hook random/evolve merely ignored would be a silent no-op. The `Observer.__call__`
  parameter is positional-only so any 1-arg callable (incl. `list.append`) conforms under pyright basic.

## Config union (phase note)

- Config is a discriminated-union surface: only `random` is registered in Phase 1A; evolve/optuna
  extend the union later without a breaking change.
