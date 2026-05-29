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
