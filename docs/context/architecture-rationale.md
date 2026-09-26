# Architecture — rationale

> Class-2 context for the `## Architecture` section (and the module-layout conventions) of
> [AGENTS.md](../../AGENTS.md). The enforceable invariants live there; this file holds the *why*,
> moved verbatim from the pre-restructure `CLAUDE.md`.

## The ports and the dependency direction

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

## Version single-source (core-isolation)

- **`__version__` lives in `ruthless/_version.py`** and is the version's SINGLE source. It cannot live
  in `__init__.py`: that module is the curated public API and imports a strategy, so a core module
  reading the version from it would break the `core-isolation` contract. `pyproject.toml` declares
  `dynamic = ["version"]` and hatchling reads this file (`[tool.hatch.version] path`), so packaging and
  runtime cannot drift. **On release, bump this one line**; the only remaining hand-edits are the
  "Ships at" line in AGENTS.md and the CHANGELOG section header.

## Logging and the CLI objective loader

- **Library never configures root logging.** Use `ruthless._logging.get_logger(name)` →
  `logging.getLogger("ruthless.<name>")`. No handlers are attached; consumers own that.
- **The CLI objective loader is trusted-config-only.** `resolve_objective("pkg.mod:attr")` uses
  `importlib` + `getattr` (never `eval`) and isinstance-checks against `Objective` (a name-only
  guard). Programmatic construction is the primary API.
