"""Shared config blocks used across strategies: compute-backend selection, fitness, evolution/LLM
knobs, evaluation, and the persistence store. These are value types in core config — they do NOT
import the `ruthless.backends` package (keeps the import-linter contract); `create_backend`
interprets `BackendConfig`."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, model_validator

_VALID_BACKEND_TYPES = frozenset({"local_cuda", "docker", "hf_jobs", "remote_ssh"})

# Shell-safety allowlists for fields the remote_ssh backend interpolates into an SSH command line.
# The objective entrypoint is shlex-quoted by the backend; device/dir/python_path are not (a path
# must keep its `~`), so they are constrained here instead — the config is the trust boundary, and
# this blocks injection (`;`, `&&`, `$(...)`, spaces) the moment a config is sourced from templated
# or semi-trusted input (CWE-78).
_SAFE_DEVICE = re.compile(r"^[A-Za-z0-9:_.+-]+$")
_SAFE_REMOTE_PATH = re.compile(r"^[A-Za-z0-9~@:/._+-]+$")


class BackendConfig(BaseModel):
    """Compute-backend selection (Plan 1B, `[backends]`). `type` is a single backend name or a
    comma-separated list (→ a priority-ordered BackendPool). A value type in core config; it does NOT
    import the `ruthless.backends` package (keeps the import-linter contract). `create_backend`
    interprets it."""

    type: str
    device: str = "cuda:0"
    docker_image: str | None = None
    hf_flavor: str | None = None
    ssh_host: str | None = None
    ssh_user: str | None = None
    ssh_remote_dir: str | None = None
    ssh_python_path: str | None = None

    @model_validator(mode="after")
    def _valid_types(self) -> BackendConfig:
        types = [t.strip() for t in self.type.split(",") if t.strip()]
        if not types:
            raise ValueError("BackendConfig.type must name at least one backend")
        unknown = [t for t in types if t not in _VALID_BACKEND_TYPES]
        if unknown:
            raise ValueError(f"Unknown backend type(s) {unknown}; valid: {sorted(_VALID_BACKEND_TYPES)}")
        return self

    @model_validator(mode="after")
    def _safe_shell_fields(self) -> BackendConfig:
        if not _SAFE_DEVICE.fullmatch(self.device):
            raise ValueError(f"device {self.device!r} contains unsafe characters (allowed: letters/digits/:._+-)")
        for field_name in ("ssh_remote_dir", "ssh_python_path"):
            value = getattr(self, field_name)
            if value is not None and not _SAFE_REMOTE_PATH.fullmatch(value):
                raise ValueError(f"{field_name} {value!r} contains unsafe characters for an SSH command line")
        return self


class FitnessConfig(BaseModel):
    primary: str
    secondary: str | None = None
    combined_weights: dict[str, float] = {}
    minimize: bool = False

    @model_validator(mode="after")
    def _weights(self) -> FitnessConfig:
        if self.combined_weights:
            total = sum(self.combined_weights.values())
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"combined_weights must sum to 1.0, got {total}")
            if self.primary not in self.combined_weights:
                raise ValueError("primary must be in combined_weights when weights are given")
        return self


class EvolutionConfig(BaseModel):
    iterations: int = 150
    population_size: int = 200
    num_islands: int = 3
    migration_interval: int = 30
    parallel_evaluations: int = 1
    diff_based: bool = True
    early_stopping_patience: int = 40
    checkpoint_interval: int = 5
    code_evolution: bool = False


class LLMModelConfig(BaseModel):
    name: str
    weight: float
    api_base: str
    api_key_env: str


class LLMConfig(BaseModel):
    models: list[LLMModelConfig] = []
    temperature: float = 0.7
    max_tokens: int = 4096

    @model_validator(mode="after")
    def _weights(self) -> LLMConfig:
        if self.models:
            total = sum(m.weight for m in self.models)
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"LLM model weights must sum to 1.0, got {total}")
        return self


class EvalConfig(BaseModel):
    # The lakehouse `dataset` default ("luxury-lakehouse/...") is DROPPED — domain; the consumer's
    # train_and_evaluate / RemoteRef owns data. epochs/seed here are the single source of truth.
    epochs: int = 5
    timeout_seconds: int = 900
    seed: int = 42


class StoreConfig(BaseModel):
    kind: Literal["sqlite"] = "sqlite"  # only sqlite in Phase 2 (single-process resume; RDB is §10/later)
    path: str
    objective_id: str  # REQUIRED identity of the objective (code + data version) these results are valid for

    @model_validator(mode="after")
    def _objective_id_nonempty(self) -> StoreConfig:
        # Fail-closed (same direction as fingerprint_model's exclusion-set rule): the caller must DECLARE the
        # objective identity a resume store's rows belong to; a blank id is as bad as none.
        if not self.objective_id.strip():
            raise ValueError("StoreConfig.objective_id must be a non-empty string")
        return self
