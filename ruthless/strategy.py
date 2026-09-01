"""Direction + the SearchStrategy port. Each strategy OWNS its loop (spec C1): it drives the search
and returns a Result. Core imposes no template-method driver; persistence/resume is strategy-internal
(spec H1/C3). report.py renders the returned Result."""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from ruthless.backend import ComputeBackend
from ruthless.objective import Objective
from ruthless.result import ProgressEvent, Result


class Direction(str, Enum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


@runtime_checkable
class SearchStrategy(Protocol):
    def run(self, objective: Objective, *, backend: ComputeBackend) -> Result: ...


class Observer(Protocol):
    """A per-candidate progress sink handed to a strategy's ``run``. Called once per completed
    evaluation, in evaluation order, with a :class:`~ruthless.result.ProgressEvent`. ``event`` is
    POSITIONAL-ONLY (the ``/``) so ANY one-argument callable conforms regardless of its own parameter
    name — a function, a ``lambda``, or a bound method such as ``list.append``. Dropping the ``/`` would
    silently break that: under pyright basic a protocol whose parameter is named ``event`` is only
    satisfied by callables whose own parameter is named ``event`` (so ``list.append`` and
    ``lambda e: ...`` would stop conforming). Implementations MUST NOT assume they see every candidate a
    run produced — on a resumed study they observe only the candidates evaluated in that call (see
    ``OptunaStrategy.run``). An Observer that raises must not be able to abort the search: the strategy
    isolates it (logs and continues).

    Intentionally NOT ``runtime_checkable``: an Observer is never isinstance-guarded, and a
    ``__call__``-only runtime check would be true for any callable — a misleading guard."""

    def __call__(self, event: ProgressEvent, /) -> None: ...
