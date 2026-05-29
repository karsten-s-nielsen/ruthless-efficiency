from pathlib import Path

import pytest

from ruthless.backends.base import is_objective_failure, parse_last_json_line, program_to_path, require_remote
from ruthless.errors import FatalEvaluationError
from ruthless.remote import RemoteRef
from ruthless.result import Candidate


class _Remote:
    def evaluate(self, candidate):
        return {"loss": 0.0}

    @property
    def remote_ref(self):
        return RemoteRef(entrypoint="m:f")

    epochs = 1
    seed = 0


def test_parse_last_json_line_finds_metrics_among_noise():
    out = 'loading...\nepoch 1\n{"combined_score": 0.8, "spearman_rho": 0.7}\n'
    assert parse_last_json_line(out) == {"combined_score": 0.8, "spearman_rho": 0.7}


def test_parse_last_json_line_raises_on_no_json():
    with pytest.raises(FatalEvaluationError):
        parse_last_json_line("no json here\nstill none\n")


def test_require_remote_returns_objective_for_remote_objective():
    obj = require_remote(_Remote(), backend="RemoteSSHBackend")
    assert obj.remote_ref.entrypoint == "m:f"


def test_require_remote_raises_for_plain_objective():
    class _Plain:
        def evaluate(self, candidate):
            return {"loss": 0.0}

    with pytest.raises(FatalEvaluationError):
        require_remote(_Plain(), backend="RemoteSSHBackend")


def test_program_to_path_writes_temp_file_and_cleans_up():
    with program_to_path(Candidate("c", {"x": 1.0}, program="def f(): return 1")) as p:
        assert p is not None and Path(p).read_text() == "def f(): return 1"
    assert not Path(p).exists()  # cleaned up on exit


def test_program_to_path_yields_none_without_program():
    with program_to_path(Candidate("c", {"x": 1.0})) as p:
        assert p is None


def test_is_objective_failure_detects_marker():
    assert is_objective_failure({"combined_score": 0.0, "error": 1}) is True
    assert is_objective_failure({"combined_score": 0.0, "_error_text": "tb"}) is True
    assert is_objective_failure({"combined_score": 0.8}) is False
