import sys
import types
from pathlib import Path

import pytest

from ruthless.backends.local_cuda import LocalCudaBackend
from ruthless.errors import FatalEvaluationError
from ruthless.remote import RemoteRef
from ruthless.result import Candidate


def _install_entrypoint(monkeypatch, recorder):
    def train_and_evaluate(*, candidate_config, device, epochs, seed, program_path):
        # Capture program CONTENTS during the call — the temp file is cleaned up after evaluate() returns.
        program_contents = Path(program_path).read_text() if program_path is not None else None
        recorder.update(
            candidate_config=candidate_config,
            device=device,
            epochs=epochs,
            seed=seed,
            program_path=program_path,
            program_contents=program_contents,
        )
        return {"loss": candidate_config["x"] ** 2}

    monkeypatch.setitem(sys.modules, "fake_obj_mod", types.SimpleNamespace(train_and_evaluate=train_and_evaluate))


class _Remote:
    def __init__(self):
        self._ref = RemoteRef(entrypoint="fake_obj_mod:train_and_evaluate")

    def evaluate(self, candidate):
        raise AssertionError("compute backends use the entrypoint, not evaluate()")

    @property
    def remote_ref(self):
        return self._ref

    epochs = 7
    seed = 11


def test_local_cuda_resolves_entrypoint_and_passes_construction_params(monkeypatch):
    rec: dict = {}
    _install_entrypoint(monkeypatch, rec)
    b = LocalCudaBackend(device="cuda:3")
    m = b.evaluate(Candidate("r0", {"x": 4.0}, program="def f(): return 1"), _Remote())
    assert m["loss"] == 16.0
    assert rec["candidate_config"] == {"x": 4.0} and rec["device"] == "cuda:3"
    assert rec["epochs"] == 7 and rec["seed"] == 11
    # program_path is a FILE PATH (not raw source); its contents are the program (captured during the call)
    assert rec["program_path"] is not None and rec["program_path"].endswith(".py")
    assert rec["program_contents"] == "def f(): return 1"


def test_local_cuda_program_none_passes_none(monkeypatch):
    rec: dict = {}
    _install_entrypoint(monkeypatch, rec)
    LocalCudaBackend().evaluate(Candidate("r0", {"x": 1.0}), _Remote())  # no program
    assert rec["program_path"] is None


def test_local_cuda_objective_crash_raises_fatal(monkeypatch):
    def train_and_evaluate(**kw):
        raise RuntimeError("training diverged")

    monkeypatch.setitem(sys.modules, "boom_mod", types.SimpleNamespace(train_and_evaluate=train_and_evaluate))

    class _R:
        def evaluate(self, candidate):
            return {}

        @property
        def remote_ref(self):
            return RemoteRef(entrypoint="boom_mod:train_and_evaluate")

        epochs = 1
        seed = 0

    with pytest.raises(FatalEvaluationError):  # objective crash -> Fatal, not raw, not a score
        LocalCudaBackend().evaluate(Candidate("r0", {"x": 1.0}), _R())


def test_local_cuda_rejects_plain_objective():
    class _Plain:
        def evaluate(self, candidate):
            return {"loss": 0.0}

    with pytest.raises(FatalEvaluationError):
        LocalCudaBackend().evaluate(Candidate("r0", {"x": 1.0}), _Plain())
