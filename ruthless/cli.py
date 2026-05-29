"""CLI entry. The objective import-string is a TRUSTED-CONFIG-ONLY convenience: it resolves via
importlib.import_module + getattr (NEVER eval) and is isinstance-checked against Objective (spec L3;
the check is name-only — see objective.py). Programmatic construction is the primary API (spec M2)."""

from __future__ import annotations

import argparse
import importlib
from collections.abc import Callable
from typing import Any

from ruthless.backend import InProcessBackend
from ruthless.config import RandomConfig, RuthlessConfig
from ruthless.objective import Objective
from ruthless.report import render_json, render_summary_md
from ruthless.strategies.random_.strategy import RandomSearchStrategy


def resolve_objective(spec: str) -> Objective:
    module_path, _, attr = spec.partition(":")
    if not attr:
        raise ValueError(f"objective spec must be 'package.module:attr', got {spec!r}")
    obj = getattr(importlib.import_module(module_path), attr)
    if not isinstance(obj, Objective):
        raise TypeError(f"resolved object {spec!r} does not satisfy the Objective protocol")
    return obj


# Strategy-config type -> builder. Only `random` is CLI-available: it needs nothing beyond the config
# (evolve/optuna require a results_dir/backend the CLI does not supply, so they stay programmatic-only
# by design). A registry instead of an isinstance ladder mirrors backends/_REGISTRY (Open/Closed): a
# new CLI-available strategy registers a row rather than editing a branch.
_STRATEGY_BUILDERS: dict[type, Callable[[Any, int], Any]] = {
    RandomConfig: lambda strategy_cfg, seed: RandomSearchStrategy(strategy_cfg, seed=seed),
}


def _build_strategy(cfg: RuthlessConfig):
    builder = _STRATEGY_BUILDERS.get(type(cfg.strategy))
    if builder is None:
        raise ValueError(f"strategy {cfg.strategy.kind!r} not available in this build")
    return builder(cfg.strategy, cfg.seed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ruthless Efficiency")
    parser.add_argument("--config", required=True)
    parser.add_argument("--objective", required=True, help="trusted import-string 'pkg.mod:attr'")
    args = parser.parse_args()

    cfg = RuthlessConfig.from_yaml(args.config)
    result = _build_strategy(cfg).run(resolve_objective(args.objective), backend=InProcessBackend())
    print(render_json(result))
    print(render_summary_md(result))


if __name__ == "__main__":
    main()
