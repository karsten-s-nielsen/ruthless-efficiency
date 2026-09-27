import pytest
from pydantic import ValidationError

from ruthless.config import StoreConfig


def test_storeconfig_requires_objective_id():
    with pytest.raises(ValidationError):
        StoreConfig.model_validate({"kind": "sqlite", "path": "r/s.db"})


def test_storeconfig_rejects_blank_objective_id():
    with pytest.raises(ValidationError, match="objective_id"):
        StoreConfig.model_validate({"kind": "sqlite", "path": "r/s.db", "objective_id": "  "})


def test_storeconfig_accepts_objective_id():
    s = StoreConfig.model_validate({"kind": "sqlite", "path": "r/s.db", "objective_id": "v1"})
    assert s.objective_id == "v1"
