import pytest

from ruthless.cli import resolve_objective
from ruthless.objective import Objective


def test_resolve_objective_imports_and_checks():
    assert isinstance(resolve_objective("tests.fixtures.objectives:quadratic"), Objective)


def test_resolve_objective_rejects_non_objective():
    with pytest.raises(TypeError):
        resolve_objective("os:getcwd")  # resolves via importlib but is not an Objective
