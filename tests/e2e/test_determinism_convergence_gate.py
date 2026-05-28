"""Standing CI gate (spec §8): deterministic + convergent, zero domain/strategy-extra deps."""

from ruthless.backend import InProcessBackend
from ruthless.config import RuthlessConfig
from ruthless.report import render_json
from ruthless.result import Candidate
from ruthless.strategies.random_.strategy import RandomSearchStrategy


class _Bowl:
    def evaluate(self, candidate: Candidate):
        x, y = candidate.params["x"], candidate.params["y"]
        return {"loss": (x - 2.0) ** 2 + (y + 1.0) ** 2}


def _cfg():
    return RuthlessConfig.model_validate(
        {
            "seed": 123,
            "strategy": {
                "kind": "random",
                "metric": "loss",
                "direction": "minimize",
                "n_trials": 500,
                "param_space": {
                    "x": {"kind": "float", "lo": -10.0, "hi": 10.0},
                    "y": {"kind": "float", "lo": -10.0, "hi": 10.0},
                },
            },
        }
    )


def test_converges_and_is_reproducible():
    cfg = _cfg()
    r1 = RandomSearchStrategy(cfg.strategy, seed=cfg.seed).run(_Bowl(), backend=InProcessBackend())
    r2 = RandomSearchStrategy(cfg.strategy, seed=cfg.seed).run(_Bowl(), backend=InProcessBackend())

    # Convergence toward the analytic optimum (2, -1). Thresholds are deliberately loose: pure random
    # search over a 20x20 box gives an expected best-of-500 loss of ~0.25 with high variance (seed=123
    # on numpy 2.2.6 yields ~0.44), and numpy does not guarantee identical Generator streams across
    # versions (cf. H-D + the numpy<3 pin). loss<2.0 (vs a uniform-random expectation of ~70) proves
    # the orchestration converges, while staying robust to seed/numpy drift.
    assert r1.best is not None
    assert r1.best.metrics["loss"] < 2.0
    assert abs(r1.best.candidate.params["x"] - 2.0) < 1.5
    assert abs(r1.best.candidate.params["y"] + 1.0) < 1.5

    # Reproducibility under fixed seed (within a numpy version) — the exact-match part of the gate.
    assert render_json(r1) == render_json(r2)
