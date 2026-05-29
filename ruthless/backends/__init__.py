"""Compute backends ([backends] extra) + the create_backend factory.

A single backend name builds one backend; a comma-separated `type` builds one per name wrapped in a
priority-ordered BackendPool. Concrete-backend imports are DEFERRED inside the factories so the heavy
per-backend deps (huggingface_hub, docker, torch) load only when that backend is actually used."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ruthless.backend import ComputeBackend
from ruthless.config import BackendConfig

if TYPE_CHECKING:
    pass

__all__ = ["create_backend"]


def _make_local_cuda(cfg: BackendConfig, timeout: int) -> ComputeBackend:
    from ruthless.backends.local_cuda import LocalCudaBackend

    return LocalCudaBackend(device=cfg.device)


def _make_docker(cfg: BackendConfig, timeout: int) -> ComputeBackend:
    from ruthless.backends.docker import DockerBackend

    return DockerBackend(docker_image=cfg.docker_image or "")


def _make_hf_jobs(cfg: BackendConfig, timeout: int) -> ComputeBackend:
    from ruthless.backends.hf_jobs import HFJobsBackend

    return HFJobsBackend(hf_flavor=cfg.hf_flavor or "l40sx1", timeout=timeout)


def _make_remote_ssh(cfg: BackendConfig, timeout: int) -> ComputeBackend:
    from ruthless.backends.remote_ssh import RemoteSSHBackend

    return RemoteSSHBackend(
        host=cfg.ssh_host or "",
        user=cfg.ssh_user or "",
        remote_dir=cfg.ssh_remote_dir or "",
        python_path=cfg.ssh_python_path or "",
        timeout=timeout,
        device=cfg.device,
    )


_REGISTRY = {
    "local_cuda": _make_local_cuda,
    "docker": _make_docker,
    "hf_jobs": _make_hf_jobs,
    "remote_ssh": _make_remote_ssh,
}


def create_backend(config: BackendConfig, *, timeout: int = 900) -> ComputeBackend:
    """Build a ComputeBackend (or BackendPool) from a validated BackendConfig."""
    types = [t.strip() for t in config.type.split(",") if t.strip()]
    backends = [_REGISTRY[t](config, timeout) for t in types]
    if len(backends) == 1:
        return backends[0]
    from ruthless.backends.pool import BackendPool

    return BackendPool(backends)
