"""OptunaStrategy ([optuna] extra). Importing this module is dependency-light — `optuna` itself is
imported lazily inside `OptunaStrategy.run` and `adopt_legacy_store`, so the install is only required to
actually run/adopt a study."""

from __future__ import annotations

from ruthless.strategies.optuna_.strategy import OptunaStrategy, adopt_legacy_store

__all__ = ["OptunaStrategy", "adopt_legacy_store"]
