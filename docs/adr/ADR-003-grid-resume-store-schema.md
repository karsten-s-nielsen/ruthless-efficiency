# ADR-003: Grid/Optuna resume-store schema and a library-wide store-identity rule

- **Status:** Accepted — `0.7.0`
- **Date:** 2026-09-26
- **Component:** `ruthless/strategies/grid_/store.py`, `ruthless/strategies/optuna_/strategy.py`,
  `ruthless/config/common.py` (`StoreConfig`), depends on `ruthless/_fingerprint.py` (ADR-002)

## Context

`0.7.0` adds `GridSearchStrategy`, whose resume is a strategy-owned on-disk store — the first hand-rolled
persistence format in the library (Optuna's resume delegates to Optuna's own SQLite storage). A persisted
format that consumers write and re-open across versions is, by Hyrum's Law, a compatibility surface, exactly
as the `fingerprint` digest is under ADR-002. Two correctness traps had to be closed at once:

- **Two-grids / stale-config reuse.** A resume store keyed only by `fingerprint(params)` would happily serve
  rows written by a *different* grid (different `param_space`/`design`/`metric`) whose points collide on
  params, mixing two grids' results into one `history`.
- **Stale-objective reuse.** The store's rows are valid only for a specific objective — its code version and
  the data it reads. Nothing in `GridConfig`/`OptunaConfig` identified that objective, so a rerun after the
  objective changed (the primary consumer, silly-kicks TF-58 D2, reads per-generation cached shards) would
  reuse the previous generation's scores. `code_identity()` is *ruthless's* own identity, not the objective's.

Optuna's existing `create_study(load_if_exists=True)` resume had the identical stale-objective trap.

## Decision

1. **`StoreConfig.objective_id` is required** (a non-empty string), on the shared `StoreConfig` value type so
   the rule covers every persisted strategy. It declares the objective identity a store's rows belong to.
   Because a `StoreConfig` exists only when resume is requested, a required field makes the declaration
   unavoidable (fail-closed, the same direction as ADR-002's exclusion-set rule). This is a breaking change,
   accepted deliberately.
2. **Grid store schema** (created idempotently on open; the parent directory is created if absent):
   - `grid_meta(key TEXT PRIMARY KEY, value TEXT)` — three rows: `schema_version`, `config_fingerprint`
     (`fingerprint_model(cfg, exclude={"store", "max_points"})`) and `objective_id`.
   - `grid_result(fp TEXT PRIMARY KEY, metrics_json TEXT)` — one row per evaluated point, `fp =
     fingerprint(params)`.
   - **Params are not stored** — they are re-derivable from the deterministic plan, and several
     `_tag`-supported level types (`Enum`, `PurePath`, `datetime`, `set`) are not `json.dumps`-able. Metrics
     are float-coerced before `json.dumps` (so a `numpy` scalar auxiliary round-trips).
   - **Meta is written in one transaction** on fresh-store init; a `grid_meta` found with a missing row is
     treated as corrupt and raises. Result rows are committed per `put` (autocommit), so a crash at point k of
     N leaves the first k rows durable and the rerun evaluates only N−k.
3. **Store identity = `config_fingerprint` + `objective_id`, honoured by both strategies:**
   - Grid: the two values are `grid_meta` rows; a mismatch on either raises at open.
   - Optuna: both live in **one** study user-attr `ruthless_identity` =
     `{"schema": 1, "objective_id", "config_fingerprint"}` (config fingerprint excludes `store`, `n_trials`
     and `warm_start` — the resume knobs). One `set_user_attr` is one atomic write, so there is no
     partial-write state; the guard is a total function of (attr present?, trial count?): present → compare
     (a malformed or unknown-`schema` value raises); absent + 0 trials → stamp (fresh); absent + ≥1 trial →
     legacy (raise).
4. **Legacy Optuna stores fail-closed with an explicit one-shot adoption.** A pre-0.7.0 study (no
   `ruthless_identity`, ≥1 trial) raises on resume, naming `adopt_legacy_store(config)`. That function stamps
   the identity once, refuses a study that already carries it, refuses a config with no store or a path with
   no study, and logs the adoption. It is deliberately not a config flag (a standing flag would be copied
   everywhere and silently disable the guard — Hyrum's Law).

## Consequences

- **The row key depends on ADR-002.** `fp = fingerprint(params)`, so a change to `_fingerprint._tag` that
  moves the digest invalidates every existing grid store. Such a change is breaking for grid stores and its
  CHANGELOG entry must say so — recorded here where the next editor of `_fingerprint.py` will look.
- **Schema stability.** Any change to the tables or their meaning bumps `SCHEMA_VERSION`; an older store then
  fails loud with no silent migration. Under `0.x` a schema change takes the minor slot and its CHANGELOG line
  states that it invalidates existing stores. `tests/test_grid_store_golden.py` pins the DDL and
  `SCHEMA_VERSION` so a drift fails CI until the version is bumped deliberately.
- **Scope.** Single-process, sqlite only (matching Optuna's SQLite resume). Multi-process/RDB resume stays a
  library-wide deferral.
- **Breaking surface.** Every consumer that builds a `StoreConfig` must supply `objective_id`; every Optuna
  resume over a store written by a different objective/config, or a legacy store, now raises. This is the
  intended fail-closed direction.
