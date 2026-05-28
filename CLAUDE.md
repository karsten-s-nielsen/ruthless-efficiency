# ruthless-efficiency

A general optimisation/search substrate: a pure hexagonal core + pluggable search strategies +
pluggable compute backends. Currently at **Phase 1A** (`0.1.0`) — core ports + a built-in
`RandomSearchStrategy`, validated by a dependency-free determinism + convergence gate.

## Architecture

- **Hexagonal.** `ruthless/` is the pure core: it defines the **ports** (`Objective`,
  `SearchStrategy`, `ComputeBackend` — structural `Protocol`s) and **value types** (`Candidate`,
  `Metrics = dict[str, float]`, `Evaluation`, `Result`). The core depends only on `pydantic` +
  `numpy` (+ `pyyaml`).
- **One-way dependency direction.** Strategies (`ruthless/strategies/`) and backends depend on the
  core, never the reverse; strategies do not import each other or backends. Enforced by import-linter
  (`.importlinter`, 2 contracts) — `lint-imports` must stay green.
- **Each strategy owns its loop.** The core imposes no template-method driver. A strategy drives the
  search and returns a `Result`; `report.py` renders it (JSON + Markdown). Persistence/resume is
  strategy-internal.
- **Backends are the inter-candidate dispatch path.** One evaluation → one compute resource. A
  backend returns the objective's metrics **verbatim** — it does not police metric values.
  `InProcessBackend` is the only Phase 1A backend; `timeout` is on the port (`evaluate(..., *,
  timeout=None)`) but only remote backends (Plan 1B) enforce it.

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

- **Phase 1A (now):** core ports + value types + config + reporting + observability +
  `RandomSearchStrategy` + the determinism/convergence gate.
- **Plan 1B:** `EvolveStrategy` (our orchestration over OpenEvolve), `BackendPool` + SSH/HF-Jobs/
  Docker backends, per-candidate timeout + transient-retry contract.
- **Phase 2:** `OptunaStrategy`, `CachedObjective`, group-scoring.

## Reference docs

- Spec: `docs/superpowers/specs/2026-05-28-optimization-engine-carveout-design.md`
- Phase 1A plan (+ execution-deviations addendum):
  `docs/superpowers/plans/2026-05-28-ruthless-efficiency-phase1a.md`
