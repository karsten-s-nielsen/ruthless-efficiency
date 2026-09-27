import pytest

from ruthless.backend import InProcessBackend
from ruthless.cli import _build_strategy, resolve_objective
from ruthless.config import RuthlessConfig
from ruthless.objective import Objective
from ruthless.result import Candidate
from ruthless.strategies.grid_ import GridSearchStrategy


def test_resolve_objective_imports_and_checks():
    assert isinstance(resolve_objective("tests.fixtures.objectives:quadratic"), Objective)


def test_resolve_objective_rejects_non_objective():
    with pytest.raises(TypeError):
        resolve_objective("os:getcwd")  # resolves via importlib but is not an Objective


class _GridObj:
    def evaluate(self, candidate: Candidate) -> dict[str, float]:
        return {"loss": float(candidate.params["b"])}


def test_cli_grid_runs_end_to_end():
    cfg = RuthlessConfig.model_validate(
        {
            "strategy": {
                "kind": "grid",
                "metric": "loss",
                "design": "cartesian",
                "param_space": {"b": {"kind": "int", "lo": 1, "hi": 2}},
            }
        }
    )
    strategy = _build_strategy(cfg)
    assert isinstance(strategy, GridSearchStrategy)
    result = strategy.run(_GridObj(), backend=InProcessBackend())
    assert result.best is not None
    assert len(result.history) == 2
