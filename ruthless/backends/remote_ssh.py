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
import time

from ruthless._logging import get_logger
from ruthless.backends.base import is_objective_failure, parse_last_json_line, program_to_path, require_remote
from ruthless.errors import FatalEvaluationError, TransientEvaluationError
from ruthless.objective import Objective
from ruthless.remote import RemoteObjective
from ruthless.result import Candidate, Metrics
from ruthless.wire import ERROR_TEXT_KEY, ERROR_TEXT_SURFACE_LIMIT

_log = get_logger("backends.remote_ssh")

# Timeout (seconds) for lightweight SSH commands (availability check, mkdir, scp).
_SSH_CMD_TIMEOUT = 30

# TTL (seconds) for the cached availability probe, so a tight polling loop does not fire one live SSH
# round-trip per call. Short enough that a node going down is noticed quickly; a stale "available"
# self-corrects via the pool's transient-retry contract on the next dispatch.
_AVAIL_TTL = 5.0

# Hardening applied to every ssh/scp invocation (CWE-295/CWE-322): BatchMode=yes fails fast instead
# of hanging on a password/passphrase prompt (the backend requires key-based auth), and
# StrictHostKeyChecking=accept-new pins a host key on first use and refuses a changed key thereafter
# (TOFU), so a silently swapped host key is rejected rather than blindly trusted.
_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]


class RemoteSSHBackend:
    """Runs an objective's remote entrypoint on a remote host over SSH (the ``[backends]`` extra).

    scps the candidate config (and optional program) to ``remote_dir`` and invokes
    ``ruthless.backends.remote_worker`` on the host via key-based SSH, enforcing ``timeout`` and the
    unified error model (transport failures → ``TransientEvaluationError``; a node-side objective
    crash → ``FatalEvaluationError``). All ssh/scp calls are hardened with ``BatchMode=yes`` and
    ``StrictHostKeyChecking=accept-new``.

    Args:
        host: Remote hostname (empty disables the backend — ``available()`` returns ``False``).
        user: SSH user (defaults to ``$USER``).
        remote_dir: Working directory on the host (created once per backend).
        python_path: Python interpreter on the host that has ``ruthless`` + the consumer package.
        timeout: Per-candidate evaluation timeout in seconds.
        device: Device string passed to the remote entrypoint (e.g. ``"cuda:0"``).
    """

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
        self._remote_dir_ensured = False  # mkdir -p is idempotent; run it once per backend, not per candidate
        self._avail_checked_at = 0.0  # monotonic time of the last availability probe (0 = never)
        self._avail_cached = False
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
            ["ssh", *_SSH_OPTS, self._ssh_target, remote_cmd],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=effective_timeout,
        )

    def _ensure_remote_dir(self) -> None:
        if self._remote_dir_ensured:
            return
        result = self._run_ssh(f"mkdir -p {self._remote_dir}", timeout=_SSH_CMD_TIMEOUT)
        if result.returncode != 0:
            _log.warning("remote_mkdir_failed", extra={"remote_dir": self._remote_dir, "stderr": result.stderr.strip()})
            return
        self._remote_dir_ensured = True

    def _kill_remote_workers(self) -> None:
        try:
            self._run_ssh("pkill -f 'ruthless.backends.remote_worker' 2>/dev/null; true", timeout=_SSH_CMD_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError):
            _log.warning("kill_remote_workers_failed", extra={"host": self._host})

    def _scp_to_remote(self, local_path: str, remote_filename: str) -> None:
        remote_dest = f"{self._ssh_target}:{self._remote_dir}/{remote_filename}"
        subprocess.run(  # noqa: S603
            ["scp", *_SSH_OPTS, local_path, remote_dest],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
            timeout=_SSH_CMD_TIMEOUT,
        )

    def _scp_secret(self, content: str, remote_filename: str) -> None:
        """scp a secret to the remote via a local mode-0600 temp file (NamedTemporaryFile is 0600)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".secret", delete=False) as tmp:
            tmp.write(content)
            local = tmp.name
        try:
            self._scp_to_remote(local, remote_filename)
        finally:
            os.unlink(local)

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
            json.dump(dict(candidate.params), tmp)
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
            hf_token_prefix = ""
            if local_hf_token:
                # Pass the token by FILE, not as an inline env prefix: an inline secret is visible in
                # the remote host's `ps`/shell history (CWE-214). scp it to a 0600 file, chmod before
                # use; the worker reads it once into HF_TOKEN and unlinks it. Only the (non-secret)
                # file path appears on the command line.
                self._scp_secret(local_hf_token, ".hf_token")
                hf_token_prefix = "chmod 600 .hf_token && HF_TOKEN_FILE=.hf_token "  # noqa: S105 - shell prefix, not a secret
            remote_cmd = (
                f"cd {self._remote_dir} && "
                f"{hf_token_prefix}PYTHONUNBUFFERED=1 stdbuf -oL -eL "
                f"{self._python_path} -m ruthless.backends.remote_worker "
                f"candidate.json {self._device} {objective.epochs} {objective.seed} {shlex.quote(entrypoint)}"
                f"{program_arg}"
            )
            proc = subprocess.Popen(  # noqa: S603
                ["ssh", *_SSH_OPTS, self._ssh_target, remote_cmd],  # noqa: S607
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
            detail = str(metrics.get(ERROR_TEXT_KEY, ""))[:ERROR_TEXT_SURFACE_LIMIT]
            raise FatalEvaluationError(f"objective crashed on {self._host} for {candidate.id}: {detail}")
        return metrics

    def available(self) -> bool:
        if not self._host:
            return False
        now = time.monotonic()
        if now - self._avail_checked_at < _AVAIL_TTL:
            return self._avail_cached  # debounce: skip the live probe within the TTL window
        try:
            result = self._run_ssh("echo OK", timeout=5)
            self._avail_cached = result.returncode == 0 and "OK" in result.stdout
        except (subprocess.TimeoutExpired, OSError):
            self._avail_cached = False
        self._avail_checked_at = now
        return self._avail_cached
