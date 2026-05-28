# Ruthless Efficiency

> "Our chief weapons are Ruthless Efficiency! …and warm-start caching."

A general optimisation/search substrate: a pure hexagonal core + pluggable search strategies
(`random` built-in; `evolve`, `optuna` via extras) + pluggable compute backends.

![hero](assets/ruthless-efficiency.jpg)

## Status

`0.x` — ports are still being validated against real consumers; the API may change until `1.0`.

## Install

- `pip install ruthless-efficiency` — core + random strategy
- `pip install "ruthless-efficiency[optuna]"` — + Optuna strategy (Phase 2)
- `pip install "ruthless-efficiency[evolve]"` — + evolve strategy (our orchestration over OpenEvolve)
- `pip install "ruthless-efficiency[backends]"` — + SSH / HF-Jobs / Docker compute backends

## Quick start

Write an `Objective` (the only thing you must implement — anything with an `evaluate(candidate)`
method that returns metrics), then hand it to a strategy:

```python
from ruthless.backend import InProcessBackend
from ruthless.config import RandomConfig
from ruthless.result import Candidate
from ruthless.strategies.random_.strategy import RandomSearchStrategy


class Quadratic:
    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        return {"loss": (candidate.params["x"] - 3.0) ** 2}


cfg = RandomConfig.model_validate(
    {
        "kind": "random",
        "metric": "loss",
        "direction": "minimize",
        "n_trials": 200,
        "param_space": {"x": {"kind": "float", "lo": -10.0, "hi": 10.0}},
    }
)
result = RandomSearchStrategy(cfg, seed=42).run(Quadratic(), backend=InProcessBackend())
print(result.best.candidate.params, result.best.metrics)  # ~{'x': 3.0} {'loss': ~0.0}
```

Or drive it from a YAML config via the CLI:

```bash
ruthless --config search.yaml --objective my_package.objectives:my_objective
```

## Architecture

A pure hexagonal core (`ruthless/`) defines the ports (`Objective`, `SearchStrategy`,
`ComputeBackend`) and value types; strategies and backends depend on the core, never the reverse
(enforced by import-linter). See [`CLAUDE.md`](CLAUDE.md) for the conventions, and open
[`docs/c4/architecture.html`](docs/c4/architecture.html) in a browser to explore the C4 diagrams
(System Context, Containers, and Core Components).

Design rationale lives in the
[spec](docs/superpowers/specs/2026-05-28-optimization-engine-carveout-design.md) and the
[Phase 1A plan](docs/superpowers/plans/2026-05-28-ruthless-efficiency-phase1a.md).

## Contributing & community

- [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup and the local quality gate (mirrors CI)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — Contributor Covenant
- [SECURITY.md](SECURITY.md) — how to report a vulnerability + the security surface
- [NOTICE](NOTICE) — third-party licenses and methodological references

## License

[MIT](LICENSE) © 2026 Karsten S. Nielsen
