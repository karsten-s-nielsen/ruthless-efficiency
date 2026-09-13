"""Acceptance gate for the general code-evolution mode (spec §7 #2): a function-body seed with no
`config` dict and an arbitrary function name runs end-to-end THROUGH ruthless (not OpenEvolve-direct) —
`_load_program` (config optional) -> `Candidate(program=source)` -> backend -> `objective.evaluate` ->
`program_to_path` -> the consumer entrypoint loads the evolved function from `program_path` -> metrics ->
`combined_score`. Trivial fitness ("evolve f(x) -> x*2, maximise f(3)") proves the plumbing."""

import importlib.util
import textwrap

from ruthless.config import EvolveConfig
from ruthless.strategies.evolve_.strategy import _build_evaluator, _remote_objective_from_config


def _train(*, candidate_config, device, epochs, seed, program_path):
    """Entrypoint (silly-kicks shape): load the evolved function from program_path, run it, score it."""
    spec = importlib.util.spec_from_file_location("_evolved_candidate", program_path)
    assert spec is not None and spec.loader is not None  # narrow ModuleSpec|None / Loader|None for pyright
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.f(3)  # seed evolves f(x) -> x * 2 ; f(3) == 6
    return {"score": float(value)}


class _InProcess:
    """Minimal backend: runs the objective in-process (mirrors InProcessBackend's contract)."""

    def evaluate(self, candidate, objective, *, timeout=None):
        return objective.evaluate(candidate)

    def available(self):
        return True


def _cfg(seed_dir):
    return EvolveConfig.model_validate(
        {
            "kind": "evolve",
            "fitness": {"primary": "score"},  # no weights -> combined_score == score
            "entrypoint": "tests.strategies.evolve.test_general_code_evolution:_train",
            "seed_programs_dir": str(seed_dir),
            "evaluation": {"epochs": 1, "seed": 0},
            "evolution": {"code_evolution": True},
            "allow_unvalidated_code": True,  # general scoring function, no lakehouse-shaped profile
        }
    )


def test_general_code_evolution_runs_through_ruthless(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    (seed_dir / "seed0.py").write_text(
        textwrap.dedent(
            """\
            # EVOLVE-BLOCK-START
            def f(x):
                return x * 2
            # EVOLVE-BLOCK-END
            """
        ),
        encoding="utf-8",
    )

    cfg = _cfg(seed_dir)
    objective = _remote_objective_from_config(cfg)
    evaluator = _build_evaluator(cfg, backend=_InProcess(), objective=objective)

    result = evaluator.evaluate(str(seed_dir / "seed0.py"))

    assert result.metrics["combined_score"] == 6.0  # f(3) == 6, no weights -> combined == score
    assert "error" not in result.metrics  # not the worst-score sentinel
