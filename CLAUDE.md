# ruthless-efficiency

A general optimisation/search substrate: a pure hexagonal core + pluggable search strategies +
pluggable compute backends. Ships at `0.1.0` (`0.x` — API unstable). **Phase 1A** delivered the core
ports + built-in `RandomSearchStrategy` (determinism gate). **Phase 1B (library side)** adds the
optional `[backends]` extra (`BackendPool` + `local_cuda`/`remote_ssh`/`hf_jobs`/`docker`, with the
per-candidate timeout + transient-retry contract) and the `[evolve]` extra (`EvolveStrategy`, a thin
adapter over OpenEvolve, + the AST sandbox). The lakehouse consumer migration (Plan 1B Part C) runs
in the lakehouse repo, not here.

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
  and run the entrypoint (`local_cuda` in-process; `remote_ssh`/`hf_jobs` on a node) and enforce
  `timeout`. `BackendPool` is a priority-ordered pool with a bounded transient-retry contract.
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

## Scope map

- **Phase 1A (done):** core ports + value types + config + reporting + observability +
  `RandomSearchStrategy` + the determinism/convergence gate.
- **Plan 1B — library side (done):** `[backends]` (`BackendPool` + `local_cuda`/`remote_ssh`/`hf_jobs`/
  `docker`, timeout + transient-retry contract, `RemoteObjective`/`RemoteRef`) and `[evolve]`
  (`EvolveStrategy` over OpenEvolve + the AST sandbox). **Part C (lakehouse consumer migration)** is
  pending and runs in the lakehouse repo (behind its hard-gate).
- **Phase 2:** `OptunaStrategy`, `CachedObjective`, group-scoring.

## Reference docs

- Spec: `docs/superpowers/specs/2026-05-28-optimization-engine-carveout-design.md`
- Phase 1A plan: `docs/superpowers/plans/2026-05-28-ruthless-efficiency-phase1a.md`
- Phase 1B plan (rev 3): `docs/superpowers/plans/2026-05-28-ruthless-efficiency-phase1b.md`
