"""LocalCudaBackend — runs the objective's remote entrypoint IN-PROCESS on a local CUDA device.
Bridged to the 1A port: resolves objective.remote_ref.entrypoint (module:callable) and calls the
standard train_and_evaluate(candidate_config, device, epochs, seed, program_path)."""

from __future__ import annotations

import importlib

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
    def __init__(self, device: str = "cuda:0") -> None:
        self._device = device
        self._available_cached: bool | None = None

    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics:
        obj = require_remote(objective, backend="LocalCudaBackend")
        fn = _resolve(obj.remote_ref.entrypoint)
        with program_to_path(candidate) as program_path:  # uniform: temp .py path or None
            try:
                return fn(
                    candidate_config=candidate.params,
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
        if self._available_cached is None:
            try:
                import torch  # type: ignore[import-not-found]  # consumer dependency; not a ruthless dep

                self._available_cached = bool(torch.cuda.is_available())
            except ImportError:
                self._available_cached = False
        return self._available_cached
