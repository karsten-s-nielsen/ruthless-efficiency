import subprocess

import pytest

from ruthless.backends import remote_ssh
from ruthless.backends.remote_ssh import RemoteSSHBackend
from ruthless.errors import FatalEvaluationError, TransientEvaluationError
from ruthless.remote import RemoteRef
from ruthless.result import Candidate


class _Remote:
    def __init__(self, entrypoint="my_pkg.obj:train_and_evaluate"):
        self._ref = RemoteRef(entrypoint=entrypoint)

    def evaluate(self, candidate):
        return {"loss": 0.0}

    @property
    def remote_ref(self):
        return self._ref

    epochs = 9
    seed = 13


class _FakeProc:
    def __init__(self, stdout, returncode=0, timeout=False):
        self._stdout = stdout
        self.returncode = returncode
        self._timeout = timeout
        self.stderr = iter([])  # streamed in a thread; empty is fine

    def communicate(self, timeout=None):
        if self._timeout:
            raise subprocess.TimeoutExpired(cmd="ssh", timeout=timeout or 0.0)
        return self._stdout, ""

    def kill(self):
        pass


@pytest.fixture
def patched_ssh(monkeypatch):
    """Patch subprocess.run (mkdir/scp/echo) to no-op success; capture Popen commands."""
    monkeypatch.setattr(
        remote_ssh.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(args=a, returncode=0, stdout="OK", stderr=""),
    )
    captured: dict = {}

    def make_popen(stdout, returncode=0, timeout=False):
        def _popen(cmd, **kwargs):
            captured["cmd"] = cmd[-1] if isinstance(cmd, list) else cmd
            return _FakeProc(stdout, returncode, timeout)

        return _popen

    return monkeypatch, make_popen, captured


def test_remote_ssh_success_parses_metrics_and_builds_command(patched_ssh):
    monkeypatch, make_popen, captured = patched_ssh
    monkeypatch.setattr(remote_ssh.subprocess, "Popen", make_popen('noise\n{"combined_score": 0.7}\n'))
    b = RemoteSSHBackend(host="h", user="u")
    m = b.evaluate(Candidate("r0", {"x": 1.0}, program="src"), _Remote())
    assert m == {"combined_score": 0.7}
    cmd = captured["cmd"]
    assert "ruthless.backends.remote_worker" in cmd
    assert "my_pkg.obj:train_and_evaluate" in cmd and " 9 13 " in cmd  # epochs/seed from objective
    assert "--program program.py" in cmd


def test_remote_ssh_timeout_raises_transient(patched_ssh):
    monkeypatch, make_popen, _ = patched_ssh
    monkeypatch.setattr(remote_ssh.subprocess, "Popen", make_popen("", timeout=True))
    b = RemoteSSHBackend(host="h", user="u")
    with pytest.raises(TransientEvaluationError):
        b.evaluate(Candidate("r0", {"x": 1.0}), _Remote())


def test_remote_ssh_nonzero_exit_raises_transient(patched_ssh):
    monkeypatch, make_popen, _ = patched_ssh
    monkeypatch.setattr(remote_ssh.subprocess, "Popen", make_popen("", returncode=1))
    b = RemoteSSHBackend(host="h", user="u")
    with pytest.raises(TransientEvaluationError):
        b.evaluate(Candidate("r0", {"x": 1.0}), _Remote())


def test_remote_ssh_objective_marker_raises_fatal(patched_ssh):
    monkeypatch, make_popen, _ = patched_ssh
    monkeypatch.setattr(
        remote_ssh.subprocess, "Popen", make_popen('{"combined_score": 0.0, "error": 1, "_error_text": "tb"}\n')
    )
    b = RemoteSSHBackend(host="h", user="u")
    with pytest.raises(FatalEvaluationError):  # node-side objective crash -> Fatal, not a returned score
        b.evaluate(Candidate("r0", {"x": 1.0}), _Remote())


def test_remote_ssh_rejects_plain_objective(patched_ssh):
    monkeypatch, make_popen, _ = patched_ssh
    monkeypatch.setattr(remote_ssh.subprocess, "Popen", make_popen("{}"))

    class _Plain:
        def evaluate(self, candidate):
            return {}

    b = RemoteSSHBackend(host="h", user="u")
    with pytest.raises(FatalEvaluationError):
        b.evaluate(Candidate("r0", {"x": 1.0}), _Plain())
