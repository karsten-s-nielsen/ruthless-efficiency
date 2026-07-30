# ruthless-efficiency

A general optimisation/search substrate: a pure hexagonal core + pluggable search strategies +
pluggable compute backends. Ships at `0.2.1` (`0.x` — API unstable). **Phase 1A** delivered the core
ports + built-in `RandomSearchStrategy` (determinism gate). **Phase 1B (library side)** adds the
optional `[backends]` extra (`BackendPool` + `local_cuda`/`remote_ssh`/`hf_jobs`/`docker`, with the
per-candidate timeout + transient-retry contract) and the `[evolve]` extra (`EvolveStrategy`, a thin
adapter over OpenEvolve, + the AST sandbox). **Phase 2 (library side)** adds the `[optuna]` extra
(`OptunaStrategy` — resumable Bayesian/sampler calibration; `CachedObjective` invariant-prep /
per-trial-patch port + `ruthless.testing.assert_cache_equivalence`). The consumer migrations (lakehouse
evolve, and **silly-kicks adopting `ruthless[optuna]`** for its own calibrations) run in those repos,
not here.

## Architecture

- **Hexagonal.** `ruthless/` is the pure core: it defines the **ports** (`Objective`,
  `SearchStrategy`, `ComputeBackend` — structural `Protocol`s) and **value types** (`Candidate`,
  `Metrics = dict[str, float]`, `Evaluation`, `Result`). The core depends only on `pydantic` +
  `numpy` (+ `pyyaml`).
- **One-way dependency direction.** Strategies (`ruthless/strategies/`) and backends
  (`ruthless/backends/`) depend on the core, never the reverse; strategies do not import each other or
  the backends package, and backends do not import strategies. Enforced by import-linter
  (`.importlinter`, **3 contracts**) — `lint-imports` must stay green. (`EvolveStrategy` receives a
  backend via `run(objective, *, backend)`; its OpenEvolve worker script imports `create_backend` at
  runtime in the worker subprocess — not a static strategy→backends import.)
- **Each strategy owns its loop.** The core imposes no template-method driver. A strategy drives the
  search and returns a `Result`; `report.py` renders it (JSON + Markdown). Persistence/resume is
  strategy-internal.
- **Backends are the inter-candidate dispatch path.** One evaluation → one compute resource, on the
  single port `evaluate(candidate, objective, *, timeout) -> Metrics`. `InProcessBackend` (core) runs
  `objective.evaluate(candidate)` for pure/CPU objectives. The `[backends]` compute backends require a
  **`RemoteObjective`** (an objective that opts into remote execution via a `RemoteRef` = install spec
  + `module:callable` entrypoint, replacing the old `shared.wheel`/`target` convention); they resolve
  and run the entrypoint (`local_cuda` in-process; `remote_ssh`/`hf_jobs` on a node). The
  cross-process backends (`remote_ssh`/`hf_jobs`) enforce the per-candidate `timeout`; the in-process
  ones (`InProcessBackend`, `local_cuda`) accept it for port compatibility but cannot cancel
  in-process work, so they document-and-ignore it. `BackendPool` is a priority-ordered pool with a
  bounded transient-retry contract.
- **Unified error model (1B).** Backends never record a sentinel score: they **raise**
  `TransientEvaluationError` (transport/infra — retried by the pool) or `FatalEvaluationError`
  (unparseable output / missing `remote_ref` / a node-side objective-crash marker). For evolve, the
  `EvolveEvaluator` is the **single** place that maps any failure to the OpenEvolve worst-score
  sentinel (objective vs. infra distinguished in artifacts), because OpenEvolve needs a score per
  candidate.

## Key conventions

- **Scored-metric finiteness only.** `classify_metric()` raises `FatalEvaluationError` if the
  *optimisation-target* metric is inf/NaN. Diagnostic/auxiliary metrics are allowed to be non-finite
  — never pass them to `classify_metric()`.
- **Fatal errors vs. penalties are distinct.** Fatal evaluation failures (`ruthless.errors`) are
  surfaced and **never** recorded as a score. Degenerate-but-valid candidates get a recorded penalty
  (`ruthless.guards.penalty_metrics`) — a finite, deliberately-bad score, not an error.
- **`Candidate` is hashable** (frozen, order-independent `__eq__`/`__hash__` over its params) so it
  can serve as a cache/dedup key. Do not mutate `params` after construction.
- **`Result` is treat-as-immutable once returned** by `SearchStrategy.run`.
- **`map_work_units` always attempts EVERY unit.** `workers` is a speed knob and must never change
  *which* units ran — work units are consumer code with consumer side effects. Unit failures aggregate
  into `WorkUnitMapError` (an `OptimizationError` sibling of `Transient`/`Fatal`, deliberately outside
  the evaluation taxonomy so `BackendPool` cannot retry it) carrying every failure **and** the partial
  results; `on_error="collect"` returns them instead. A dead pool propagates `BrokenExecutor`
  unwrapped, because that voids the attempted-every-unit guarantee. Cost: a systematic failure now
  costs a full pass (the serial path no longer short-circuits).
- **Cache identity is a declared EXCLUSION set, never an inclusion list.** `ruthless._fingerprint`
  (private core) is the one hashing implementation: type-tagged in both the **key** and value position,
  structural rather than concatenated, order-insensitive, and fail-closed on unknown types.
  `fingerprint_model(model, exclude=...)` covers every model field except the named exclusions, so a
  field added later is included automatically — the failure mode of forgetting becomes an unnecessary
  cache *miss* (recompute, safe), never a stale *hit* (wrong). Naming a non-existent field raises. Each
  exclusion carries a comment naming the test that makes it safe (see evolve's `_SEED_CACHE_EXCLUDE`).
- **Provenance never overclaims.** `ruthless._provenance.code_identity()` never reports a commit
  without a tree state, and never degrades to `"clean"` — a bare SHA from a dirty tree is
  verifiable-looking *false* provenance, worse than recording nothing. Keys are `ruthless_`-prefixed
  because they identify ruthless's tree, not the consumer's objective, and the enclosing repo must be
  proved to **track** this module (so a wheel in a consumer's venv reports `"unknown"` rather than the
  consumer's commit). Uses the `git` CLI opportunistically — absent git is a supported state, not an
  error.
- **`__version__` lives in `ruthless/_version.py`** and is the version's SINGLE source. It cannot live in
  `__init__.py`: that module is the curated public API and imports a strategy, so a core module reading
  the version from it would break the `core-isolation` contract. `pyproject.toml` declares
  `dynamic = ["version"]` and hatchling reads this file (`[tool.hatch.version] path`), so packaging and
  runtime cannot drift. **On release, bump this one line**; the only remaining hand-edits are the
  "Ships at" line below and the CHANGELOG section header.
- **Config is a discriminated-union surface.** `RuthlessConfig` carries a discriminated *strategy*
  union and a discriminated *param-space* union (`FloatRange` / `IntRange` / `Choice`, with a `log`
  flag on floats). Only `random` is registered in Phase 1A; evolve/optuna extend the union later
  without a breaking change.
- **Library never configures root logging.** Use `ruthless._logging.get_logger(name)` →
  `logging.getLogger("ruthless.<name>")`. No handlers are attached; consumers own that.
- **The CLI objective loader is trusted-config-only.** `resolve_objective("pkg.mod:attr")` uses
  `importlib` + `getattr` (never `eval`) and isinstance-checks against `Objective` (a name-only
  guard). Programmatic construction is the primary API.

## Local quality gate (mirrors CI exactly)

Run all five before declaring work done (Shift Left — catch it locally, not in CI):

```bash
uv run ruff check ruthless tests
uv run ruff format --check ruthless tests
uv run pyright
uv run lint-imports
uv run pytest -v
```

`pyright` runs on **both** `ruthless` and `tests` (see `[tool.pyright] include`).

## Workflow conventions

- **TDD** — write the failing test first, then implement (red → green per change).
- **`/final-review`** is the mandatory pre-commit quality gate for every work cycle (it also
  generates/updates the C4 diagram at `docs/c4/architecture.html`).
- **No commit without explicit user approval.**
- **No git worktrees** — project convention; work on a feature branch in this repo.

## Tech stack

Python ≥3.10 (CI on 3.10), pydantic v2, numpy (`<3`, pinned for RNG-stream stability of the
determinism gate), pyyaml. Dev: pytest + hypothesis, ruff, pyright, import-linter, hatchling.

The only external *tool* the core touches is the `git` CLI, used opportunistically by
`ruthless._provenance` — absent or failing git is a supported state (`"unknown"`), never an error. No
Python dependency is added for it.

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

## Reference docs

- Spec: `docs/superpowers/specs/2026-05-28-optimization-engine-carveout-design.md`
- Phase 1A plan: `docs/superpowers/plans/2026-05-28-ruthless-efficiency-phase1a.md`
- Phase 1B plan (rev 3): `docs/superpowers/plans/2026-05-28-ruthless-efficiency-phase1b.md`
- Phase 2 plan (rev 3): `docs/superpowers/plans/2026-05-28-ruthless-efficiency-phase2-library.md`
- Work-unit error model + cache identity (rev 3):
  `docs/superpowers/specs/2026-07-29-parallel-error-model-and-cache-identity.md` and
  `docs/superpowers/plans/2026-07-29-parallel-error-model-and-cache-identity-plan.md`

## Architecture decisions

- `docs/adr/ADR-001-ast-sandbox-security-model.md` — AST allowlist for evolve Level-2 code evolution.
- `docs/adr/ADR-002-cache-identity-and-code-provenance.md` — why cache identity is a private core
  primitive with an exclusion-set scope, and why provenance never emits a SHA without a tree state.
