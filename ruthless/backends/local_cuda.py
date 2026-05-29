"""LocalCudaBackend — runs the objective's remote entrypoint IN-PROCESS on a local CUDA device.
Bridged to the 1A port: resolves objective.remote_ref.entrypoint (module:callable) and calls the
standard train_and_evaluate(candidate_config, device, epochs, seed, program_path)."""

from __future__ import annotations

import importlib
import threading

from ruthless.backends.base import program_to_path, require_remote
from ruthless.errors import FatalEvaluationError
from ruthless.objective import Objective
from ruthless.result import Candidate, Metrics


def _resolve(entrypoint: str):
    module_path, _, attr = entrypoint.partition(":")
    if not attr:
        raise FatalEvaluationError(f"remote_ref.entrypoint must be 'module:callable', got {entrypoint!r}")
    return getattr(importlib.import_module(module_path), attr)


class LocalCudaBackend:
    """Runs an objective's remote entrypoint IN-PROCESS on a local CUDA device.

    Resolves ``objective.remote_ref.entrypoint`` (``module:callable``) and invokes the standard
    ``train_and_evaluate(candidate_config, device, epochs, seed, program_path)`` at ``device``.

    Timeout: like :class:`~ruthless.backend.InProcessBackend`, this backend runs in-process and does
    NOT enforce the ``timeout`` argument — there is no in-process cancellation, so it is accepted for
    port compatibility and ignored. Only the cross-process backends (:class:`RemoteSSHBackend`,
    :class:`HFJobsBackend`) enforce a per-candidate timeout.

    Args:
        device: CUDA device string the entrypoint runs on (e.g. ``"cuda:0"``).
    """

    def __init__(self, device: str = "cuda:0") -> None:
        self._device = device
        self._available_cached: bool | None = None
        self._available_lock = threading.Lock()  # guards the lazy probe (safe on free-threaded builds)

    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics:
        # timeout is ignored in-process (no cancellation here); enforced only by the remote backends.
        obj = require_remote(objective, backend="LocalCudaBackend")
        fn = _resolve(obj.remote_ref.entrypoint)
        with program_to_path(candidate) as program_path:  # uniform: temp .py path or None
            try:
                return fn(
                    candidate_config=dict(candidate.params),  # consumers get a plain, mutable dict
                    device=self._device,
                    epochs=obj.epochs,
                    seed=obj.seed,
                    program_path=program_path,
                )
            except Exception as exc:  # H1: any objective crash -> Fatal (surfaced, never a recorded score)
                raise FatalEvaluationError(
                    f"objective entrypoint {obj.remote_ref.entrypoint!r} crashed on {candidate.id}: {exc}"
                ) from exc

    def available(self) -> bool:
        # Double-checked lazy probe: keep the heavy `torch` import deferred (don't import it at
        # construction just to memoise), but guard the one-time init so concurrent callers on a
        # free-threaded (no-GIL) build can't race on `_available_cached`.
        if self._available_cached is None:
            with self._available_lock:
                if self._available_cached is None:
                    try:
                        import torch  # type: ignore[import-not-found]  # consumer dependency; not a ruthless dep

                        self._available_cached = bool(torch.cuda.is_available())
                    except ImportError:
                        self._available_cached = False
        return self._available_cached
