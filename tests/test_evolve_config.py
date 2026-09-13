import pytest
from pydantic import ValidationError

from ruthless.config import (
    BackendConfig,
    EvolutionConfig,
    EvolveConfig,
    FitnessConfig,
    LLMConfig,
    LLMModelConfig,
    RandomConfig,
    RuthlessConfig,
)


def test_fitness_weights_must_sum_to_one():
    with pytest.raises(ValidationError, match="must sum to"):
        FitnessConfig(primary="a", combined_weights={"a": 0.5, "b": 0.2})


def test_fitness_primary_must_be_in_weights():
    with pytest.raises(ValidationError, match="primary"):
        FitnessConfig(primary="a", combined_weights={"b": 1.0})


def test_llm_weights_must_sum_to_one():
    with pytest.raises(ValidationError, match="must sum to"):
        LLMConfig(
            models=[
                LLMModelConfig(name="m1", weight=0.5, api_base="u", api_key_env="K1"),
                LLMModelConfig(name="m2", weight=0.2, api_base="u", api_key_env="K2"),
            ]
        )


def test_backend_unknown_type_rejected():
    with pytest.raises(ValidationError, match="Unknown backend type"):
        BackendConfig(type="no_such")


def test_evolution_code_evolution_default_false():
    assert EvolutionConfig().code_evolution is False


def test_loads_evolve_strategy_via_union():
    cfg = RuthlessConfig.model_validate(
        {
            "strategy": {
                "kind": "evolve",
                "fitness": {"primary": "combined_score"},
                "entrypoint": "my_pkg.obj:train_and_evaluate",
                "seed_programs_dir": "seeds",
            }
        }
    )
    assert isinstance(cfg.strategy, EvolveConfig)
    assert cfg.strategy.entrypoint == "my_pkg.obj:train_and_evaluate"
    assert cfg.strategy.evaluation.epochs == 5  # EvalConfig default; canonical source of truth


def test_random_strategy_still_loads_via_union():
    cfg = RuthlessConfig.model_validate({"strategy": {"kind": "random", "metric": "loss", "param_space": {}}})
    assert isinstance(cfg.strategy, RandomConfig)


def test_code_evolution_without_profile_or_optout_is_rejected():
    with pytest.raises(ValidationError, match="requires a validation_profile"):
        EvolveConfig.model_validate(
            {
                "kind": "evolve",
                "fitness": {"primary": "s"},
                "entrypoint": "m:f",
                "seed_programs_dir": "seeds",
                "evolution": {"code_evolution": True},
            }
        )


def test_code_evolution_optout_allows_no_profile():
    cfg = EvolveConfig.model_validate(
        {
            "kind": "evolve",
            "fitness": {"primary": "s"},
            "entrypoint": "m:f",
            "seed_programs_dir": "seeds",
            "evolution": {"code_evolution": True},
            "allow_unvalidated_code": True,
        }
    )
    assert cfg.allow_unvalidated_code is True
    assert cfg.validation_profile is None


def test_code_evolution_profile_still_satisfies_the_gate():
    cfg = EvolveConfig.model_validate(
        {
            "kind": "evolve",
            "fitness": {"primary": "s"},
            "entrypoint": "m:f",
            "seed_programs_dir": "seeds",
            "evolution": {"code_evolution": True},
            "validation_profile": "pkg.mod:PROFILE",
        }
    )
    assert cfg.allow_unvalidated_code is False and cfg.validation_profile == "pkg.mod:PROFILE"
