"""Standing Optuna gate (spec C3): resumable study — no lost/duplicate trials + converges. NOT
trajectory-identity (Optuna does not persist sampler RNG)."""

from ruthless.backend import InProcessBackend
from ruthless.config import OptunaConfig
from ruthless.result import Candidate
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
            "store": {"kind": "sqlite", "path": path},
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


def test_observer_resume_with_no_remaining_trials_fires_zero_events(tmp_path):
    db = str(tmp_path / "done.db")
    OptunaStrategy(_cfg(3, db), seed=123).run(_Bowl(), backend=InProcessBackend())  # fill to n_trials
    events: list = []
    r = OptunaStrategy(_cfg(3, db), seed=123).run(_Bowl(), backend=InProcessBackend(), observer=events.append)
    assert events == []  # remaining == 0 → study.optimize not called → no events
    assert len(r.history) == 3  # Result is still reconstructed from the store
