import pytest

from ruthless.backends.docker import DockerBackend
from ruthless.errors import FatalEvaluationError
from ruthless.result import Candidate


def test_docker_unavailable():
    assert DockerBackend().available() is False


class _Obj:
    def evaluate(self, candidate):
        return {}


def test_docker_evaluate_raises_fatal():
    with pytest.raises(FatalEvaluationError):
        DockerBackend().evaluate(Candidate("c", {"x": 1.0}), _Obj())
