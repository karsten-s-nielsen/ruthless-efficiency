"""Helpers shared by the compute backends ([backends] extra). The ComputeBackend port lives in
ruthless.backend (1A, core); backends import it from there. These helpers replace the lakehouse
fail_metrics() swallowing with the 1A error taxonomy (raise Fatal/Transient, never record a sentinel)."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

from ruthless.errors import FatalEvaluationError
from ruthless.remote import RemoteObjective
from ruthless.result import Candidate

# The marker a remote worker emits when the OBJECTIVE crashed on the node (vs. a transport failure).
# Backends convert this into a raise (H1) rather than returning it as a score.
_OBJECTIVE_FAILURE_KEYS = ("_error_text",)


def is_objective_failure(metrics: dict) -> bool:
    """True if a parsed worker metrics dict is actually a node-side objective-failure marker (H1)."""
    return metrics.get("error") == 1 or any(k in metrics for k in _OBJECTIVE_FAILURE_KEYS)


@contextmanager
def program_to_path(candidate: Candidate) -> Iterator[str | None]:
    """Yield a temp `.py` path holding candidate.program, or None if there is none.

    Gives every backend a UNIFORM `program_path` contract: a filesystem path or None, never raw
    source. The temp file is removed on exit."""
    if candidate.program is None:
        yield None
        return
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(candidate.program)
        path = tmp.name
    try:
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def parse_last_json_line(stdout: str) -> dict[str, float]:
    """Return the last non-empty line of `stdout` parsed as a JSON metrics dict.

    Mirrors the lakehouse remote backends: the worker prints exactly one JSON line; earlier lines
    may be stray warnings. Raises FatalEvaluationError if no JSON object line is present."""
    for line in reversed([ln.strip() for ln in stdout.splitlines() if ln.strip()]):
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
