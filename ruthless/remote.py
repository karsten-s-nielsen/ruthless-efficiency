"""Remote resolvability for the single ComputeBackend port (Plan 1B).

The 1A port `ComputeBackend.evaluate(candidate, objective, *, timeout)` assumed a backend can call
`objective.evaluate(candidate)` locally. Remote SSH/HF-Jobs backends cannot ship an arbitrary
Objective over the wire, so remote-ness is an explicit OPT-IN property: a RemoteObjective carries a
RemoteRef (install spec + import entrypoint) that compute backends use to resolve and run the
objective on a compute node. This replaces the lakehouse `shared.wheel` import + the
`evolve.targets.<target>` convention with injected config (never an import)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ruthless.result import Candidate, Metrics


@dataclass(frozen=True)
class RemoteRef:
    """How a compute backend resolves and runs a consumer Objective on a compute node.

    The resolved callable is the standard remote entrypoint, always invoked with KEYWORD arguments
    (so a positional-or-keyword def is fine):

        train_and_evaluate(candidate_config: dict, device: str, epochs: int,
                           seed: int, program_path: str | None) -> dict[str, float]

    `program_path` is ALWAYS a filesystem path to a `.py` file, or None (never raw source) — every
    caller (in-process, local_cuda, remote worker) writes Candidate.program to a temp file first.
    """

    entrypoint: str  # "package.module:callable" the node imports & invokes
    package: str | None = None  # PEP-723 dependency spec the node installs, e.g.
    #   "my-pkg[train] @ https://.../my_pkg-1.0-py3-none-any.whl".
    #   None when the node already has the package on PYTHONPATH (SSH case).


@runtime_checkable
class RemoteObjective(Protocol):
    """An Objective (1A port) that is ALSO resolvable on a compute node.

    The remote entrypoint (`remote_ref.entrypoint` -> `train_and_evaluate`) is the SINGLE execution
    path, reached two ways: InProcessBackend calls `objective.evaluate(candidate)`, a thin LOCAL
    invocation of that same entrypoint at a default device (a real in-process fallback, NOT dead
    code); compute backends ([backends]) invoke the entrypoint directly (local_cuda in-process at the
    backend's device; ssh/hf on the node). A compute backend handed a non-RemoteObjective raises
    FatalEvaluationError.

    `epochs`/`seed` ride on the objective because the port hands a backend only `(candidate,
    objective)` — they are run knobs, not candidate knobs, so the objective is their per-run carrier.
    Their single source of truth is `EvolveConfig.evaluation`; EvolveStrategy sets/threads them from
    config — a consumer must not hand-sync them. `device` is the backend's (asymmetry by design:
    where-to-run is the compute resource's property, not the objective's)."""

    def evaluate(self, candidate: Candidate) -> Metrics: ...  # 1A port; local entrypoint at default device

    @property
    def remote_ref(self) -> RemoteRef: ...

    @property
    def epochs(self) -> int: ...

    @property
    def seed(self) -> int: ...
