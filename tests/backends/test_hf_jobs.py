import types

import pytest
from huggingface_hub._jobs_api import JobStage

from ruthless.backends import hf_jobs
from ruthless.backends.hf_jobs import HFJobsBackend, _build_worker_script
from ruthless.errors import FatalEvaluationError, TransientEvaluationError
from ruthless.remote import RemoteRef
from ruthless.result import Candidate


class _Remote:
    def __init__(self, package="my-pkg[train] @ https://h/x.whl"):
        self._ref = RemoteRef(entrypoint="my_pkg.obj:train_and_evaluate", package=package)

    def evaluate(self, candidate):
        return {"loss": 0.0}

    @property
    def remote_ref(self):
        return self._ref

    epochs = 3
    seed = 7


# ---- worker-script (shared.wheel sever) ----


def test_build_worker_script_severs_shared_wheel():
    s = _build_worker_script(RemoteRef(entrypoint="my_pkg.obj:train_and_evaluate", package="my-pkg @ https://h/x.whl"))
    assert "my-pkg @ https://h/x.whl" in s
    assert "EVOLVE_ENTRYPOINT" in s
    assert "shared" not in s and "luxury-lakehouse" not in s and "WHEEL_BASE_URL" not in s


def test_build_worker_script_requires_package():
    with pytest.raises(FatalEvaluationError):
        _build_worker_script(RemoteRef(entrypoint="m:f", package=None))


# ---- a fake HF API ----


def _status(stage, message=None):
    return types.SimpleNamespace(stage=stage, message=message)


class _FakeApi:
    def __init__(self, *, stages, logs):
        self._stages = list(stages)
        self._logs = logs
        self.cancelled = False
        self.submitted_env = None

    def run_uv_job(self, *, script, env, secrets, flavor, timeout, namespace):
        self.submitted_env = env
        return types.SimpleNamespace(id="job123")

    def inspect_job(self, *, job_id, namespace):
        stage = self._stages.pop(0) if len(self._stages) > 1 else self._stages[0]
        return types.SimpleNamespace(status=stage)

    def fetch_job_logs(self, *, job_id, namespace):
        return self._logs

    def cancel_job(self, *, job_id, namespace):
        self.cancelled = True


@pytest.fixture
def patch_time(monkeypatch):
    """monotonic returns an increasing counter; sleep is a no-op."""
    ticks = {"t": 0.0}

    def monotonic():
        ticks["t"] += 1.0
        return ticks["t"]

    monkeypatch.setattr(hf_jobs.time, "monotonic", monotonic)
    monkeypatch.setattr(hf_jobs.time, "sleep", lambda *_: None)


def _patch_api(monkeypatch, api):
    import sys

    monkeypatch.setattr(HFJobsBackend, "_get_hf_token", staticmethod(lambda: "tok"))
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(HfApi=lambda: api))


def test_hf_submits_and_parses(monkeypatch, patch_time):
    api = _FakeApi(stages=[_status(JobStage.COMPLETED)], logs=["noise", '{"combined_score": 0.9}'])
    _patch_api(monkeypatch, api)
    b = HFJobsBackend(timeout=100)
    m = b.evaluate(Candidate("r0", {"x": 2.0}, program="src"), _Remote())
    assert m == {"combined_score": 0.9}
    assert api.submitted_env is not None
    assert api.submitted_env["EVOLVE_EPOCHS"] == "3" and api.submitted_env["EVOLVE_SEED"] == "7"
    assert api.submitted_env["EVOLVE_ENTRYPOINT"] == "my_pkg.obj:train_and_evaluate"
    assert "EVOLVE_PROGRAM" in api.submitted_env


def test_hf_error_stage_raises_fatal(monkeypatch, patch_time):
    api = _FakeApi(stages=[_status(JobStage.ERROR, "boom")], logs=[])
    _patch_api(monkeypatch, api)
    with pytest.raises(FatalEvaluationError):
        HFJobsBackend(timeout=100).evaluate(Candidate("r0", {"x": 1.0}), _Remote())


def test_hf_timeout_cancels_and_raises_transient(monkeypatch, patch_time):
    api = _FakeApi(stages=[_status(JobStage.RUNNING)], logs=[])
    _patch_api(monkeypatch, api)
    with pytest.raises(TransientEvaluationError):
        HFJobsBackend(timeout=3).evaluate(Candidate("r0", {"x": 1.0}), _Remote())
    assert api.cancelled is True


def test_hf_objective_marker_raises_fatal(monkeypatch, patch_time):
    marker_log = '{"combined_score": 0.0, "error": 1, "_error_text": "tb"}'
    api = _FakeApi(stages=[_status(JobStage.COMPLETED)], logs=[marker_log])
    _patch_api(monkeypatch, api)
    with pytest.raises(FatalEvaluationError):
        HFJobsBackend(timeout=100).evaluate(Candidate("r0", {"x": 1.0}), _Remote())


def test_hf_rejects_plain_objective():
    class _Plain:
        def evaluate(self, candidate):
            return {}

    with pytest.raises(FatalEvaluationError):
        HFJobsBackend().evaluate(Candidate("r0", {"x": 1.0}), _Plain())
