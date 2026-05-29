# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) (with the usual `0.x` caveat: the public
API may change between minor versions until `1.0`).

## [0.2.0] - 2026-05-28

First published release. Ships the Phase 2 `[optuna]` extra alongside the Phase 1A/1B core, and folds
in the 2026-05-28 audit cleanup (curated public API, value-object immutability, security hardening).

### Added
- `[optuna]` extra: `OptunaStrategy` — resumable Bayesian/sampler calibration on a SQLite study
  (single-process resume; warm-start; C3 resume contract).
- `CachedObjective` core Protocol (one-time `prepare()` invariant + per-trial `evaluate_patch`) and
  `ruthless.testing.assert_cache_equivalence`, proving the fast path equals the full recompute.
- Curated top-level public API: import the supported surface from `ruthless` directly
  (`from ruthless import Candidate, RandomConfig, RandomSearchStrategy, InProcessBackend, ...`), with
  an explicit `__all__`. Per-strategy namespaces re-export their strategy
  (`ruthless.strategies.random_`, `…optuna_`, `…evolve_`).
- `ruthless.wire` — single source of truth for the cross-wire failure/score contract
  (`combined_score` / `error` / `_error_text`), replacing magic strings duplicated across backends.
- `docs/adr/ADR-001-ast-sandbox-security-model.md` — the security model behind the evolve AST
  allowlist (previously a dangling reference).
- `benchmarks/` — pytest-benchmark performance baselines for the random-search loop and
  `assert_cache_equivalence` (not part of the default test run).

### Changed
- `ruthless.config` is now a package (`space` / `common` / `strategies` submodules) instead of a
  single module. All public names still import from `ruthless.config` — no import sites change.
- `Candidate.params` is now a read-only mapping (frozen + defensively copied at construction) and
  `Choice.choices` is a tuple, enforcing the value-object immutability the dedup-key invariant relies
  on. Consumers that need a mutable copy use `dict(candidate.params)`.

### Security
- SSH backend: all `ssh`/`scp` calls now use `BatchMode=yes` and `StrictHostKeyChecking=accept-new`;
  `HF_TOKEN` is transferred to the remote node via a 0600 file (read once, then unlinked) instead of
  an inline command-line env prefix, keeping it out of the remote `ps`/shell history.
- `BackendConfig` validates `device` / `ssh_remote_dir` / `ssh_python_path` against a shell-safe
  allowlist (blocks injection when a config is sourced from templated input).
- CI workflow actions are pinned to commit SHAs (supply-chain hardening), matching the publish
  workflow.

## [0.1.0]

### Added
- Hexagonal core: the `Objective`, `SearchStrategy`, and `ComputeBackend` ports; the `Candidate`,
  `Metrics`, `Evaluation`, and `Result` value types; the discriminated-union config surface; JSON +
  Markdown reporting; the unified error taxonomy (`TransientEvaluationError` /
  `FatalEvaluationError`); and `InProcessBackend`.
- `RandomSearchStrategy` — the built-in zero-dependency baseline and the driver of the
  determinism/convergence gate (Phase 1A).
- `[backends]` extra: `BackendPool` (priority-ordered dispatch + bounded transient-retry) over
  `local_cuda` / `remote_ssh` / `hf_jobs` / `docker`, with the `RemoteObjective` / `RemoteRef`
  remote-resolution contract (Phase 1B).
- `[evolve]` extra: `EvolveStrategy` — a thin orchestration adapter over OpenEvolve — plus the AST
  allowlist validator for Level-2 code evolution (Phase 1B).
