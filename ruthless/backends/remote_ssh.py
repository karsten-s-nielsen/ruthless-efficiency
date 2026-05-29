"""RemoteSSHBackend — runs an objective's remote entrypoint on a remote host over SSH.

Ported from the lakehouse backend, bridged to the 1A ComputeBackend port. It scps the candidate
config (+ optional program file) to the remote, invokes `ruthless.backends.remote_worker` over SSH,
and parses the single JSON metrics line from stdout. Per the unified error model it RAISES rather
than recording a sentinel: transport failures (timeout, ssh/host, non-zero exit) -> TransientEvaluationError;
unparseable output or a node-side objective-failure marker -> FatalEvaluationError.

Requirements: SSH key-based auth (no passwords); the remote env has `ruthless` + the consumer
package on its PYTHONPATH (RemoteRef.package is informational for ssh — installs are the HF-Jobs path)."""

from __future__ import annotations

import atexit
import json
import os
import shlex
import subprocess
import tempfile
import threading

from ruthless._logging import get_logger
from ruthless.backends.base import is_objective_failure, parse_last_json_line, program_to_path, require_remote
from ruthless.errors import FatalEvaluationError, TransientEvaluationError
from ruthless.objective import Objective
from ruthless.remote import RemoteObjective
from ruthless.result import Candidate, Metrics

_log = get_logger("backends.remote_ssh")

# Timeout (seconds) for lightweight SSH commands (availability check, mkdir, scp).
_SSH_CMD_TIMEOUT = 30


class RemoteSSHBackend:
    def __init__(
        self,
        host: str = "",
        user: str = "",
        remote_dir: str = "",
        python_path: str = "",
        timeout: int = 900,
        device: str = "cuda:0",
    ) -> None:
        self._host = host
        self._user = user or os.environ.get("USER", "")
        self._remote_dir = remote_dir or "~/Development/evolve-workspace"
        self._python_path = python_path or "~/Development/evolve-env/bin/python"
        self._timeout = timeout
        self._device = device
        self._active_procs: set[subprocess.Popen[str]] = set()
        self._proc_lock = threading.Lock()
        atexit.register(self._cleanup_remote_procs)
        self._kill_remote_workers()

    @property
    def _ssh_target(self) -> str:
        return f"{self._user}@{self._host}"

    def _cleanup_remote_procs(self) -> None:
        with self._proc_lock:
            for proc in list(self._active_procs):
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            self._active_procs.clear()

    def _run_ssh(self, remote_cmd: str, *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        effective_timeout = timeout if timeout is not None else self._timeout
        return subprocess.run(  # noqa: S603
            ["ssh", self._ssh_target, remote_cmd],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=effective_timeout,
        )

    def _ensure_remote_dir(self) -> None:
        result = self._run_ssh(f"mkdir -p {self._remote_dir}", timeout=_SSH_CMD_TIMEOUT)
        if result.returncode != 0:
            _log.warning("remote_mkdir_failed", extra={"remote_dir": self._remote_dir, "stderr": result.stderr.strip()})

    def _kill_remote_workers(self) -> None:
        try:
            self._run_ssh("pkill -f 'ruthless.backends.remote_worker' 2>/dev/null; true", timeout=_SSH_CMD_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError):
            _log.warning("kill_remote_workers_failed", extra={"host": self._host})

    def _scp_to_remote(self, local_path: str, remote_filename: str) -> None:
        remote_dest = f"{self._ssh_target}:{self._remote_dir}/{remote_filename}"
        subprocess.run(  # noqa: S603
            ["scp", local_path, remote_dest],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
            timeout=_SSH_CMD_TIMEOUT,
        )

    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics:
        obj = require_remote(objective, backend="RemoteSSHBackend")
        effective_timeout = int(timeout) if timeout is not None else self._timeout
        try:
            return self._evaluate_impl(candidate, obj, obj.remote_ref.entrypoint, effective_timeout)
        except subprocess.TimeoutExpired as exc:
            self._kill_remote_workers()
            raise TransientEvaluationError(
                f"remote training timed out after {effective_timeout}s on {self._host}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise TransientEvaluationError(
                f"remote command failed on {self._host}: {(exc.stderr or '').strip()}"
            ) from exc
        except OSError as exc:
            raise TransientEvaluationError(f"OS/SSH error on {self._host}: {exc}") from exc

    def _evaluate_impl(
        self, candidate: Candidate, objective: RemoteObjective, entrypoint: str, effective_timeout: int
    ) -> Metrics:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(candidate.params, tmp)
            local_candidate_path = tmp.name
        try:
            self._ensure_remote_dir()
            self._scp_to_remote(local_candidate_path, "candidate.json")
        finally:
            os.unlink(local_candidate_path)

        with program_to_path(candidate) as program_path:
            remote_program = None
            if program_path is not None:
                remote_program = "program.py"
                self._scp_to_remote(program_path, remote_program)

            program_arg = f" --program {remote_program}" if remote_program else ""
            local_hf_token = os.environ.get("HF_TOKEN", "")
            hf_token_prefix = f"HF_TOKEN={shlex.quote(local_hf_token)} " if local_hf_token else ""
            remote_cmd = (
                f"cd {self._remote_dir} && "
                f"{hf_token_prefix}PYTHONUNBUFFERED=1 stdbuf -oL -eL "
                f"{self._python_path} -m ruthless.backends.remote_worker "
                f"candidate.json {self._device} {objective.epochs} {objective.seed} {shlex.quote(entrypoint)}"
                f"{program_arg}"
            )
            proc = subprocess.Popen(  # noqa: S603
                ["ssh", self._ssh_target, remote_cmd],  # noqa: S607
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with self._proc_lock:
                self._active_procs.add(proc)

            stderr_lines: list[str] = []

            def _stream_stderr() -> None:
                if proc.stderr is None:
                    return
                try:
                    for line in proc.stderr:
                        stripped = line.rstrip()
                        if stripped:
                            stderr_lines.append(stripped)
                            _log.info("remote_stderr", extra={"line": stripped})
                except ValueError:
                    pass

            stderr_thread = threading.Thread(target=_stream_stderr, daemon=True)
            stderr_thread.start()
            try:
                stdout, _ = proc.communicate(timeout=effective_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise
            finally:
                with self._proc_lock:
                    self._active_procs.discard(proc)
            stderr_thread.join(timeout=5)

        if proc.returncode != 0:
            raise TransientEvaluationError(
                f"remote worker exited {proc.returncode} on {self._host}: {chr(10).join(stderr_lines[-5:])}"
            )

        metrics = parse_last_json_line(stdout or "")
        if is_objective_failure(metrics):  # node-side objective crash -> Fatal (never a recorded score)
            detail = str(metrics.get("_error_text", ""))[:300]
            raise FatalEvaluationError(f"objective crashed on {self._host} for {candidate.id}: {detail}")
        return metrics

    def available(self) -> bool:
        if not self._host:
            return False
        try:
            result = self._run_ssh("echo OK", timeout=5)
            return result.returncode == 0 and "OK" in result.stdout
        except (subprocess.TimeoutExpired, OSError):
            return False
