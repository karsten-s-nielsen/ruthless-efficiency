# Contributing to ruthless-efficiency

## Development Setup

```bash
git clone https://github.com/karsten-s-nielsen/ruthless-efficiency.git
cd ruthless-efficiency
uv venv --python 3.10
uv pip install -e ".[dev]"
```

## Running Tests

```bash
# Full suite
uv run pytest -v

# A single module
uv run pytest tests/test_random_strategy.py -v
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
  (`ruthless.guards`). Only the *scored* metric is checked for finiteness.
- New public functions need docstrings explaining what they do and how to use them.

For the system-level view, open [`docs/c4/architecture.html`](docs/c4/architecture.html) in a browser
(C4 System Context / Container / Component diagrams). The conventions above are detailed in
[`CLAUDE.md`](CLAUDE.md); the design rationale is in the
[spec](docs/superpowers/specs/2026-05-28-optimization-engine-carveout-design.md).

## Versioning

The project is `0.x` — the ports are still being validated against real consumers, so the public API
may change until `1.0`.
