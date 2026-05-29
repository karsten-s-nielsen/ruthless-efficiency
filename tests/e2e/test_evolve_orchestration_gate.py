"""Standing evolve orchestration gate (spec C-A): proves OUR orchestration is preserved without
reproducing OpenEvolve's stochastic loop. A deterministic fake loop drives a fixed set of candidate
programs through the REAL EvolveEvaluator (real AST sandbox + real BackendPool over fake in-process
backends). No GPU, no LLM, no network, no real openevolve loop."""

from __future__ import annotations

import textwrap

from ruthless.backends.pool import BackendPool
from ruthless.config import FitnessConfig
from ruthless.errors import TransientEvaluationError
from ruthless.remote import RemoteRef
from ruthless.strategies.evolve_.evaluator import EvolveEvaluator
from ruthless.strategies.evolve_.sandbox import ValidationProfile

_PROFILE = ValidationProfile(
    patch_method="_embed",
    patch_signature=["self", "x", "y"],
    return_shape="(batch, hidden_dim)",
    known_model_attrs=frozenset({"linear"}),
    allowed_namespaces=frozenset({"torch", "math"}),
    layers_args=["hidden_dim"],
    rejected_builtins=frozenset({"eval", "exec", "open", "__import__"}),
)


class _Objective:
    def evaluate(self, candidate):
        return {}

    @property
    def remote_ref(self):
        return RemoteRef(entrypoint="m:f")

    epochs = 1
    seed = 0


class _FastBackend:
    """Returns a score derived from the candidate config (so dispatch + metric flow is observable)."""

    def __init__(self):
        self.calls = 0

    def evaluate(self, candidate, objective, *, timeout=None):
        self.calls += 1
        return {"primary": float(candidate.params["hidden_dim"]) / 256.0}

    def available(self):
        return True


class _FlakyBackend:
    """Always raises Transient -> the pool must retry on the fast backend (pool contract)."""

    def __init__(self):
        self.calls = 0

    def evaluate(self, candidate, objective, *, timeout=None):
        self.calls += 1
        raise TransientEvaluationError("flaky node")

    def available(self):
        return True


def _program(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src), encoding="utf-8")
    return str(p)


def test_orchestration_gate(tmp_path):
    flaky, fast = _FlakyBackend(), _FastBackend()
    pool = BackendPool([flaky, fast], max_retries=2)  # flaky is priority 0 -> always retried onto fast
    evaluator = EvolveEvaluator(
        backend=pool,
        objective=_Objective(),
        fitness_config=FitnessConfig(primary="primary"),
        code_evolution=True,
        validation_profile=_PROFILE,
    )

    good_a = _program(tmp_path, "good_a.py", 'config = {"hidden_dim": 256}\n')
    good_b = _program(tmp_path, "good_b.py", 'config = {"hidden_dim": 512}\n')
    malicious = _program(
        tmp_path,
        "malicious.py",
        """\
        config = {"hidden_dim": 256}

        def custom_embed(self, x, y):
            import os
            return x
        """,
    )

    # Fake evolutionary loop: evaluate each candidate through the real orchestration, track the best.
    results = {path: evaluator.evaluate(path) for path in (good_a, good_b, malicious)}

    # (1) Sandbox verdict golden: the malicious candidate is rejected before any dispatch.
    mal = results[malicious]
    assert mal.metrics["combined_score"] == 0.0 and mal.metrics["error"] == 1.0
    assert mal.artifacts["failure_kind"] == "objective" and "validation_rejected" in str(mal.artifacts["error"])

    # (2) Valid candidates dispatch through the pool and their metrics flow back.
    assert results[good_a].metrics["combined_score"] == 1.0  # 256/256
    assert results[good_b].metrics["combined_score"] == 2.0  # 512/256

    # (3) Pool transient-retry contract: every valid eval hit flaky (pri 0) then succeeded on fast.
    assert fast.calls == 2 and flaky.calls == 2  # 2 valid candidates; each retried once

    # (4) Best-by-combined-score aggregation (what the strategy/loop would select).
    best_path = max((good_a, good_b), key=lambda p: results[p].metrics["combined_score"])
    assert best_path == good_b
