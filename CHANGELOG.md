# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) (with the usual `0.x` caveat: the public
API may change between minor versions until `1.0`).

## [Unreleased]

### Fixed
- `ruthless._fingerprint` now handles `Path`, `Enum`, `datetime`, and `date` instead of raising. A config
  model gaining a field of any of those types made `fingerprint_model` raise `TypeError` **mid-run**
  rather than degrade — reachable today, since `model_dump()` yields live `Path`/`Enum` objects. Each is
  type-tagged: paths by POSIX form (so the same logical path digests identically across OSes), enums by
  class **and** value (so two enums sharing a value cannot collide), datetimes/dates by ISO form.
  - The `enum` branch is checked **first** and `datetime` **before** `date`, because an `IntEnum`/`StrEnum`
    member is also an `int`/`str` and `datetime` subclasses `date` — the same subclass-shadowing trap as
    `bool` before `int`. Pinned by tests; a wrong branch order silently collides the subclass with its base.

### Changed
- `ruthless._provenance._repo_tracks_module` is now cached, removing one git subprocess per
  `SearchStrategy.run()`. Whether a repo tracks a given source file is static for a process. The tree
  **state** is deliberately *not* cached — a run that starts clean and turns dirty must report dirty, and
  a stale `"clean"` is exactly the false provenance the module exists to prevent. Both properties are
  pinned by tests.
- `WorkUnitMapError.results` documents why it is `list[object | None]` and cannot be narrower (`except
  WorkUnitMapError as exc` erases any type parameter, so a generic exception would not help), and points
  callers wanting typed partial results at `on_error="collect"`. A test pins that both routes return
  identical values.

### Internal
- The published sdist no longer ships `/.github` — CI workflows, `dependabot.yml`, `CODEOWNERS`, and the
  PR/issue templates (8 files). They are development infrastructure with no use to anyone installing the
  package, and the same reasoning already excluded `CLAUDE.md` and the internal planning docs. Excluding
  them also makes "a workflow-only change does not alter the published package" true rather than
  nearly-true. The wheel was never affected; user-facing docs, the ADRs, and the C4 diagram still ship.

## [0.3.0] - 2026-07-30

Minor bump rather than patch: `map_work_units` changes which exception a failing map raises, and under
this project's `0.x` convention a breaking change takes the minor slot.

### Added
- Private core cache-identity primitive (`ruthless._fingerprint`): a type-tagged, structural,
  order-insensitive, fail-closed digest over declared inputs, plus `fingerprint_model(model, exclude=...)`
  whose invalidation scope is a declared EXCLUSION set. A field added to a model later is included by
  default, so the failure mode of forgetting to revisit an exclusion is an unnecessary cache miss
  (recompute) rather than a stale hit (wrong). Naming a non-existent field in `exclude` raises, closing
  the renamed-field gap. Private and absent from `ruthless.__all__` — no public API commitment.
- `Result.provenance` now carries ruthless's own code identity: `ruthless_version`,
  `ruthless_git_commit` and `ruthless_git_state` (`"clean"` | `"dirty"` | `"unknown"`), captured at run
  time. A commit is never reported without a state, and an absent/failing git reports `"unknown"` rather
  than degrading to `"clean"` — a bare SHA from a dirty tree is verifiable-looking false provenance,
  which is worse than recording nothing. Keys are `ruthless_`-prefixed because this identifies ruthless's
  tree, not the consumer's objective code; the enclosing repo must be proved to track this module as
  source, so a wheel installed into a project-local venv reports `"unknown"` instead of stamping the
  consumer's commit.

### Changed (BREAKING)
- `ruthless.parallel.map_work_units` now has a real error model. Previously it raised the first unit
  exception by input order, **discarded every completed result**, and the set of units actually attempted
  depended on `workers` — a documented performance knob silently deciding which of the caller's side
  effects happened. Under a parallel executor it also could not fail fast at all: `shutdown(wait=True)`
  meant the exception surfaced only after the whole map finished (measured: a fault at 0.01s surfaced at
  2.03s with 7 of 8 units run and all results thrown away).
  - Every unit is now **always attempted**, at every `workers` value and under both executors.
  - Unit failures aggregate into a new `WorkUnitMapError` (a sibling of `TransientEvaluationError` /
    `FatalEvaluationError` under `OptimizationError`, so `BackendPool` can never retry it) carrying
    every `UnitFailure` **and** the partial results.
  - New `on_error="collect"` returns `(results, failures)` instead of raising, with `None` in each
    failed slot. A dead pool still propagates `concurrent.futures.BrokenExecutor` unwrapped.
  - **Migration:** replace `except ValueError` (or whatever your unit raised) around `map_work_units`
    with `from ruthless.parallel import WorkUnitMapError` / `except WorkUnitMapError` and read
    `exc.failures[i].exception`, or switch to `on_error="collect"`. Note a systematic failure now costs a
    full pass rather than short-circuiting.

### Changed
- `EvolveStrategy`'s seed-result cache fingerprint now delegates to `ruthless._fingerprint`. The set of
  inputs it covers is unchanged (`epochs` + `seed`; `timeout_seconds` remains excluded, and that
  exclusion's load-bearing read filter is now pinned by a test), but the **digest value changes**, so
  existing on-disk seed caches miss once and recompute. Benign, and in the fail-closed direction. The old
  hand-rolled `sha256(f"{epochs}:{seed}")` used untagged string concatenation over a `:` separator, which
  was collision-free only because both fields are ints.
- `render_summary_md` renders provenance as one `- key: value` line per entry instead of a single-line
  dict repr, so `ruthless_git_state` stays visible as the dict grows. The machine-readable surface
  (`render_json`) is unchanged; the docstring at `report.py:40` already directs machine consumers there.

### Internal
- The `__version__` literal moved from `ruthless/__init__.py` to a new `ruthless/_version.py`, re-exported
  from the package root — `ruthless.__version__` is unchanged for all callers. Required because
  `__init__.py` is the curated public API and therefore imports a strategy, so a core module reading the
  version from the package root transitively imported `ruthless.strategies` and broke the
  `core-isolation` import-linter contract.
- **The version is now single-sourced.** `pyproject.toml` declares `dynamic = ["version"]` with
  `[tool.hatch.version] path = "ruthless/_version.py"`, so hatchling reads the same literal the runtime
  does. Previously the packaging version and `__version__` were two independent literals with nothing
  enforcing agreement; drift meant wheel metadata disagreeing with `ruthless.__version__` — and, now that
  provenance stamps `ruthless_version` into every `Result`, a wrong version recorded in result artifacts.
  Deleting the duplication beats testing for it. **Release note:** bump `ruthless/_version.py` and the
  packaging version follows; the remaining hand-edits are the `CLAUDE.md` "Ships at" line and the
  CHANGELOG section header.

## [0.2.1] - 2026-05-30

### Fixed
- `OptunaStrategy.run`: a fresh warm-started study now runs exactly `n_trials` trials (the warm-start
  baseline is the first trial), instead of `n_trials - 1`. The enqueued `WAITING` baseline was
  double-counted — subtracted from the remaining-trials budget *and* consumed by `study.optimize` —
  so at `n_trials=2` the search collapsed to just the baseline with zero exploration. The
  remaining-trials guard now reads the persisted trial count *before* `enqueue_trial`, preserving
  resume semantics (persisted `COMPLETE`/`FAILED`/`PRUNED` still count; the baseline is not
  re-enqueued on resume).

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
