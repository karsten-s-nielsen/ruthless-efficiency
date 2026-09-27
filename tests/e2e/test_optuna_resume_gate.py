"""Standing Optuna gate (spec C3): resumable study — no lost/duplicate trials + converges. NOT
trajectory-identity (Optuna does not persist sampler RNG)."""

import optuna
import pytest

from ruthless.backend import InProcessBackend
from ruthless.config import OptunaConfig
from ruthless.result import Candidate
from ruthless.strategies.optuna_ import adopt_legacy_store
from ruthless.strategies.optuna_.strategy import OptunaStrategy


class _Bowl:
    def evaluate(self, candidate: Candidate):
        x = candidate.params["x"]
        return {"loss": (x - 2.0) ** 2}


def _cfg(n, path):
    return OptunaConfig.model_validate(
        {
            "kind": "optuna",
            "metric": "loss",
            "direction": "minimize",
            "n_trials": n,
            "param_space": {"x": {"kind": "float", "lo": -10.0, "hi": 10.0}},
            "store": {"kind": "sqlite", "path": path, "objective_id": "resume-gate-obj"},
        }
    )


def test_resume_no_lost_or_duplicate_trials_and_converges(tmp_path):
    import optuna

    db = str(tmp_path / "study.db")
    # Run the first half, then "kill" (discard the strategy) and resume to the full count.
    r1 = OptunaStrategy(_cfg(20, db), seed=123).run(_Bowl(), backend=InProcessBackend())
    assert r1.diagnostics["n_trials"] == 20 and len(r1.history) == 20
    r2 = OptunaStrategy(_cfg(50, db), seed=123).run(_Bowl(), backend=InProcessBackend())
    # monotone growth, no lost/dup: the resumed study has exactly n_trials total.
    assert r2.diagnostics["n_trials"] == 50
    # best + history span the WHOLE store, not just the 30 trials this process ran.
    assert len(r2.history) == 50
    # trial ids are contiguous 0..49 (no lost, no duplicate).
    study = optuna.load_study(study_name=db, storage=f"sqlite:///{db}")
    assert sorted(t.number for t in study.trials) == list(range(50))
    # convergence within tolerance (NOT trajectory identity — Optuna RNG is not persisted).
    assert r2.best is not None and abs(r2.best.candidate.params["x"] - 2.0) < 0.5


def test_resume_with_warm_start_runs_exactly_n_trials_and_baseline_runs_once(tmp_path):
    import optuna

    db = str(tmp_path / "warm.db")
    cfg1 = _cfg(5, db).model_copy(update={"warm_start": {"x": 7.5}})
    cfg2 = _cfg(12, db).model_copy(update={"warm_start": {"x": 7.5}})
    # Fresh warm-started study runs exactly n_trials (baseline = trial 0).
    r1 = OptunaStrategy(cfg1, seed=7).run(_Bowl(), backend=InProcessBackend())
    assert r1.diagnostics["n_trials"] == 5 and len(r1.history) == 5
    assert r1.history[0].candidate.params["x"] == 7.5
    # Resume: baseline must NOT be re-enqueued (n_existing != 0), total stays exact.
    r2 = OptunaStrategy(cfg2, seed=7).run(_Bowl(), backend=InProcessBackend())
    assert r2.diagnostics["n_trials"] == 12 and len(r2.history) == 12
    study = optuna.load_study(study_name=db, storage=f"sqlite:///{db}")
    assert sorted(t.number for t in study.trials) == list(range(12))
    # the warm-start point appears exactly once across the whole store (not re-enqueued on resume).
    assert sum(1 for t in study.trials if t.params.get("x") == 7.5) == 1


def test_observer_resume_fires_only_new_continued_numbers(tmp_path):
    db = str(tmp_path / "obs.db")
    first: list = []
    OptunaStrategy(_cfg(2, db), seed=123).run(_Bowl(), backend=InProcessBackend(), observer=first.append)
    assert [e.number for e in first] == [0, 1]
    second: list = []
    OptunaStrategy(_cfg(4, db), seed=123).run(_Bowl(), backend=InProcessBackend(), observer=second.append)
    # the resumed run fires ONLY the two new trials, with CONTINUED store-global numbers — not 0,1
    assert [e.number for e in second] == [2, 3]


# --- store-identity guard + legacy adoption (0.7.0) ---


def _ocfg(path, *, objective_id="v1", **extra):
    base = {
        "kind": "optuna",
        "metric": "loss",
        "n_trials": 2,
        "sampler": "random",
        "param_space": {"x": {"kind": "float", "lo": 0.0, "hi": 1.0}},
        "store": {"kind": "sqlite", "path": path, "objective_id": objective_id},
    }
    base.update(extra)
    return OptunaConfig.model_validate(base)


class _OObj:
    def evaluate(self, candidate):
        return {"loss": float(candidate.params["x"])}


def test_optuna_matching_identity_resumes(tmp_path):
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())
    r = OptunaStrategy(_ocfg(p, n_trials=4)).run(_OObj(), backend=InProcessBackend())  # more budget OK
    assert len(r.history) >= 2


def test_optuna_ntrials_warmstart_change_ok(tmp_path):
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())
    OptunaStrategy(_ocfg(p, n_trials=3, warm_start={"x": 0.5})).run(_OObj(), backend=InProcessBackend())


def test_optuna_objective_id_mismatch_raises(tmp_path):
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p, objective_id="v1")).run(_OObj(), backend=InProcessBackend())
    with pytest.raises(ValueError, match="different objective"):
        OptunaStrategy(_ocfg(p, objective_id="v2")).run(_OObj(), backend=InProcessBackend())


def test_optuna_config_mismatch_raises(tmp_path):
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())
    changed = _ocfg(p, param_space={"x": {"kind": "float", "lo": 0.0, "hi": 2.0}})
    with pytest.raises(ValueError, match="different config"):
        OptunaStrategy(changed).run(_OObj(), backend=InProcessBackend())


@pytest.mark.parametrize(
    "bad",
    [
        {"schema": 99},
        "not-a-dict",
        {"schema": 1, "objective_id": "v1"},  # missing config_fingerprint
        {"schema": True, "objective_id": "v1", "config_fingerprint": "x"},  # bool is not a valid schema
        {"schema": 1.0, "objective_id": "v1", "config_fingerprint": "x"},  # float is not a valid schema
    ],
)
def test_optuna_malformed_identity_raises(tmp_path, bad):
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())
    study = optuna.load_study(study_name=p, storage=f"sqlite:///{p}")
    study.set_user_attr("ruthless_identity", bad)
    with pytest.raises(ValueError, match=r"corrupt|unrecognised"):
        OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())


def _legacy_study(path):
    study = optuna.create_study(study_name=path, storage=f"sqlite:///{path}", direction="minimize")
    study.optimize(lambda t: t.suggest_float("x", 0.0, 1.0), n_trials=1)  # >=1 trial, no ruthless_identity


def test_optuna_legacy_study_raises(tmp_path):
    p = str(tmp_path / "legacy.db")
    _legacy_study(p)
    with pytest.raises(ValueError, match="adopt_legacy_store"):
        OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())


def test_adopt_then_resume_succeeds(tmp_path):
    p = str(tmp_path / "legacy.db")
    _legacy_study(p)
    cfg = _ocfg(p)
    adopt_legacy_store(cfg)
    OptunaStrategy(cfg).run(_OObj(), backend=InProcessBackend())


def test_adopt_already_stamped_raises(tmp_path):
    p = str(tmp_path / "s.db")
    OptunaStrategy(_ocfg(p)).run(_OObj(), backend=InProcessBackend())  # stamps identity
    with pytest.raises(ValueError, match="already carries"):
        adopt_legacy_store(_ocfg(p))


def test_adopt_then_diff_objective_id_raises(tmp_path):
    p = str(tmp_path / "legacy.db")
    _legacy_study(p)
    adopt_legacy_store(_ocfg(p, objective_id="v1"))
    with pytest.raises(ValueError, match="different objective"):
        OptunaStrategy(_ocfg(p, objective_id="v2")).run(_OObj(), backend=InProcessBackend())


def test_adopt_then_diff_config_raises(tmp_path):
    p = str(tmp_path / "legacy.db")
    _legacy_study(p)
    adopt_legacy_store(_ocfg(p))
    changed = _ocfg(p, param_space={"x": {"kind": "float", "lo": 0.0, "hi": 2.0}})
    with pytest.raises(ValueError, match="different config"):
        OptunaStrategy(changed).run(_OObj(), backend=InProcessBackend())


def test_adopt_requires_store_and_study(tmp_path):
    with pytest.raises(ValueError):
        adopt_legacy_store(
            OptunaConfig.model_validate(
                {"kind": "optuna", "metric": "loss", "param_space": {"x": {"kind": "float", "lo": 0.0, "hi": 1.0}}}
            )
        )
    with pytest.raises(ValueError, match="no optuna study"):
        adopt_legacy_store(_ocfg(str(tmp_path / "nope.db")))


def test_observer_resume_with_no_remaining_trials_fires_zero_events(tmp_path):
    db = str(tmp_path / "done.db")
    OptunaStrategy(_cfg(3, db), seed=123).run(_Bowl(), backend=InProcessBackend())  # fill to n_trials
    events: list = []
    r = OptunaStrategy(_cfg(3, db), seed=123).run(_Bowl(), backend=InProcessBackend(), observer=events.append)
    assert events == []  # remaining == 0 → study.optimize not called → no events
    assert len(r.history) == 3  # Result is still reconstructed from the store
