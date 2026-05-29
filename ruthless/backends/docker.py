"""DockerBackend — not-yet-implemented stub (ported from the lakehouse stub, bridged to the 1A port).
Under the unified error model a not-implemented backend is a fatal config error, never a silently
recorded sentinel score."""

from __future__ import annotations

from ruthless.errors import FatalEvaluationError
from ruthless.objective import Objective
from ruthless.result import Candidate, Metrics


class DockerBackend:
    def __init__(self, docker_image: str = "") -> None:
        self._docker_image = docker_image

    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics:
        raise FatalEvaluationError("DockerBackend is not implemented (Plan 1B stub); use local_cuda/remote_ssh/hf_jobs")

    def available(self) -> bool:
        return False
