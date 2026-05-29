"""EvolveEvaluator — the OpenEvolve evaluator plugin. OpenEvolve calls evaluate(program_path) for
every candidate; this loads the candidate config, runs the (injected) search-space + AST-sandbox
gates, dispatches to a ComputeBackend via the 1A port, and computes a combined fitness score.

Generalised from the lakehouse evaluator: no `evolve.targets` coupling — search-space validation and
the pre-validation hook are injected callables; the backend is the 1A `evaluate(candidate, objective,
*, timeout)` port.

Single failure->sentinel mapping point (H1): a candidate failure (load, search-space, sandbox, or a
backend Fatal) is recorded as the OpenEvolve sentinel (combined_score=0, error=1) — because OpenEvolve
needs a per-candidate score; a crashed candidate must score worst so the search avoids it. Backends
raise (never record); this is the one place a failure becomes a score. NOTE (accepted trade-off): a
`failure_kind="infra"` (exhausted-transient) candidate is also recorded as 0, so transient infra
flakiness *can* evict an otherwise-good candidate — inherent to OpenEvolve; mitigated only by the
distinct tag + WARNING (strictly better than the lakehouse's undifferentiated fail_metrics)."""

from __future__ import annotations

import ast
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openevolve.evaluation_result import EvaluationResult

from ruthless._logging import get_logger
from ruthless.backend import ComputeBackend
from ruthless.config import FitnessConfig
from ruthless.errors import FatalEvaluationError, TransientEvaluationError
from ruthless.remote import RemoteObjective
from ruthless.result import Candidate
from ruthless.strategies.evolve_.sandbox import ValidationProfile, validate_program

_log = get_logger("strategies.evolve.evaluator")


def fail_metrics() -> dict[str, float]:
    """The OpenEvolve worst-score sentinel for a failed candidate (fresh dict each call)."""
    return {"combined_score": 0.0, "error": 1.0}


@dataclass(frozen=True)
class Program:
    config: dict[str, Any]
    has_custom_embed: bool
    has_custom_layers: bool
    source: str


def _extract_config(tree: ast.Module, source: str, filename: str) -> dict[str, Any]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "config":
                value_source = ast.get_source_segment(source, node.value)
                if value_source is None:
                    raise ValueError(f"Cannot extract config value from {filename}")
                raw = ast.literal_eval(value_source)
                if not isinstance(raw, dict):
                    raise ValueError(f"config must be a dict, got {type(raw).__name__} in {filename}")
                return raw
    raise ValueError(f"No 'config = {{...}}' assignment found in {filename}")


def _load_program(program_path: str) -> Program:
    source = Path(program_path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=program_path)
    config = _extract_config(tree, source, program_path)
    func_names = {node.name for node in ast.iter_child_nodes(tree) if isinstance(node, ast.FunctionDef)}
    return Program(
        config=config,
        has_custom_embed="custom_embed" in func_names,
        has_custom_layers="custom_layers" in func_names,
        source=source,
    )


class EvolveEvaluator:
    def __init__(
        self,
        *,
        backend: ComputeBackend,
        objective: RemoteObjective,
        fitness_config: FitnessConfig,
        code_evolution: bool = False,
        validation_profile: ValidationProfile | None = None,
        search_space_validator: Callable[[dict[str, Any]], tuple[bool, str]] | None = None,
        pre_validate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        timeout: float | None = None,
    ) -> None:
        self._backend = backend
        self._objective = objective
        self._fitness_config = fitness_config
        self._code_evolution = code_evolution
        self._validation_profile = validation_profile
        self._search_space_validator = search_space_validator
        self._pre_validate = pre_validate
        self._timeout = timeout

    def evaluate(self, program_path: str) -> EvaluationResult:
        try:
            program = _load_program(program_path)
        except Exception:  # noqa: BLE001 - H1: any candidate-load failure -> recorded sentinel (one place)
            return self._sentinel(f"load_error: {traceback.format_exc()}", kind="objective")

        config = program.config
        if self._pre_validate is not None:
            config = self._pre_validate(config)

        if self._search_space_validator is not None:
            ok, reason = self._search_space_validator(config)
            if not ok:
                _log.warning("search_space_rejected", extra={"program": program_path, "reason": reason})
                return self._sentinel(f"search_space: {reason}", kind="objective")

        program_source: str | None = None
        if program.has_custom_embed or program.has_custom_layers:
            if self._validation_profile is None:
                return self._sentinel("no_profile: Level-2 program but no ValidationProfile", kind="objective")
            valid, reason = validate_program(
                program.source, self._validation_profile, code_evolution=self._code_evolution
            )
            if not valid:
                _log.warning("validation_rejected", extra={"program": program_path, "reason": reason})
                return self._sentinel(f"validation_rejected: {reason}", kind="objective")
            program_source = program.source

        candidate = Candidate(id=Path(program_path).stem, params=config, program=program_source)
        try:
            metrics = self._backend.evaluate(candidate, self._objective, timeout=self._timeout)
        except FatalEvaluationError:
            return self._sentinel(f"objective: {traceback.format_exc()}", kind="objective")
        except TransientEvaluationError as exc:
            _log.warning("infra_failure", extra={"program": program_path, "error": str(exc)})
            return self._sentinel(f"infra: {exc}", kind="infra")
        except Exception:  # noqa: BLE001 - H1: the single failure->sentinel mapping point (any error -> score)
            return self._sentinel(f"backend_error: {traceback.format_exc()}", kind="objective")

        error_text = metrics.pop("_error_text", None)
        combined = self._compute_combined_score(metrics)
        result_metrics = {**metrics, "combined_score": combined}
        if error_text is not None:
            return EvaluationResult(metrics=result_metrics, artifacts={"error": str(error_text)})
        return EvaluationResult.from_dict(result_metrics)

    def _sentinel(self, text: str, *, kind: str) -> EvaluationResult:
        return EvaluationResult(
            metrics={**fail_metrics(), **self._fail_score()},
            artifacts={"error": text, "failure_kind": kind},
        )

    def _compute_combined_score(self, metrics: dict[str, float]) -> float:
        weights = self._fitness_config.combined_weights
        if not weights:
            return metrics.get(self._fitness_config.primary, 0.0)
        return sum(w * metrics.get(key, 0.0) for key, w in weights.items())

    def _fail_score(self) -> dict[str, float]:
        return {key: 0.0 for key in self._fitness_config.combined_weights}
