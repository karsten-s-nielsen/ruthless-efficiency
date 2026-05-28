"""Direction + the SearchStrategy port. Each strategy OWNS its loop (spec C1): it drives the search
and returns a Result. Core imposes no template-method driver; persistence/resume is strategy-internal
(spec H1/C3). report.py renders the returned Result."""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from ruthless.backend import ComputeBackend
from ruthless.objective import Objective
from ruthless.result import Result


class Direction(str, Enum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


@runtime_checkable
class SearchStrategy(Protocol):
    def run(self, objective: Objective, *, backend: ComputeBackend) -> Result: ...
