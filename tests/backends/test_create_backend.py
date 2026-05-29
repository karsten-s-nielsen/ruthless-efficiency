import pytest
from pydantic import ValidationError

from ruthless.backends import create_backend
from ruthless.backends.docker import DockerBackend
from ruthless.backends.local_cuda import LocalCudaBackend
from ruthless.backends.pool import BackendPool
from ruthless.config import BackendConfig


def test_single_backend_builds_one_instance():
    b = create_backend(BackendConfig(type="local_cuda", device="cuda:2"))
    assert isinstance(b, LocalCudaBackend) and b._device == "cuda:2"


def test_docker_builds_stub():
    assert isinstance(create_backend(BackendConfig(type="docker")), DockerBackend)


def test_comma_multi_type_builds_pool():
    b = create_backend(BackendConfig(type="hf_jobs,hf_jobs"))
    assert isinstance(b, BackendPool) and len(b._backends) == 2


def test_unknown_type_rejected_at_config_validation():
    with pytest.raises(ValidationError):
        BackendConfig(type="no_such")
