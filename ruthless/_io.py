"""Tiny filesystem helper shared across the core, strategies, and backends.

`program_to_path` gives every caller a UNIFORM `program_path` contract — a filesystem path to a
`.py` file holding `Candidate.program`, or `None` when there is none — so no caller ever passes raw
source around. It lives in the pure core (stdlib-only) so both `ruthless.backends` and
`ruthless.strategies` can reuse it without crossing the one-way dependency boundary (strategies must
not import backends)."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

from ruthless.result import Candidate


@contextmanager
def program_to_path(candidate: Candidate) -> Iterator[str | None]:
    """Yield a temp `.py` path holding `candidate.program`, or `None` if there is none.

    The temp file is removed on exit (best-effort). Callers get a path-or-None they can hand to a
    `train_and_evaluate(..., program_path=...)` entrypoint without branching on raw source."""
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
