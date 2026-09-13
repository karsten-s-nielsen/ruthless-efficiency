"""EvolveStrategy — a thin SearchStrategy adapter over OpenEvolve. OpenEvolve owns the evolutionary
loop; we own the orchestration: config translation, seed evaluation + resume cache, the standalone
evaluator script the worker subprocess reconstructs, and Result mapping.

Single source of truth: EvolveConfig. The OpenEvolve ProcessPoolExecutor worker gets no live Python
objects, so it rebuilds a config-derived RemoteObjective + the evaluator from the serialised config
(`_remote_objective_from_config` + `_build_evaluator`, used by BOTH the in-process seed-eval path and
the worker — provably identical). epochs/seed come from `cfg.evaluation` (canonical); `run()` asserts
the passed objective agrees with the config before doing anything.

NOTE: this module does NOT import `ruthless.backends` (import-linter: strategies must not import
backends). It receives the backend via `run(objective, *, backend)`; the generated worker script
imports `create_backend` at runtime in the worker subprocess (not a static import here)."""

from __future__ import annotations

import concurrent.futures
import importlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from ruthless._fingerprint import fingerprint, fingerprint_model
from ruthless._io import program_to_path
from ruthless._logging import get_logger
from ruthless._provenance import code_identity
from ruthless.backend import ComputeBackend
from ruthless.config import EvolveConfig
from ruthless.errors import FatalEvaluationError
from ruthless.objective import Objective
from ruthless.remote import RemoteObjective, RemoteRef
from ruthless.result import Candidate, Evaluation, Metrics, Result
from ruthless.strategies.evolve_.evaluator import EvolveEvaluator
from ruthless.strategies.evolve_.sandbox import ValidationProfile

_log = get_logger("strategies.evolve")


# --------------------------------------------------------------------------- hooks + objective


@cache
def _resolve_hook(import_string: str, *, expect: str) -> Any:
    """Resolve a "module:attr" import-string (importlib + getattr; never eval) and type-check it.

    Mirrors the 1A CLI objective loader's trusted-config convention. Cached: resolution is pure for a
    given (import_string, expect), so the per-candidate evaluate() path resolves the entrypoint once
    rather than re-importing on every trial."""
    module_path, _, attr = import_string.partition(":")
    if not attr:
        raise FatalEvaluationError(f"hook import-string must be 'module:attr', got {import_string!r}")
    obj = getattr(importlib.import_module(module_path), attr)
    if expect == "callable" and not callable(obj):
        raise FatalEvaluationError(f"{import_string!r} did not resolve to a callable")
    if expect == "ValidationProfile" and not isinstance(obj, ValidationProfile):
        raise FatalEvaluationError(f"{import_string!r} did not resolve to a ValidationProfile")
    return obj


@dataclass(frozen=True)
class _ConfigRemoteObjective:
    """A RemoteObjective derived entirely from EvolveConfig — the canonical objective for evolve.
    Its evaluate() is the in-process local fallback (M2): resolve the entrypoint and run it at a
    default device, writing candidate.program to a temp .py (uniform path-or-None contract)."""

    _ref: RemoteRef
    epochs: int
    seed: int

    @property
    def remote_ref(self) -> RemoteRef:
        return self._ref

    def evaluate(self, candidate: Candidate) -> Metrics:
        fn = _resolve_hook(self._ref.entrypoint, expect="callable")
        # consumers get a plain, mutable dict (candidate.params is a read-only Mapping)
        kw = {"candidate_config": dict(candidate.params), "device": "cpu", "epochs": self.epochs, "seed": self.seed}
        with program_to_path(candidate) as program_path:  # uniform path-or-None (shared core helper)
            return fn(**kw, program_path=program_path)


def _remote_objective_from_config(cfg: EvolveConfig) -> RemoteObjective:
    return _ConfigRemoteObjective(
        _ref=RemoteRef(entrypoint=cfg.entrypoint, package=cfg.remote_package),
        epochs=cfg.evaluation.epochs,
        seed=cfg.evaluation.seed,
    )


def _build_evaluator(cfg: EvolveConfig, backend: ComputeBackend, objective: RemoteObjective) -> EvolveEvaluator:
    """Build an EvolveEvaluator with hooks resolved from the config import-strings. Used by BOTH the
    in-process seed-eval path and the OpenEvolve worker, so the two are identical."""
    ssv: Callable[[dict[str, Any]], tuple[bool, str]] | None = (
        _resolve_hook(cfg.search_space_validator, expect="callable") if cfg.search_space_validator else None
    )
    pre: Callable[[dict[str, Any]], dict[str, Any]] | None = (
        _resolve_hook(cfg.pre_validate, expect="callable") if cfg.pre_validate else None
    )
    profile: ValidationProfile | None = (
        _resolve_hook(cfg.validation_profile, expect="ValidationProfile") if cfg.validation_profile else None
    )
    return EvolveEvaluator(
        backend=backend,
        objective=objective,
        fitness_config=cfg.fitness,
        code_evolution=cfg.evolution.code_evolution,
        validation_profile=profile,
        allow_unvalidated_code=cfg.allow_unvalidated_code,
        search_space_validator=ssv,
        pre_validate=pre,
        timeout=cfg.evaluation.timeout_seconds,
    )


# --------------------------------------------------------------------------- seeds


def _discover_seed_programs(seed_programs_dir: str) -> list[Path]:
    seed_dir = Path(seed_programs_dir)
    if not seed_dir.is_dir():
        raise FileNotFoundError(f"Seed programs directory not found: {seed_dir}")
    programs = sorted(p for p in seed_dir.glob("*.py") if p.name != "__init__.py")
    if not programs:
        raise FileNotFoundError(f"No seed programs found in {seed_dir}")
    return programs


# EvalConfig fields deliberately EXCLUDED from seed-cache identity, with the reason for each.
# Rule: declare what determines the cached artifact's CONTENT, not what CONSUMES it.
_SEED_CACHE_EXCLUDE = frozenset(
    {
        # An infra budget, not a determinant of a seed's metrics. A truncated run maps to the worst-score
        # sentinel (combined_score=0) and is WRITTEN like any other result - _eval_one writes
        # unconditionally - but is never READ BACK, because _load_cached_seeds accepts only
        # combined_score > 0.0. That read filter is the ONLY thing making this exclusion safe; it is
        # pinned by test_a_zero_score_seed_result_is_never_cache_readable. Relax it and this exclusion
        # becomes silently unsafe.
        "timeout_seconds",
    }
)


def _eval_fingerprint(cfg: EvolveConfig) -> str:
    """Deterministic identity of the params that determine seed-result CONTENT.

    Covers EVERY EvalConfig field except `_SEED_CACHE_EXCLUDE` (fail-closed - a new field is picked up
    automatically; see `ruthless._fingerprint.fingerprint_model`) PLUS `evolution.code_evolution`, because
    that flag decides whether the evolved source is attached to the candidate, which changes what a
    config-only seed evaluates to (spec §7). `fingerprint` is Mapping-only, so compose via a mapping. The
    policy of WHAT determines seed content stays here; the hashing lives in core."""
    base = fingerprint_model(cfg.evaluation, exclude=_SEED_CACHE_EXCLUDE)
    return fingerprint({"eval": base, "code_evolution": cfg.evolution.code_evolution})


def _load_cached_seeds(
    seed_results_dir: Path, seed_programs: list[Path], fingerprint: str
) -> dict[str, dict[str, Any]]:
    cached: dict[str, dict[str, Any]] = {}
    for program in seed_programs:
        result_file = seed_results_dir / f"{program.stem}.json"
        if not result_file.exists():
            continue
        try:
            data = json.loads(result_file.read_text())
            if data.get("fingerprint") != fingerprint:
                continue
            metrics = data["metrics"]
            if metrics.get("combined_score", 0.0) > 0.0:
                cached[program.stem] = metrics
        except (json.JSONDecodeError, KeyError):
            _log.warning("corrupt_seed_cache", extra={"program": program.name})
    return cached


def _evaluate_seeds(
    evaluator: EvolveEvaluator,
    seed_programs: list[Path],
    results_dir: Path,
    fingerprint: str,
    *,
    max_parallel: int = 1,
    cached_seeds: dict[str, dict[str, Any]] | None = None,
) -> tuple[Path, dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    seed_results_dir = results_dir / "seed_results"
    seed_results_dir.mkdir(parents=True, exist_ok=True)
    cached = cached_seeds or {}
    to_evaluate = [p for p in seed_programs if p.stem not in cached]
    all_metrics: list[tuple[str, dict[str, Any]]] = []

    def _eval_one(program: Path) -> tuple[Path, dict[str, Any]]:
        metrics = evaluator.evaluate(str(program)).to_dict()
        (seed_results_dir / f"{program.stem}.json").write_text(
            json.dumps({"program": program.name, "fingerprint": fingerprint, "metrics": metrics}, indent=2)
        )
        return program, metrics

    best_path: Path | None = None
    best_metrics: dict[str, Any] = {}
    best_score = float("-inf")
    for program in seed_programs:
        if program.stem in cached:
            m = cached[program.stem]
            all_metrics.append((program.stem, m))
            if m.get("combined_score", 0.0) > best_score:
                best_score, best_path, best_metrics = m["combined_score"], program, m

    if to_evaluate:
        workers = min(max_parallel, len(to_evaluate))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for future in concurrent.futures.as_completed({pool.submit(_eval_one, p) for p in to_evaluate}):
                program, metrics = future.result()
                all_metrics.append((program.stem, metrics))
                score = metrics.get("combined_score", 0.0)
                if score > best_score:
                    best_score, best_path, best_metrics = score, program, metrics

    if best_path is None or best_score <= 0.0:
        raise FatalEvaluationError("No seed program produced a valid (non-zero) combined score")
    return best_path, best_metrics, all_metrics


# --------------------------------------------------------------------------- openevolve translation


def _translate_to_openevolve_config(cfg: EvolveConfig) -> dict[str, Any]:
    evo, llm = cfg.evolution, cfg.llm
    oe: dict[str, Any] = {
        "max_iterations": evo.iterations,
        "diff_based_evolution": evo.diff_based,
        "early_stopping_patience": evo.early_stopping_patience,
        "checkpoint_interval": evo.checkpoint_interval,
        "database": {
            "population_size": evo.population_size,
            "num_islands": evo.num_islands,
            "migration_interval": evo.migration_interval,
        },
        "evaluator": {"parallel_evaluations": evo.parallel_evaluations, "timeout": cfg.evaluation.timeout_seconds},
    }
    if cfg.prompt_template_dir and Path(cfg.prompt_template_dir).is_dir():
        oe["prompt"] = {"template_dir": str(Path(cfg.prompt_template_dir).resolve())}
    if llm.models:
        oe["llm"] = {
            "models": [
                {"name": m.name, "weight": m.weight, "api_base": m.api_base, "api_key": f"${{{m.api_key_env}}}"}
                for m in llm.models
            ],
            "temperature": llm.temperature,
            "max_tokens": llm.max_tokens,
        }
    return oe


def _set_api_keys(cfg: EvolveConfig) -> None:
    for env_var in {m.api_key_env for m in cfg.llm.models}:
        if not os.environ.get(env_var):
            _log.warning("api_key_env_unset", extra={"env_var": env_var})


_EVALUATOR_SCRIPT = '''\
"""Standalone evaluator loaded by OpenEvolve via importlib. Self-contained: rebuilds a config-derived
RemoteObjective + EvolveEvaluator from the serialised EvolveConfig JSON written alongside this script
(ProcessPoolExecutor workers get a fresh interpreter, no in-process globals). Each worker claims a
unique backend index via atomic claim files so N workers map 1:1 to N comma-listed backends."""

import json
import multiprocessing
import os
from pathlib import Path

_evaluator = None


def _claim_backend_index(backend_types, claim_dir):
    pid = os.getpid()
    for i in range(len(backend_types)):
        claim_file = claim_dir / f"_backend_claim_{i}"
        try:
            fd = os.open(str(claim_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(pid).encode())
            os.close(fd)
            return i
        except FileExistsError:
            continue
    return pid % len(backend_types)


def _get_evaluator():
    global _evaluator
    if _evaluator is not None:
        return _evaluator
    from ruthless.backends import create_backend
    from ruthless.config import BackendConfig, EvolveConfig
    from ruthless.strategies.evolve_.strategy import _build_evaluator, _remote_objective_from_config

    cfg_dict = json.loads(Path(__file__).with_name("_evaluator_config.json").read_text())
    cfg = EvolveConfig.model_validate(cfg_dict)

    backend_types = [t.strip() for t in cfg.backend.type.split(",")]
    is_worker = multiprocessing.current_process().name != "MainProcess"
    if len(backend_types) == 1 or not is_worker:
        backend = create_backend(cfg.backend, timeout=cfg.evaluation.timeout_seconds)
    else:
        index = _claim_backend_index(backend_types, Path(__file__).parent)
        single = BackendConfig(**{**cfg.backend.model_dump(), "type": backend_types[index]})
        backend = create_backend(single, timeout=cfg.evaluation.timeout_seconds)

    objective = _remote_objective_from_config(cfg)
    _evaluator = _build_evaluator(cfg, backend, objective)
    return _evaluator


def evaluate(program_path: str):
    return _get_evaluator().evaluate(program_path)
'''


def _write_evaluator_script(results_dir: Path, cfg: EvolveConfig) -> Path:
    (results_dir / "_evaluator_config.json").write_text(json.dumps(cfg.model_dump(), indent=2))
    script_path = results_dir / "_openevolve_evaluator.py"
    script_path.write_text(_EVALUATOR_SCRIPT, encoding="utf-8")
    return script_path


# --------------------------------------------------------------------------- strategy


class EvolveStrategy:
    """Thin :class:`~ruthless.strategy.SearchStrategy` adapter over OpenEvolve.

    OpenEvolve owns the evolutionary loop; this strategy owns orchestration: config translation, seed
    evaluation with a resume cache, the standalone evaluator script the worker subprocess rebuilds,
    and ``Result`` mapping. ``EvolveConfig`` is the single source of truth — ``run`` asserts the
    passed objective agrees with it before doing anything.

    Args:
        config: Evolve configuration (the canonical source for epochs/seed/backend/LLM/evolution).
        results_dir: Output + checkpoint directory (also where the resume cache lives).
        resume: If ``True``, reuse cached seed results matching the eval fingerprint.
    """

    def __init__(self, config: EvolveConfig, *, results_dir: str | Path, resume: bool = False) -> None:
        self._cfg = config
        self._results_dir = Path(results_dir)
        self._resume = resume

    def run(self, objective: Objective, *, backend: ComputeBackend) -> Result:
        cfg = self._cfg
        if not isinstance(objective, RemoteObjective):
            raise FatalEvaluationError(
                "EvolveStrategy requires a RemoteObjective; build one with _remote_objective_from_config(cfg)"
            )
        expected = _remote_objective_from_config(cfg)
        if (
            objective.remote_ref != expected.remote_ref
            or objective.epochs != cfg.evaluation.epochs
            or objective.seed != cfg.evaluation.seed
        ):
            raise FatalEvaluationError(
                "objective disagrees with EvolveConfig (remote_ref/epochs/seed); EvolveConfig is the source of truth"
            )

        self._results_dir.mkdir(parents=True, exist_ok=True)
        seed_programs = _discover_seed_programs(cfg.seed_programs_dir)
        fingerprint = _eval_fingerprint(cfg)
        cached = (
            _load_cached_seeds(self._results_dir / "seed_results", seed_programs, fingerprint) if self._resume else {}
        )
        evaluator = _build_evaluator(cfg, backend, objective)
        best_seed, _best_seed_metrics, all_seed_metrics = _evaluate_seeds(
            evaluator,
            seed_programs,
            self._results_dir,
            fingerprint,
            max_parallel=cfg.evolution.parallel_evaluations,
            cached_seeds=cached,
        )

        try:
            import openevolve
        except ImportError as exc:  # pragma: no cover - exercised only without the [evolve] extra
            raise FatalEvaluationError("openevolve is not installed; install ruthless[evolve]") from exc

        _set_api_keys(cfg)
        oe_cfg = openevolve.Config.from_dict(_translate_to_openevolve_config(cfg))
        evaluator_path = _write_evaluator_script(self._results_dir, cfg)
        best_result = openevolve.run_evolution(
            initial_program=str(best_seed),
            evaluator=str(evaluator_path),
            config=oe_cfg,
            iterations=cfg.evolution.iterations,
            output_dir=str(self._results_dir),
        )

        best_code = best_result.best_code or None
        best_metrics: Metrics = best_result.metrics or {}
        best = Evaluation(candidate=Candidate(id="best", params={}, program=best_code), metrics=best_metrics, ok=True)
        history = [
            Evaluation(candidate=Candidate(id=stem, params={}), metrics=m, ok=m.get("combined_score", 0.0) > 0.0)
            for stem, m in all_seed_metrics
        ]
        return Result(
            best=best,
            history=history,
            diagnostics={"best_score": best_result.best_score, "best_seed": best_seed.name},
            provenance={
                "strategy": "evolve",
                "iterations": cfg.evolution.iterations,
                "num_islands": cfg.evolution.num_islands,
                "checkpoint_dir": str(self._results_dir),
                **code_identity(),
            },
        )
