import numpy as np
import pytest

from ruthless.config import GridConfig
from ruthless.strategies.grid_.store import GridStore


def _cfg(store_dir, *, objective_id="obj-v1", **extra):
    base = {
        "kind": "grid",
        "metric": "loss",
        "design": "cartesian",
        "param_space": {"a": {"kind": "choice", "choices": ("x", "y")}},
        "store": {"kind": "sqlite", "path": str(store_dir / "grid.db"), "objective_id": objective_id},
    }
    base.update(extra)
    return GridConfig.model_validate(base)


def test_put_get_roundtrip_and_mkdir(tmp_path):
    cfg = _cfg(tmp_path / "nested")  # parent dir does not exist yet
    store = GridStore(cfg)
    assert store.get("fp1") is None
    store.put("fp1", {"loss": 0.5, "aux": 2.0})
    assert store.get("fp1") == {"loss": 0.5, "aux": 2.0}
    store.close()


def test_reopen_sees_committed_rows(tmp_path):
    cfg = _cfg(tmp_path)
    first = GridStore(cfg)
    first.put("fp1", {"loss": 1.0})
    first.close()
    assert GridStore(cfg).get("fp1") == {"loss": 1.0}


def test_meta_guard_objective_id(tmp_path):
    GridStore(_cfg(tmp_path, objective_id="v1")).close()
    with pytest.raises(ValueError, match="different grid"):
        GridStore(_cfg(tmp_path, objective_id="v2"))


def test_meta_guard_config(tmp_path):
    GridStore(_cfg(tmp_path)).close()
    changed = GridConfig.model_validate({**_cfg(tmp_path).model_dump(), "metric": "acc"})
    with pytest.raises(ValueError, match="different grid"):
        GridStore(changed)


def test_max_points_change_does_not_raise(tmp_path):
    GridStore(_cfg(tmp_path, max_points=100)).close()
    GridStore(_cfg(tmp_path, max_points=200)).close()  # max_points excluded from identity -> no raise


def test_schema_version_mismatch_raises(tmp_path):
    cfg = _cfg(tmp_path)
    store = GridStore(cfg)
    store._conn.execute("UPDATE grid_meta SET value='0' WHERE key='schema_version'")
    store.close()
    with pytest.raises(ValueError, match="different grid"):
        GridStore(cfg)


def test_corrupt_meta_missing_row_raises(tmp_path):
    cfg = _cfg(tmp_path)
    store = GridStore(cfg)
    store._conn.execute("DELETE FROM grid_meta WHERE key='objective_id'")
    store.close()
    with pytest.raises(ValueError, match="corrupt"):
        GridStore(cfg)


def test_guard_failure_closes_connection(tmp_path):
    import os

    GridStore(_cfg(tmp_path, objective_id="v1")).close()
    raised = False
    try:
        GridStore(_cfg(tmp_path, objective_id="v2"))
    except ValueError:
        raised = True
        # Unlink INSIDE the handler: the failed __init__'s frame (hence any leaked open connection) is still
        # referenced by the live traceback here, so a missing close() leaves the handle open and this unlink
        # raises PermissionError (WinError 32) on Windows. After the handler exits the frame is freed and GC
        # would mask the leak — which is why this must not be an `unlink` after a `with pytest.raises` block.
        os.unlink(str(tmp_path / "grid.db"))
    assert raised


def test_metrics_float_coercion(tmp_path):
    store = GridStore(_cfg(tmp_path))
    store.put("fp1", {"loss": np.float32(0.25)})  # type: ignore  # numpy would break json.dumps without coercion
    assert store.get("fp1") == {"loss": 0.25}
    store.close()
