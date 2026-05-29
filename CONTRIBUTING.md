# Contributing to ruthless-efficiency

## Development Setup

```bash
git clone https://github.com/karsten-s-nielsen/ruthless-efficiency.git
cd ruthless-efficiency
uv venv --python 3.10
uv pip install -e ".[dev]"                          # core-only dev install
# For the FULL test suite (backends/evolve/optuna tests + e2e gates), install the extras too:
uv pip install -e ".[dev,backends,evolve,optuna]"
```

The core-only install (`.[dev]`) runs the core test subset; the backend/strategy tests under
`tests/backends/`, `tests/strategies/evolve/`, and `tests/strategies/optuna_/` (and their e2e gates)
require the extras. CI runs both: a full `test` job with all extras and a `core-lean` job that proves
the default install stays dependency-light.

## Running Tests

```bash
# Full suite
uv run pytest -v

# A single module
uv run pytest tests/test_random_strategy.py -v

# Performance baselines (not part of the default run — see benchmarks/)
uv run pytest benchmarks/ --benchmark-only
```

## Code Quality

The full local gate mirrors CI exactly:

```bash
uv run ruff check ruthless tests
uv run ruff format --check ruthless tests
uv run pyright
uv run lint-imports
uv run pytest -v
```

All five must pass before opening a PR (Shift Left — catch it locally, not in CI).

## Pull Request Process

1. Create a feature branch from `main`
2. Write tests first (TDD preferred — red → green per change)
3. Ensure the full gate above is green
4. Keep commits focused — one logical change per commit
5. Include a clear description of what and why

## Architecture Guidelines

- **Hexagonal / pure core.** `ruthless/` defines the ports (`Objective`, `SearchStrategy`,
  `ComputeBackend`) and value types (`Candidate`, `Metrics`, `Result`) and depends only on
  `pydantic` + `numpy` (+ `pyyaml`).
- **Dependency direction is one-way.** Strategies and backends depend on the core, never the reverse.
  This is enforced by import-linter (`.importlinter`) — `lint-imports` must stay green.
- **Each strategy owns its loop.** The core imposes no template-method driver; a strategy drives the
  search and returns a `Result` that `report.py` renders.
- **Error taxonomy vs. penalties.** Fatal evaluation failures (`ruthless.errors`) are surfaced and
  never recorded as a score; degenerate-but-valid candidates get a recorded penalty
  (`ruthless.guards`). Only the *scored* metric is checked for finiteness. The cross-wire
  failure-marker vocabulary (`combined_score`/`error`/`_error_text`) lives in `ruthless.wire`.
- **Remote execution (`[backends]`).** Compute backends require a `RemoteObjective` exposing a
  `RemoteRef` (install spec + `module:callable` entrypoint); `BackendPool` adds priority-ordered
  dispatch with a bounded transient-retry contract. Backends *raise* `TransientEvaluationError`
  (retried) or `FatalEvaluationError` (surfaced) — they never record a sentinel.
- **Cached objectives (`[optuna]`).** `CachedObjective` (a core Protocol) declares a one-time
  `prepare()` invariant + a per-trial `evaluate_patch`; `ruthless.testing.assert_cache_equivalence`
  proves the fast path equals the full recompute. `OptunaStrategy` uses the fast path.
- New public functions and classes need docstrings explaining what they do and how to use them.

For the system-level view, download [`docs/c4/architecture.html`](docs/c4/architecture.html) and open
it in a browser (C4 System Context / Container / Component diagrams). The conventions above are
detailed in [`CLAUDE.md`](CLAUDE.md); the design rationale is in the
[spec](docs/superpowers/specs/2026-05-28-optimization-engine-carveout-design.md).

## Versioning

The project is `0.x` — the ports are still being validated against real consumers. Breaking changes
to the public ports (`Objective`, `SearchStrategy`, `ComputeBackend`) and value types may occur before
`1.0`. Every release — and any breaking change — is recorded in [CHANGELOG.md](CHANGELOG.md).
