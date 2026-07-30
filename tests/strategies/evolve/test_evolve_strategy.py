import json
import types

import openevolve
import pytest

from ruthless.config import EvolveConfig
from ruthless.errors import FatalEvaluationError
from ruthless.strategies.evolve_ import strategy as strat
from ruthless.strategies.evolve_.strategy import (
    EvolveStrategy,
    _remote_objective_from_config,
    _resolve_hook,
    _translate_to_openevolve_config,
)
from ruthless.wire import worst_score_metrics


def _cfg(seed_dir, **over):
    base = {
        "kind": "evolve",
        "fitness": {"primary": "primary"},
        "entrypoint": "tests.strategies.evolve.test_evolve_strategy:_fake_train",
        "seed_programs_dir": str(seed_dir),
        "evaluation": {"epochs": 3, "seed": 7},
    }
    base.update(over)
    return EvolveConfig.model_validate(base)


def _fake_train(*, candidate_config, device, epochs, seed, program_path):  # entrypoint for the in-process objective
    return {"primary": 1.0}


class _FakeBackend:
    def evaluate(self, candidate, objective, *, timeout=None):
        return {"primary": 1.0}

    def available(self):
        return True


@pytest.fixture
def seed_dir(tmp_path):
    d = tmp_path / "seeds"
    d.mkdir()
    (d / "seed0.py").write_text('config = {"hidden_dim": 256}\n')
    return d


# ---- pure helpers (no openevolve) ----


def test_translate_maps_islands_iterations_llm():
    cfg = EvolveConfig.model_validate(
        {
            "kind": "evolve",
            "fitness": {"primary": "s"},
            "entrypoint": "m:f",
            "seed_programs_dir": "seeds",
            "evolution": {"iterations": 99, "num_islands": 5},
            "llm": {"models": [{"name": "g", "weight": 1.0, "api_base": "u", "api_key_env": "K"}]},
        }
    )
    oe = _translate_to_openevolve_config(cfg)
    assert oe["max_iterations"] == 99
    assert oe["database"]["num_islands"] == 5
    assert oe["llm"]["models"][0]["api_key"] == "${K}"


def test_remote_objective_from_config_matches_cfg(seed_dir):
    cfg = _cfg(seed_dir, remote_package="pkg @ url")
    obj = _remote_objective_from_config(cfg)
    assert obj.remote_ref.entrypoint == cfg.entrypoint
    assert obj.remote_ref.package == "pkg @ url"
    assert obj.epochs == 3 and obj.seed == 7  # from cfg.evaluation (canonical)


def test_resolve_hook_type_checks():
    with pytest.raises(FatalEvaluationError):
        _resolve_hook("os:getcwd", expect="ValidationProfile")  # resolves but wrong type


# ---- run() with a FAKE loop ----


def _patch_fake_loop(monkeypatch, best_code="def best():\n    return 1\n"):
    monkeypatch.setattr(openevolve, "Config", types.SimpleNamespace(from_dict=lambda d: d))
    monkeypatch.setattr(
        openevolve,
        "run_evolution",
        lambda **kw: types.SimpleNamespace(
            best_code=best_code, metrics={"primary": 0.95, "combined_score": 0.95}, best_score=0.95
        ),
    )


def test_run_returns_result_from_fake_loop(seed_dir, tmp_path, monkeypatch):
    _patch_fake_loop(monkeypatch)
    cfg = _cfg(seed_dir)
    strategy = EvolveStrategy(cfg, results_dir=tmp_path / "out")
    result = strategy.run(_remote_objective_from_config(cfg), backend=_FakeBackend())
    assert result.best is not None
    assert result.best.candidate.program == "def best():\n    return 1\n"
    assert result.best.metrics["combined_score"] == 0.95
    assert result.provenance["strategy"] == "evolve" and result.diagnostics["best_score"] == 0.95
    assert len(result.history) == 1  # one seed evaluated


def test_run_rejects_plain_objective(seed_dir, tmp_path, monkeypatch):
    _patch_fake_loop(monkeypatch)
    cfg = _cfg(seed_dir)

    class _Plain:
        def evaluate(self, candidate):
            return {}

    with pytest.raises(FatalEvaluationError, match="requires a RemoteObjective"):
        EvolveStrategy(cfg, results_dir=tmp_path / "out").run(_Plain(), backend=_FakeBackend())


def test_run_rejects_objective_disagreeing_with_config(seed_dir, tmp_path, monkeypatch):
    _patch_fake_loop(monkeypatch)
    cfg = _cfg(seed_dir)
    mismatched = _remote_objective_from_config(_cfg(seed_dir, entrypoint="other.mod:fn"))
    with pytest.raises(FatalEvaluationError, match="disagrees with EvolveConfig"):
        EvolveStrategy(cfg, results_dir=tmp_path / "out").run(mismatched, backend=_FakeBackend())


def test_run_seed_cache_resume_skips_cached(seed_dir, tmp_path, monkeypatch):
    _patch_fake_loop(monkeypatch)
    cfg = _cfg(seed_dir)
    out = tmp_path / "out"
    # Pre-seed a cached result with the matching fingerprint for seed0.
    fp = strat._eval_fingerprint(cfg)
    (out / "seed_results").mkdir(parents=True)
    (out / "seed_results" / "seed0.json").write_text(
        json.dumps({"program": "seed0.py", "fingerprint": fp, "metrics": {"combined_score": 0.5, "primary": 0.5}})
    )

    calls = {"n": 0}

    class _CountingBackend(_FakeBackend):
        def evaluate(self, candidate, objective, *, timeout=None):
            calls["n"] += 1
            return {"primary": 1.0}

    strategy = EvolveStrategy(cfg, results_dir=out, resume=True)
    strategy.run(_remote_objective_from_config(cfg), backend=_CountingBackend())
    assert calls["n"] == 0  # the only seed was cached -> backend never called


# ---- seed-cache identity: declared exclusion scope (spec §3) ----


def test_eval_fingerprint_tracks_epochs_and_seed_but_not_timeout(seed_dir):
    """Pins evolve's DECLARED cache-identity scope (spec §3)."""
    base = strat._eval_fingerprint(_cfg(seed_dir))
    assert strat._eval_fingerprint(_cfg(seed_dir, evaluation={"epochs": 99, "seed": 7})) != base
    assert strat._eval_fingerprint(_cfg(seed_dir, evaluation={"epochs": 3, "seed": 99})) != base
    # timeout_seconds is an infra budget, not a determinant of a seed's metrics -> excluded.
    assert strat._eval_fingerprint(_cfg(seed_dir, evaluation={"epochs": 3, "seed": 7, "timeout_seconds": 1})) == base


def test_a_zero_score_seed_result_is_never_cache_readable(seed_dir, tmp_path):
    """Load-bearing for _SEED_CACHE_EXCLUDE's `timeout_seconds` entry (spec §3.2). A truncated run maps
    to the worst-score sentinel (combined_score=0), is WRITTEN to the seed-results dir like any other
    result (_eval_one writes unconditionally), and this read filter is the ONLY thing that stops it being
    reused. Relax it and the timeout exclusion becomes silently unsafe."""
    cfg = _cfg(seed_dir)
    fp = strat._eval_fingerprint(cfg)
    results_dir = tmp_path / "seed_results"
    results_dir.mkdir(parents=True)
    (results_dir / "seed0.json").write_text(
        json.dumps({"program": "seed0.py", "fingerprint": fp, "metrics": worst_score_metrics()})
    )
    cached = strat._load_cached_seeds(results_dir, [seed_dir / "seed0.py"], fp)
    assert cached == {}, "a combined_score=0 sentinel must never be readable from the seed cache"


def test_a_positive_score_seed_result_is_cache_readable(seed_dir, tmp_path):
    """The control for the test above: the filter rejects sentinels, not everything."""
    cfg = _cfg(seed_dir)
    fp = strat._eval_fingerprint(cfg)
    results_dir = tmp_path / "seed_results"
    results_dir.mkdir(parents=True)
    (results_dir / "seed0.json").write_text(
        json.dumps({"program": "seed0.py", "fingerprint": fp, "metrics": {"combined_score": 0.5}})
    )
    assert strat._load_cached_seeds(results_dir, [seed_dir / "seed0.py"], fp) == {"seed0": {"combined_score": 0.5}}
