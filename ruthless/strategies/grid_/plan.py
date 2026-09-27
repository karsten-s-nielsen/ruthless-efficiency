"""Pure, deterministic grid enumeration. Zero-dependency; imports only core. De-duplicates on
`fingerprint(params)` (the same identity the resume store keys on), preserving first occurrence."""

from __future__ import annotations

import itertools
from typing import Any

from ruthless._fingerprint import fingerprint
from ruthless.config import GridConfig
from ruthless.config.space import levels


def enumerate_points(cfg: GridConfig) -> list[dict[str, Any]]:
    if cfg.design == "cartesian":
        names = list(cfg.param_space)
        raw = [
            dict(zip(names, combo, strict=True))
            for combo in itertools.product(*(levels(cfg.param_space[n]) for n in names))
        ]
    elif cfg.design == "one_at_a_time":
        base = dict(cfg.baseline or {})
        raw = [dict(base)]
        for name in cfg.param_space:
            for lvl in levels(cfg.param_space[name]):
                if not (type(lvl) is type(base[name]) and lvl == base[name]):  # type-strict "other level"
                    raw.append({**base, name: lvl})
    else:  # points
        raw = [dict(pt) for pt in (cfg.points or [])]

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for params in raw:
        fp = fingerprint(params)  # order-insensitive, value-distinguishing (spec §0.1)
        if fp not in seen:
            seen.add(fp)
            out.append(params)
    return out
