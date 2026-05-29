"""HFJobsBackend — runs an objective's remote entrypoint on Hugging Face Jobs.

Ported from the lakehouse backend, bridged to the 1A port. Submits a PEP-723 UV worker script via
`huggingface_hub.run_uv_job`, polls until completion, and parses the JSON metrics line from the job
logs. The `shared.wheel` lakehouse coupling is SEVERED: the worker's install spec is the injected
`RemoteRef.package` and the import target is `RemoteRef.entrypoint` (no `evolve.targets.<target>`).

Per the unified error model it RAISES rather than recording a sentinel: timeout -> cancel +
TransientEvaluationError; job ERROR/CANCELED/DELETED -> FatalEvaluationError; no metrics line or a
node-side objective-failure marker -> FatalEvaluationError."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from ruthless._logging import get_logger
from ruthless.backends.base import is_objective_failure, parse_last_json_line, require_remote
from ruthless.errors import FatalEvaluationError, TransientEvaluationError
from ruthless.objective import Objective
from ruthless.remote import RemoteObjective, RemoteRef
from ruthless.result import Candidate, Metrics
from ruthless.wire import ERROR_TEXT_KEY, ERROR_TEXT_SURFACE_LIMIT

_log = get_logger("backends.hf_jobs")
_POLL_INTERVAL = 15  # seconds


def _build_worker_script(ref: RemoteRef) -> str:
    """Build the PEP-723 UV worker script, interpolating the injected install spec + entrypoint.

    Replaces the lakehouse module-level f-string that baked in `shared.wheel.WHEEL_BASE_URL`. The
    failure-marker keys emitted below (`combined_score`/`error`/`_error_text`) are the cross-wire
    contract defined in `ruthless.wire`; they are written as literals here because this script runs as
    a self-contained worker on a fresh node — keep them in sync with `ruthless.wire`."""
    if ref.package is None:
        raise FatalEvaluationError(
            "HFJobsBackend requires RemoteRef.package (the node is fresh; it must install something)"
        )
    return f'''\
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "{ref.package}",
# ]
# ///
"""HF Jobs worker — generic ruthless remote entrypoint runner."""

import base64
import importlib
import json
import logging
import os
import sys

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(message)s")
_log = logging.getLogger("hf_jobs_worker")


def main() -> None:
    config_b64 = os.environ.get("EVOLVE_CANDIDATE_CONFIG", "")
    if not config_b64:
        print(json.dumps({{"combined_score": 0.0, "error": 1.0, "_error_text": "missing EVOLVE_CANDIDATE_CONFIG"}}))
        sys.exit(0)

    candidate_config = json.loads(base64.b64decode(config_b64).decode())
    device = os.environ.get("EVOLVE_DEVICE", "cuda:0")
    epochs = int(os.environ.get("EVOLVE_EPOCHS", "5"))
    seed = int(os.environ.get("EVOLVE_SEED", "42"))
    entrypoint = os.environ["EVOLVE_ENTRYPOINT"]

    program_path = None
    program_b64 = os.environ.get("EVOLVE_PROGRAM")
    if program_b64:
        program_path = "/tmp/ruthless_program.py"
        with open(program_path, "w") as fh:
            fh.write(base64.b64decode(program_b64).decode())

    module_path, _, attr = entrypoint.partition(":")
    fn = getattr(importlib.import_module(module_path), attr)
    try:
        metrics = fn(
            candidate_config=candidate_config, device=device, epochs=epochs, seed=seed, program_path=program_path
        )
    except Exception:
        import traceback
        metrics = {{"combined_score": 0.0, "error": 1.0, "_error_text": traceback.format_exc()}}

    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
'''


class HFJobsBackend:
    """Runs an objective's remote entrypoint on Hugging Face Jobs (the ``[backends]`` extra).

    Submits a PEP-723 UV worker script via ``huggingface_hub.run_uv_job``, polls to completion, and
    parses the JSON metrics line from the job logs. The worker installs ``RemoteRef.package`` and
    imports ``RemoteRef.entrypoint``. Enforces ``timeout`` (cancel + ``TransientEvaluationError``);
    a job ERROR/CANCELED/DELETED or a node-side objective-failure marker → ``FatalEvaluationError``.

    Args:
        hf_flavor: HF Jobs hardware flavor (e.g. ``"l40sx1"``).
        timeout: Per-candidate timeout in seconds (also the job submission timeout).
        namespace: HF namespace to run the job under (defaults to the token owner).
    """

    def __init__(self, hf_flavor: str = "l40sx1", timeout: int = 6000, namespace: str | None = None) -> None:
        self._hf_flavor = hf_flavor
        self._timeout = timeout
        self._namespace = namespace
        # The worker script depends only on ref.package, which is constant across a run's candidates;
        # cache it so we don't re-template the multi-KB f-string on every evaluation.
        self._worker_script_cache: dict[str | None, str] = {}

    def _worker_script(self, ref: RemoteRef) -> str:
        if ref.package not in self._worker_script_cache:
            self._worker_script_cache[ref.package] = _build_worker_script(ref)
        return self._worker_script_cache[ref.package]

    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics:
        obj = require_remote(objective, backend="HFJobsBackend")
        # objective-crash markers and job failures raise (below); transport/submission errors -> Transient.
        try:
            return self._evaluate_impl(candidate, obj, obj.remote_ref)
        except (FatalEvaluationError, TransientEvaluationError):
            raise
        except Exception as exc:  # submission / API / network -> transient
            raise TransientEvaluationError(f"HF Jobs submission/poll error: {exc}") from exc

    def _evaluate_impl(self, candidate: Candidate, objective: RemoteObjective, ref: RemoteRef) -> Metrics:
        from huggingface_hub import HfApi

        api = HfApi()
        script = self._worker_script(ref)

        env: dict[str, str] = {
            "EVOLVE_CANDIDATE_CONFIG": base64.b64encode(json.dumps(dict(candidate.params)).encode()).decode(),
            "EVOLVE_DEVICE": "cuda:0",
            "EVOLVE_EPOCHS": str(objective.epochs),
            "EVOLVE_SEED": str(objective.seed),
            "EVOLVE_ENTRYPOINT": ref.entrypoint,
        }
        if candidate.program is not None:
            env["EVOLVE_PROGRAM"] = base64.b64encode(candidate.program.encode()).decode()

        # The worker script only needs to exist on disk during submission (run_uv_job reads + uploads
        # it); the temp dir is cleaned up before polling so it does not accumulate one dir per trial.
        with tempfile.TemporaryDirectory(prefix="ruthless_hfjob_") as tmp_dir:
            script_file = Path(tmp_dir) / "worker.py"
            script_file.write_text(script, encoding="utf-8")
            job_info = api.run_uv_job(
                script=str(script_file),
                env=env,
                secrets={"HF_TOKEN": self._get_hf_token()},
                flavor=self._hf_flavor,
                timeout=f"{self._timeout}s",
                namespace=self._namespace,
            )
        _log.info("hf_job_submitted", extra={"job_id": job_info.id, "flavor": self._hf_flavor})
        return self._poll_job(api, job_info.id)

    @staticmethod
    def _get_hf_token() -> str:
        from huggingface_hub import get_token

        return get_token() or ""

    def _poll_job(self, api: Any, job_id: str) -> Metrics:
        from huggingface_hub._jobs_api import JobStage

        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            info = api.inspect_job(job_id=job_id, namespace=self._namespace)
            stage = info.status.stage
            if stage == JobStage.COMPLETED:
                return self._parse_metrics(api, job_id, candidate_id=job_id)
            if stage in (JobStage.ERROR, JobStage.CANCELED, JobStage.DELETED):
                msg = info.status.message or "unknown"
                raise FatalEvaluationError(f"HF Job {job_id} failed: stage={stage.value}, message={msg}")
            time.sleep(_POLL_INTERVAL)

        try:
            api.cancel_job(job_id=job_id, namespace=self._namespace)
        except Exception:  # noqa: BLE001 - best-effort cancel; the timeout is reported regardless
            _log.warning("cancel_failed", extra={"job_id": job_id})
        raise TransientEvaluationError(f"HF Job {job_id} timed out after {self._timeout}s")

    def _parse_metrics(self, api: Any, job_id: str, *, candidate_id: str) -> Metrics:
        logs = "\n".join(api.fetch_job_logs(job_id=job_id, namespace=self._namespace))
        metrics = parse_last_json_line(logs)
        if is_objective_failure(metrics):
            detail = str(metrics.get(ERROR_TEXT_KEY, ""))[:ERROR_TEXT_SURFACE_LIMIT]
            raise FatalEvaluationError(f"objective crashed in HF Job {job_id}: {detail}")
        return metrics

    def available(self) -> bool:
        if not os.environ.get("HF_TOKEN"):
            return False
        try:
            from huggingface_hub import HfApi

            HfApi().whoami()
            return True
        except Exception:  # noqa: BLE001 - availability probe: any failure means "not available"
            _log.warning("hf_unavailable")
            return False
