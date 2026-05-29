"""OptunaStrategy ([optuna] extra). Importing this module is dependency-light — `optuna` itself is
imported lazily inside `OptunaStrategy.run`, so the install is only required to actually run a study."""

from __future__ import annotations

from ruthless.strategies.optuna_.strategy import OptunaStrategy

__all__ = ["OptunaStrategy"]
