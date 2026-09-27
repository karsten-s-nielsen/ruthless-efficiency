"""Strategy-owned sqlite resume store for GridSearchStrategy. Rows keyed by fingerprint(params); a meta
table binds the store to one (grid config + objective) identity and fails loud on mismatch. stdlib sqlite3,
single-process (StoreConfig scope). See ADR-003."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ruthless._fingerprint import fingerprint_model
from ruthless.config import GridConfig

SCHEMA_VERSION = "1"
GRID_META_DDL = "CREATE TABLE IF NOT EXISTS grid_meta (key TEXT PRIMARY KEY, value TEXT)"
GRID_RESULT_DDL = "CREATE TABLE IF NOT EXISTS grid_result (fp TEXT PRIMARY KEY, metrics_json TEXT)"


class GridStore:
    def __init__(self, cfg: GridConfig) -> None:
        if cfg.store is None:
            raise ValueError("GridStore requires cfg.store to be set")
        self._path = cfg.store.path
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, isolation_level=None)  # autocommit => durable per put
        try:
            self._conn.execute(GRID_META_DDL)
            self._conn.execute(GRID_RESULT_DDL)
            self._init_and_guard(cfg, cfg.store.objective_id)
        except BaseException:
            # A guard/corrupt-meta failure must not leak the open handle: on Windows an open connection
            # blocks the very "delete the store" remedy the error suggests (WinError 32).
            self._conn.close()
            raise

    def _init_and_guard(self, cfg: GridConfig, objective_id: str) -> None:
        want = {
            "schema_version": SCHEMA_VERSION,
            "config_fingerprint": fingerprint_model(cfg, exclude=frozenset({"store", "max_points"})),
            "objective_id": objective_id,
        }
        rows = dict(self._conn.execute("SELECT key, value FROM grid_meta").fetchall())
        if not rows:
            self._conn.execute("BEGIN")  # atomic meta init: no partial meta after a crash
            try:
                self._conn.executemany("INSERT INTO grid_meta (key, value) VALUES (?, ?)", list(want.items()))
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            return
        for key in want:
            if key not in rows:
                raise ValueError(f"grid store at {self._path!r} has corrupt meta (missing {key!r})")
        for key, value in want.items():
            if rows[key] != value:
                raise ValueError(
                    f"grid store at {self._path!r} was written for a different grid ({key} differs); "
                    "use a new path or delete the store"
                )

    def get(self, fp: str) -> dict[str, float] | None:
        row = self._conn.execute("SELECT metrics_json FROM grid_result WHERE fp = ?", (fp,)).fetchone()
        if row is None:
            return None
        loaded: dict[str, float] = json.loads(row[0])
        return loaded

    def put(self, fp: str, metrics: dict[str, float]) -> None:
        payload = json.dumps({k: float(v) for k, v in metrics.items()})  # float() accepts numpy scalars
        self._conn.execute("INSERT OR REPLACE INTO grid_result (fp, metrics_json) VALUES (?, ?)", (fp, payload))

    def close(self) -> None:
        self._conn.close()
