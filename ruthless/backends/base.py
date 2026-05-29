"""Helpers shared by the compute backends ([backends] extra). The ComputeBackend port lives in
ruthless.backend (1A, core); backends import it from there. These helpers replace the lakehouse
fail_metrics() swallowing with the 1A error taxonomy (raise Fatal/Transient, never record a sentinel).

`program_to_path` and the cross-wire failure-marker vocabulary live in the core (`ruthless._io`,
`ruthless.wire`) so strategies can reuse them without importing backends; they are re-exported here
for the backends that already import them from this module."""

from __future__ import annotations

import json

from ruthless._io import program_to_path
from ruthless.errors import FatalEvaluationError
from ruthless.remote import RemoteObjective
from ruthless.wire import is_failure_marker

__all__ = ["is_objective_failure", "parse_last_json_line", "program_to_path", "require_remote"]


def is_objective_failure(metrics: dict) -> bool:
    """True if a parsed worker metrics dict is actually a node-side objective-failure marker (H1).

    Thin alias over `ruthless.wire.is_failure_marker` (the single definition of the marker shape)."""
    return is_failure_marker(metrics)


def parse_last_json_line(stdout: str) -> dict[str, float]:
    """Return the last non-empty line of `stdout` parsed as a JSON metrics dict.

    Mirrors the lakehouse remote backends: the worker prints exactly one JSON line; earlier lines
    may be stray warnings. Raises FatalEvaluationError if no JSON object line is present. Scans from
    the end without materialising an intermediate filtered list."""
    for raw_line in reversed(stdout.splitlines()):
        line = raw_line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise FatalEvaluationError(f"no JSON metrics line in worker stdout (last 200 chars): {stdout[-200:]!r}")


def require_remote(objective: object, *, backend: str) -> RemoteObjective:
    """Return the objective narrowed to RemoteObjective, or raise FatalEvaluationError if it is not one.

    Compute backends cannot ship an arbitrary in-process Objective to a node — the objective must opt
    in to remote execution by exposing `remote_ref` (and `epochs`/`seed`). Returning the narrowed
    objective lets callers read `.remote_ref`/`.epochs`/`.seed` without a separate isinstance assert."""
    if not isinstance(objective, RemoteObjective):
        raise FatalEvaluationError(
            f"{backend} requires a RemoteObjective (with .remote_ref/.epochs/.seed); "
            f"got {type(objective).__name__}. Use InProcessBackend for non-remote objectives."
        )
    return objective
