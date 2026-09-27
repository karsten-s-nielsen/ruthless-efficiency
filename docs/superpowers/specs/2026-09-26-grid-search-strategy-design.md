# Spec — native `GridSearchStrategy` + a library-wide store-identity rule

**Date:** 2026-09-26
**Status:** rev 7 — independent review round 4 **APPROVED**
(`D:\Development\_reviews\2026-09-26-grid-search-strategy-spec-r4.md`, 0 blocking); the one optional CONSIDER
(G-SPEC-25 — content-validate `ruthless_identity`, add a `schema` sub-field) is folded in as a strict
fail-closed hardening. Rounds 1–3 incorporated at rev 2/5/6; Optuna full resume-identity guard added rev 5
(owner ruling). This spec is ready for the implementation plan.
**Baseline:** `main` @ `a93734a`, version `0.6.0`, tree carries only untracked `.serena/` + this spec
(feature branch `feat/grid-strategy`).
**Origin:** a handoff from the silly-kicks TF-58 session, prerequisite of TF-58. Full handoff at
`D:\Development\_handoffs\ruthless-grid-strategy-handoff.md`; its pinned contract is reproduced **verbatim
in Appendix A**.
**Target release:** `0.7.0` — minor, but now **contains a deliberate breaking change** (owner-approved:
"breaking changes are not a concern"): `StoreConfig` gains a **required** `objective_id`, so any config that
set a store without it must add it. No `_tag`/digest change, so **existing `fingerprint` caches are
unaffected**; existing *Optuna SQLite stores* written at ≤0.6.0 lack the new identity attr and are handled
per §3.4.
**Design bar (owner directive, 2026-09-26):** "gold standard, best practice; breaking changes are not a
concern." Fail-closed everywhere a persisted result could be silently reused.

### Rev 7 changes (independent review round 4 — APPROVED)

| Review ID | Change |
|---|---|
| G-SPEC-25 (optional CONSIDER, folded in) | `ruthless_identity` gains a `"schema": 1` sub-field, and the guarded path **content-validates** the attr before comparing: a non-dict, missing sub-field, or unknown `schema` raises a defined `ValueError` (foreign/future writer), never an undefined comparison. Recorded in ADR-003. §3.4, test 30c. |

### Rev 6 changes (independent review round 3)

| Review ID | Change |
|---|---|
| G-SPEC-21 | Optuna's two identity attrs are **collapsed into one** `ruthless_identity` dict attr (`{objective_id, config_fingerprint}`) — one `set_user_attr` = one atomic storage write, so the "exactly one of two attrs present" partial-crash state is impossible; the fresh/legacy/guarded rule is now a total function of (attr-present?, trials?). §3.4. |
| G-SPEC-22 | CHANGELOG `### Breaking` now names the new Optuna config-identity guard (resume with a changed `param_space`/`sampler`/`direction`/`metric` raises) with its remedy (new `store.path`). §5.4. |
| G-SPEC-23 | Reworded: `optuna_` does **not** import `fingerprint_model` today; adding it is an allowed strategy→core import with no third-party edge. §5.2. |
| G-SPEC-24 | `adopt_legacy_store` raises a **clear `ValueError`** for a `store.path` with no study (not a leaked optuna `KeyError`), and for `config.store is None`. §3.4, test 35b. |
| grid_meta atomicity (round-3 "outside") | The three `grid_meta` rows are written in **one transaction** on fresh-store init; a missing row → corrupt → `ValueError`. Same crash-atomicity principle as G-SPEC-21. §3.3, test 25b. |

### Rev 4 changes (independent review round 2)

| Review ID | Change |
|---|---|
| G-SPEC-16 | `adopt_legacy_store` **drops its `objective_id` kwarg** — `StoreConfig.objective_id` is required, so the config already carries the one identity to stamp. Signature: `adopt_legacy_store(config: OptunaConfig)` (the whole config, because G-SPEC-18 makes it stamp `config_fingerprint` too); it stamps `config.store.objective_id`. §3.4, §5.2, tests 31–35. |
| G-SPEC-17 | Rule 5 now also rejects an **unhashable** level (`Candidate` params must be hashable — `result.py`). A `set` is `fingerprint`-able but unhashable, so it is rejected at construction; test 22 uses `frozenset`, and a new test shows a `set` level raises. §1.2 rule 5, §1.3. |
| G-SPEC-19 | "Fresh vs legacy vs guarded" Optuna study is **defined** by attr-presence + trial count (a `load_if_exists` create cannot tell on its own): attr present → guarded (compare); attr absent + 0 trials → fresh (stamp); attr absent + ≥1 trial → legacy (raise). Test 31's legacy fixture carries ≥1 trial. §3.4. |
| G-SPEC-20 | Downstream notice recorded: silly-kicks builds `StoreConfig` at 6 sites (`calibration/_spaces.py:48,73,116`, `train_xshot_occurrence.py:202`, `train_xcross_attempt.py:270`, `test_xshot_occurrence_integration.py:69`) — all break at `>=0.7.0`; the TF-58 session carries that migration (this session does not edit silly-kicks). §3.4 TF-58 note, Appendix A. |
| G-SPEC-18 (owner: **add it now**) | Full Optuna resume-identity guard added: the `ruthless_identity` attr now also carries `config_fingerprint = fingerprint_model(OptunaConfig, exclude={"store","n_trials","warm_start"})` = `{kind,metric,direction,sampler,param_space}`; a resumed study whose config differs fails loud. The rev-3 "new non-goal" is **removed**. `adopt_legacy_store` takes the `OptunaConfig` (it must build the identity from the full config; config_fingerprint needs it), which also resolves G-SPEC-16 cleanly. §3.4, §6, tests 34–35. |

### Rev 3 changes (owner sign-off, hardened)

| Item | Change |
|---|---|
| objective identity (was G-SPEC-05, decision 10) | **Promoted from a GridConfig field to a required `StoreConfig.objective_id`** (core `config/common.py`), so one rule covers every persisted strategy. **Required whenever a store is set** (fail-closed — an optional default re-opens the trap). **`OptunaStrategy` must honour it this release too** (its `load_if_exists=True` resume has the identical trap): Optuna records it in the study's attrs on create and raises on mismatch at load. A field one strategy silently ignores is a bug. §3.4. |
| ADR (was G-SPEC-13, decision 11) | **Write `ADR-003`** for the on-disk resume-store schema **and back it with a golden test** (`tests/test_grid_store_golden.py`) that pins the table DDL + `schema_version`, in the style of `test_fingerprint_golden.py`, so a schema change fails CI until the version is bumped deliberately. §5.4. |
| existing tests | `tests/test_optuna_config.py:23` and `tests/e2e/test_optuna_resume_gate.py:24` build a store without `objective_id`; both updated to the required field. Plus a new Optuna "objective_id mismatch raises on resume" test. §4. |
| ~~new non-goal~~ (removed in rev 5) | Rev 3 deferred Optuna's full resume config-identity guard; **rev 5 adds it** (G-SPEC-18, owner-approved), so this non-goal is removed. §3.4, §6. |
| legacy Optuna stores (owner directive) | An attr-less (≤0.6.0) Optuna study on resume **raises, fail-closed** — no silent stamping. The escape hatch is an explicit one-shot `adopt_legacy_store(config)` (in `ruthless.strategies.optuna_`, not a config flag): it stamps the single `ruthless_identity` attr **once**, refuses a study that already carries it, requires the study to exist, and logs the adoption. §3.4, §5.2, tests 29–35. |

### Rev 2 changes (independent review round 1 — all findings accepted)

| Review ID | Change |
|---|---|
| G-SPEC-01 (BLOCKING) | Size guard uses a non-materialising per-dimension `level_count`; the guard runs **before** any rule that could materialise levels; `IntRange` membership is arithmetic. §1.2, §1.4, §1.5. |
| G-SPEC-02 | Resume durability: each `put` is committed before the next point is evaluated. §3.3, test 20. |
| G-SPEC-03 | Old test 20 replaced with an abort-driven public-surface test. §4. |
| G-SPEC-04 | Store drops `params_json` (params re-derived from the plan; key is the fingerprint); metrics float-coerced. §3.3. |
| G-SPEC-06 | Header count fixed; full "adds to the minimum" list in Appendix A; lazy `prepare()` listed; Appendix A restores the change-control sentence. |
| G-SPEC-07 | Every `Choice` level + `baseline`/`points` value is validated `fingerprint`-able at construction. §1.2 rule 5, §1.3. |
| G-SPEC-08 | Size-guard boundary test added. Test 8. |
| G-SPEC-09 | §5.1 no longer claims a group; `__all__` is alphabetised (ruff RUF022). |
| G-SPEC-10 | `tests/strategies/grid_/__init__.py` is a stated deliverable. |
| G-SPEC-11 | Tests for the `schema_version` mismatch and parent-dir creation. Tests 25–26. |
| G-SPEC-12 | `param_space` is required (no default). §1.1. |
| G-SPEC-14 | Auxiliary metrics float-coerced before storage. §3.3, test 23. |

---

## 0. Summary of decisions

"Owner-confirmed"/"owner-approved" notes were decided interactively in the 2026-09-26 design session.

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | Native `GridSearchStrategy` vs `OptunaConfig.sampler="grid"` | **NATIVE, separate strategy** | GridSampler is Cartesian-only; cannot express OAT/points, cannot satisfy Appendix A, adds `optuna` for enumeration that needs none. Owner-confirmed. §2. |
| 2 | Grid-size guard | **`max_points: int = 100_000`, closed-form `level_count`** | Never materialises; runs before membership; `IntRange(0, 10**12)` raises fast (G-SPEC-01). Owner-confirmed default. §1.4. |
| 3 | CLI availability | **REGISTER `grid`** | One registry row. Owner-confirmed. §5.3. |
| 4 | Float grids | **`FloatRange` raises; floats are `Choice`** | Matches sklearn `ParameterGrid`. Owner-confirmed. §1.2, §6. |
| 5 | Parallel dispatch | **SEQUENTIAL** | Library-wide deferral; TF-58 does not need it. §2.4, §6. |
| 6 | Grid resume store | **stdlib `sqlite3`, `fingerprint`-keyed rows, per-put commit, config+objective meta-guard** | No new dependency; single-process. §3.3. |
| 7 | Level/size logic placement | **CORE (`config/space.py`)** | `GridConfig` validators cannot import `ruthless.strategies`. §1.5. |
| 8 | Point identity | **`fingerprint(dict(params))`** — dedup *and* store key | §0.1. §2.2. |
| 9 | `seed` in grid | **NONE** | Deterministic; no `seed` in `provenance`. §2.3, §3.1. |
| 10 | Store identity (objective) | **`StoreConfig.objective_id`, REQUIRED when a store is set; library-wide** | Owner-approved + hardened: on `StoreConfig`, required, honoured by **Grid and Optuna** (fail-closed). Closes stale-objective reuse (TF-58 D2 reads per-generation shards). §3.4. |
| 11 | ADR + enforcement | **ADR-003 + a golden schema test** | Owner-approved + hardened: the store is a persisted compatibility surface (like the digest, ADR-002); a golden test pins the schema so a change fails CI. §5.4. |
| 12 | Optuna resume-identity guard this release | **FULL: both `objective_id` AND `config_fingerprint`** (record in study attrs, raise on mismatch) | Owner-ruled (G-SPEC-18): add the full guard now, fail-closed and symmetric with Grid — not just `objective_id`. `n_trials`/`warm_start` excluded from the identity (resume knobs). §3.4, §6. |
| 13 | Ceremony | **spec → review → plan → review → TDD → `/final-review` → commit on explicit approval → PR → `v0.7.0` → OIDC publish** | New public surface + a breaking config change; pin before code. §5.4. |

### 0.1 What this design relies on, verified by execution rather than assumed

Throwaway probe (`scratchpad/grid_probe.py`, not in the library) executed against installed `0.6.0`; all
seven outcomes also re-verified against source by the reviewer (report rows 8–14). Each becomes a test:

1. `fingerprint` order-insensitive over a param dict → sound dedup + store key.
2. `fingerprint` distinguishes values.
3. `bool` ≠ `int` (`_tag` branch order; matters for type-strict membership).
4. `Candidate` equality includes `id` → dedup on *params*, not the `Candidate` (post-dedup `g{index}` id).
5. `frozenset(params.items())` is a valid in-memory key (spec uses `fingerprint` for both so they can't drift).
6. `classify_metric(nan, …)` raises `FatalEvaluationError`.
7. `fingerprint` → 16 lowercase hex.

---

## 1. The config contract — `GridConfig`

New member of the discriminated `StrategyConfig` union in `ruthless/config/strategies.py`, `kind="grid"`.

### 1.1 Fields

```python
class GridConfig(BaseModel):
    kind: Literal["grid"]
    metric: str
    direction: Direction = Direction.MINIMIZE
    design: Literal["cartesian", "one_at_a_time", "points"]
    param_space: dict[str, ParamSpec]                    # REQUIRED (rule 1 rejects empty)
    baseline: dict[str, Any] | None = None               # required iff design == "one_at_a_time"
    points: list[dict[str, Any]] | None = None           # required iff design == "points"
    store: StoreConfig | None = None                      # None => no resume; StoreConfig now carries objective_id (§3.4)
    max_points: int = 100_000
```

The objective identity lives on `StoreConfig.objective_id` (§3.4), **not** on `GridConfig` — it is a
persisted-store concern shared with every strategy, so it belongs on the store type.

### 1.2 Validation — construction-time, fail-loud (`model_validator(mode="after")`)

Ordered so nothing materialises a large `IntRange` before the size guard (G-SPEC-01):

1. `param_space` non-empty.
2. No `FloatRange` in `param_space` (message names `Choice`).
3. Design-field presence + exclusivity: OAT → `baseline` present, `points` None; `points` → `points`
   present & non-empty, `baseline` None; `cartesian` → both None.
4. **Size guard (before any membership check):** `grid_plan_size(...) <= max_points`, from the
   non-materialising `level_count` (§1.4).
5. **Fingerprintable AND hashable (G-SPEC-07, G-SPEC-17):** each `Choice` level + each `baseline`/`points`
   value must be a `_tag`-supported native type (validated by fingerprinting it once — numpy scalars raise
   here, not at plan time) **and** hashable (validated by `hash(value)` — a `Candidate`'s params must be
   hashable, `result.py`). A `set` is `fingerprint`-able but unhashable, so it is rejected here; use a
   `frozenset` (both). `IntRange` yields native, hashable `int`s and is skipped.
6. `baseline` (OAT): keys **equal** `param_space` keys; each value passes type-strict membership (§1.3).
7. `points`: each entry's keys **equal** `param_space` keys; each value passes type-strict membership.

### 1.3 Type-strict, non-materialising level membership

`value in levels` is wrong: `3 in (3.0,)` and `True in (1,)` are `True`, but `fingerprint` tags them
distinctly, so a `3.0` where the level is `3` would validate then never match its store row/dedup key.
Membership is type-strict and dispatches on the spec so it never materialises an `IntRange`:

```python
def is_level(value: object, spec: ParamSpec) -> bool:
    if isinstance(spec, IntRange):
        return type(value) is int and spec.lo <= value <= spec.hi     # arithmetic, no tuple
    if isinstance(spec, Choice):
        return any(type(value) is type(lvl) and value == lvl for lvl in spec.choices)
    return False   # FloatRange rejected by rule 2
```

`type(True) is int` is `False`, so `True` where the level is `1` is refused, matching the digest. Honest
limitation (correcting rev-1 overclaim, G-SPEC-07): a level must be a `_tag`-supported native type; a numpy
scalar is rejected by rule 5.

### 1.4 The size guard is closed-form and never materialises (`level_count`)

```python
def level_count(spec: ParamSpec) -> int:
    if isinstance(spec, IntRange): return spec.hi - spec.lo + 1      # arithmetic
    if isinstance(spec, Choice):   return len(spec.choices)
    raise TypeError(...)
```

- `cartesian`: `prod(level_count(spec) …)`
- `one_at_a_time`: `1 + sum(level_count(spec) - 1 …)` (upper bound; dedup can only lower it)
- `points`: `len(points)`

No `range(lo, hi+1)` is built; `IntRange(0, 10**12)` raises in microseconds (test 7). This is
`diagnostics["n_points"]` (pre-dedup); `n_unique` is what is evaluated.

### 1.5 Core placement (keeps `.importlinter` green)

`GridConfig` validators run in `ruthless.config.strategies` (a `core-isolation` `source_module`, forbidden
`ruthless.strategies`). Pure helpers live in `ruthless/config/space.py`:

```python
def levels(spec) -> tuple[Any, ...]: ...    # MATERIALISES; STRATEGY enumeration only, AFTER the guard
def level_count(spec) -> int: ...           # non-materialising; config guard/validation
def grid_plan_size(design, param_space, points) -> int: ...
def is_level(value, spec) -> bool: ...
```

`random_`/`optuna_` are not modified; these helpers are additive.

---

## 2. The strategy — `ruthless/strategies/grid_/`

`grid_/strategy.py` holds `GridSearchStrategy`; `grid_/__init__.py` re-exports it
(`from ruthless.strategies.grid_ import GridSearchStrategy`), mirroring `random_/__init__.py`. Imports are
core-only (the `ruthless.backend` **port**, not `ruthless.backends`). **No numpy, no optuna.**

### 2.1 Enumeration (pure, deterministic) — `grid_/plan.py`

- `cartesian`: `itertools.product(*[levels(spec) …])` zipped to `param_space` key order (last dim varies
  fastest — deterministic, pinned).
- `one_at_a_time`: `baseline` first; then per `name` in order, per `lvl != baseline[name]` (type-strict),
  emit `{**baseline, name: lvl}`.
- `points`: as given.

Then **de-duplicate preserving first occurrence**, keyed by `fingerprint(dict(params))`. Survivors get
stable ids `g{index}` by position; ids are stable across runs; each distinct dict evaluated exactly once
(Appendix A §4).

### 2.2 Point identity

`fingerprint(dict(candidate.params))` — the single notion for in-memory dedup and the sqlite row key
(decision 8; §0.1 facts 1–2, 4). Not `Candidate` equality (includes the post-dedup `id`).

### 2.3 Evaluation

Sequential through the `ComputeBackend` port, as `RandomSearchStrategy`:

```python
candidate = Candidate(id=f"g{i}", params=params)
metrics = backend.evaluate(candidate, objective)          # or the cached fast path, §2.5
classify_metric(metrics[cfg.metric], candidate_id=candidate.id, metric=cfg.metric)  # scored only
history.append(Evaluation(candidate=candidate, metrics=metrics, ok=True))
```

Non-finite scored metric → `FatalEvaluationError` propagates and aborts; that point is not persisted, so a
resume retries it (TF-58 D2's missing-shard flow). `ok=True` always, as `random_`/`optuna_`.

### 2.4 Dispatch stays sequential

No `map_work_units`; concurrent dispatch is a library-wide deferral (§6).

### 2.5 `CachedObjective` fast path (same rule as `OptunaStrategy`)

- `extra = set(param_space) - objective.patch_params`; if non-empty → `ValueError`.
- `prepare()` once, **lazily** — only if ≥1 point needs evaluating, so a fully-resumed run does **zero**
  `prepare()` (refines Appendix A §4.5; listed in Appendix A per G-SPEC-06). Then `evaluate_patch` per point.
- Store hits skip evaluation and `prepare()` entirely.

---

## 3. `Result`, semantics, and resume

### 3.1 The returned `Result`

- `best`: optimises `metric`/`direction`; tie → first in enumeration order (strict `<`/`>`).
- `history`: one `Evaluation` per distinct point (len `== n_unique`), in order, each with its full `metrics`
  dict (TF-58's sensitivity artifact source, Appendix A §7).
- `diagnostics`: `{"design", "n_points", "n_unique", "n_from_store"}`. `n_points >= n_unique`.
- `provenance`: `{"strategy": "grid", "design", "direction", **code_identity()}`. **No `seed`.**

### 3.2 Determinism

Same ids, `history` order, `best` across fresh and resumed runs. No RNG.

### 3.3 Grid resume store — stdlib `sqlite3`, `fingerprint`-keyed, per-put commit

`store` set (`StoreConfig`, §3.4): completed points persist; a rerun evaluates only not-yet-done points.
Stdlib `sqlite3`, single-process. Parent dir created with `mkdir(parents=True, exist_ok=True)` (test 26).

**Schema** (created idempotently; params **not** stored — G-SPEC-04 — being re-derivable from the plan):

```
grid_meta(key TEXT PRIMARY KEY, value TEXT)      -- schema_version, config_fingerprint, objective_id
grid_result(fp TEXT PRIMARY KEY, metrics_json TEXT)
```

**Durability (G-SPEC-02):** each row is committed before the next point is evaluated (`isolation_level=None`
autocommit, or explicit `commit()` per `put`). A crash at point k of N leaves the first k rows durable; the
resume evaluates only N−k (test 20).

**Metric encoding (G-SPEC-04/14):** `json.dumps({k: float(v) for k, v in metrics.items()})` — float-coercion
accepts `numpy.float32`/`int64` auxiliaries; the scored metric is finite by storage time; `json`'s
`Infinity`/`NaN` round-trip preserves non-finite auxiliaries. No `_tag`-only type ever reaches `json.dumps`.

**Meta-guard.** On open, guard three `grid_meta` rows; any mismatch raises `ValueError` ("store at
`<path>` was written for a different grid config/objective; use a new path or delete the store"):
- `schema_version` (test 25) — governs the ADR-003 stability stance (§5.4).
- `config_fingerprint = fingerprint_model(cfg, exclude={"store", "max_points"})` — the grid's identity
  (design/metric/direction/param_space/baseline/points). Closes the two-grids trap.
- `objective_id = cfg.store.objective_id` (§3.4) — closes the stale-objective trap.

Empty `grid_meta` → fresh store: write all three rows **in a single transaction** (an explicit
`BEGIN`/`COMMIT`, even under the per-`put` autocommit used for `grid_result`), so a crash during meta
initialisation can never leave a partially-written meta the guard would then misread (same crash-atomicity
principle as the Optuna single-attr, G-SPEC-21). A `grid_meta` found with a missing row is treated as
corrupt → `ValueError` naming the path.

**Loop:**
```
for i, params in enumerate(plan):
    fp = fingerprint(dict(params))
    row = store.get(fp)
    if row is not None:
        metrics = json.loads(row); n_from_store += 1              # hit -> no evaluate/prepare
    else:
        metrics = <backend.evaluate | cached evaluate_patch>      # prepare() lazily on first miss
        classify_metric(metrics[cfg.metric], ...)                 # fatal -> raise, not persisted
        store.put(fp, metrics); store.commit()                    # durable before the next point
    history.append(Evaluation(Candidate(id=f"g{i}", params=params), metrics, ok=True))
```

### 3.4 Store identity — a library-wide rule (`StoreConfig.objective_id`)

**The rule (owner directive, decision 10/12).** A resume store persists results valid only for a specific
objective — its code version and the data it reads. The caller must declare that identity, and the library
**forces** the declaration rather than assuming the objective is unchanged (the same fail-closed direction
as `fingerprint_model`'s exclusion-set rule).

- **`StoreConfig` (core `config/common.py`) gains `objective_id: str`, required + non-empty.** Because a
  `StoreConfig` exists only when resume is requested, a required field makes the declaration unavoidable.
  An optional default (`None`) would re-open the trap for anyone who omits it — rejected.
- **Every persisted strategy honours it (a field one strategy silently ignores is a bug):**
  - **Grid:** binds `objective_id` into its sqlite meta-guard (§3.3); mismatch → `ValueError` at open.
  - **Optuna** guards both identities in **one** study user-attr — `ruthless_identity`, a single dict
    `{"schema": 1, "objective_id": store.objective_id, "config_fingerprint": <fp>}` where
    `<fp> = fingerprint_model(OptunaConfig, exclude={"store", "n_trials", "warm_start"})` =
    `{kind, metric, direction, sampler, param_space}`. `n_trials` is excluded because resuming to run *more*
    trials is the normal case; `warm_start` because it is enqueued only on a fresh study; `store` because its
    path is not identity and `objective_id` is a sub-field here. **One attr = one `set_user_attr` = one atomic
    storage write**, so there is no partial-write state to reason about (G-SPEC-21). `create_study(load_if_exists=True)`
    cannot itself tell fresh from resumed, so the state is derived **after** create from attr-presence + trial
    count (G-SPEC-19) — a total function over the two observable facts:
    - attr **present** → *guarded*: first validate the attr is **well-formed** — a dict with `schema == 1` and
      both sub-fields; a malformed or unknown-`schema` value (a foreign writer, or a future ruthless version)
      raises a defined `ValueError` ("corrupt or unrecognised `ruthless_identity`; use a new store path" —
      G-SPEC-25), never an undefined comparison. Then compare both sub-fields; a mismatch raises `ValueError`
      **before** `optimize` (distinct messages — "different objective" vs "different config"). Fail-closed
      symmetry with Grid.
    - attr **absent** and **0 trials** → *fresh*: stamp `ruthless_identity` (one write, persisted to storage).
    - attr **absent** and **≥1 trial** → *legacy* (a study written at ≤0.6.0): raise (see below).

    The rule is total over both the observable state **and** the attr's content: every (attr-present?, trials?)
    combination has a defined outcome, and a present attr is content-validated before use (`schema` is the
    forward-compat seam — a later ruthless bumps it and old readers fail loud rather than misread). Recorded in
    ADR-003; tests 30–35 + 30c.

    This closes Optuna's stale-objective **and** stale-config resume traps (`load_if_exists` otherwise resumes
    a study written by a different objective or a different `param_space`/`sampler`/`direction`).

**Legacy Optuna stores — fail-closed with an explicit one-shot adoption (owner directive).** A study written
at ≤0.6.0 carries no `ruthless_identity` attr. Rather than silently stamp it (which would permanently bless a
store the guard never actually checked — the exact hole the guard exists for) or refuse it with no remedy
(which discards every completed trial even when the objective is genuinely unchanged):

- **Resume of a legacy (attr-less, ≥1-trial) study raises** `ValueError`, naming the store path **and the
  exact adoption call to run**.
- The escape hatch is one public function, **`adopt_legacy_store(config: OptunaConfig)`**, in
  `ruthless.strategies.optuna_` (re-exported from `optuna_/__init__.py`). It is a deliberate, one-time caller
  assertion that the study at `config.store.path` was produced by *this* config. It takes the whole
  `OptunaConfig` because it must build the `ruthless_identity` attr from both `config.store.objective_id` (the
  single source, so there is **no redundant `objective_id` argument**, G-SPEC-16) **and** the
  `config_fingerprint` (computed from `config`, which a bare `StoreConfig` cannot supply, G-SPEC-18). It:
  - requires `config.store is not None` (else `ValueError` — nothing to adopt);
  - requires the study to **exist** at `config.store.path` (else a clear `ValueError`, not a leaked optuna
    `KeyError`, G-SPEC-24);
  - stamps `ruthless_identity` in **one** write;
  - **refuses a study that already carries `ruthless_identity`** (matching or not), so it can never overwrite;
  - logs the adoption (path + `objective_id`) through `ruthless._logging`.
- After adoption, every resume is fully guarded, exactly as for stores created under 0.7.0.
- **Not** a config flag (e.g. `assume_objective_match=True`): a standing flag gets copied into every config
  and never removed (Hyrum's Law), quietly disabling the guard for the next legacy store the caller points
  at. A decision made once per store belongs in a one-shot call, not a persistent field.
- **Placement:** `adopt_legacy_store` stamps an Optuna study, so it needs `optuna` and therefore cannot be a
  top-level `ruthless.` name — `import ruthless` must not pull `optuna` (the lean-install guard,
  `test_top_level_import_does_not_require_optional_extras`). It sits beside `OptunaStrategy` (also not in the
  top-level `__all__`); `optuna` is imported lazily inside it.
- **Grid is unaffected:** grid stores are new in 0.7.0 and are always created with an `objective_id`.
- **Breaking change (owner-approved):** configs that set a store without `objective_id` now fail
  construction. Updated in this release (ruthless): `tests/test_optuna_config.py:23`,
  `tests/e2e/test_optuna_resume_gate.py:24` (§4).
- **Downstream notice (G-SPEC-20) — TF-58's migration, not this session's:** silly-kicks builds `StoreConfig`
  at `calibration/_spaces.py:48,73,116`, `train_xshot_occurrence.py:202`, `train_xcross_attempt.py:270`,
  `test_xshot_occurrence_integration.py:69` — all break at `>=0.7.0` until `objective_id` is supplied. This
  session does not edit silly-kicks (repo-boundary rule); the TF-58 session carries the migration when it
  raises the floor. Any lakehouse `StoreConfig` users are likewise their sessions' migration.

**Full Optuna resume-identity guard (G-SPEC-18, owner-approved).** Beyond `objective_id`, Optuna now also
guards `config_fingerprint` (above), so a resumed study whose `param_space`/`sampler`/`direction`/`metric`
differs from the config **fails loud** rather than silently continuing a differently-shaped study. This
closes the pre-existing 0.6.0 gap and makes Optuna resume fail-closed and symmetric with Grid. `n_trials` and
`warm_start` are deliberately **not** part of the identity (they are resume knobs, not identity — see the
exclusion set above).

---

## 4. Tests (TDD — each written failing first)

Locations: config `tests/test_grid_config.py`; enumeration `tests/strategies/grid_/test_grid_plan.py`;
strategy `tests/strategies/grid_/test_grid_strategy.py`; grid resume `tests/e2e/test_grid_resume_gate.py`;
store golden `tests/test_grid_store_golden.py`; Optuna identity extends
`tests/e2e/test_optuna_resume_gate.py`; public/CLI extend existing files.
`tests/strategies/grid_/__init__.py` is added (siblings have one). Names lowercase (N802).

**Config:**
1. loads `cartesian`/OAT/`points`.
2. `FloatRange` rejected (names `Choice`).
3. empty/omitted `param_space` rejected.
4. OAT: missing/incomplete/extra-key `baseline` rejected; value-not-a-level rejected incl. type-strict
   `3.0` vs `3` and `True` vs `1`.
5. `points`: missing; wrong keys; value-not-a-level (type-strict) rejected.
6. cross-field: `baseline` on non-OAT; `points` on non-`points` rejected.
7. size guard: `IntRange(0, 10**12)` raises a **fast** `ValueError` with bounded memory (G-SPEC-01 gate).
8. boundary: count `== max_points` constructs; `+1` raises (G-SPEC-08).
9. fingerprintability: a `numpy.int64` `Choice` level rejected at construction (G-SPEC-07).
9b. hashability (G-SPEC-17): a `set` `Choice` level rejected at construction (unhashable); a `frozenset`
    level constructs.

**Enumeration:**
10. `cartesian` exact ordered list; count `== product`; `IntRange` `lo..hi` inclusive.
11. OAT: baseline first; per-param other-levels in order; baseline once; count `== 1 + sum(level_count-1)`.
12. `points` as given.
13. dedup: duplicate `points` entry collapses; OAT swap reproducing another point collapses; ids `g0..g{n-1}`.
14. determinism: two calls identical.

**Strategy:**
15. `InProcessBackend`; `best` for MIN and MAX; tie → first.
16. `history` full metrics per distinct point.
17. `diagnostics`/`provenance` exact (no `seed`).
18. non-finite scored → `FatalEvaluationError` propagates; not in history.
19. `CachedObjective`: extra-param → `ValueError`; happy path `prepare()` once + `evaluate_patch`;
    `assert_cache_equivalence`; typed `_s: SearchStrategy = GridSearchStrategy(_cfg())` (pyright gate).

**Grid resume (`test_grid_resume_gate.py`):**
20. durability/partial (G-SPEC-02/03): objective raises at point k on run 1; run 2 has `n_from_store == k`
    and evaluates N−k; `history` spans N. Public surface only; no pre-seeding.
21. full resume: rerun does zero evaluations, `n_from_store == N`, identical `history`/`best`.
22. `_tag`-typed levels with a store (G-SPEC-04): `Enum`/`PurePath`/`datetime`/`frozenset` `Choice` levels run
    + resume (hashable **and** fingerprint-able; a `set` is excluded by test 9b).
23. numpy auxiliary metric with a store (G-SPEC-14) persists + resumes.
24. objective meta-guard: rerun with changed `store.objective_id` raises; changed `store.path`/`max_points`
    does not.
25. config meta-guard + schema_version mismatch raise (G-SPEC-11).
25b. corrupt `grid_meta` (a missing required row) raises `ValueError` naming the path (meta-atomicity guard,
    §3.3).
26. `mkdir`: non-existent `store.path` dir created (G-SPEC-11).
27. cached + fully resumed: `prepare()` called **zero** times.

**Store golden (`test_grid_store_golden.py`, ADR-003 enforcement):**
28. pins the `grid_meta`/`grid_result` table DDL and the `schema_version` constant; a schema change fails
    until the version is bumped (style of `test_fingerprint_golden.py`).

**Optuna store identity + legacy adoption (`test_optuna_resume_gate.py`):**
29. resume with a **matching** `objective_id` **and** matching config proceeds as today (regression:
    existing resume behaviour unchanged when both identities match).
30. resume with a **mismatched** `objective_id` raises `ValueError` before `optimize`.
30b. resume with a **mismatched** `config_fingerprint` — a changed `param_space`/`sampler`/`direction`/`metric`
    on the same store — raises `ValueError` before `optimize` (G-SPEC-18). Also: changing only `n_trials`
    (more budget) or `warm_start` does **not** raise (they are excluded from the identity).
30c. a **malformed** `ruthless_identity` (not a dict, missing a sub-field, or `schema != 1`) on resume raises a
    defined `ValueError`, not an undefined comparison (G-SPEC-25).
31. resume of a **legacy study** (`ruthless_identity` absent **and ≥1 trial**, per §3.4/G-SPEC-19) raises `ValueError`, and
    the message contains the `adopt_legacy_store(config)` call to run. (The fixture must carry ≥1 trial, else
    it reads as a fresh study and is stamped, not raised.)
32. `adopt_legacy_store(config)` then resume **succeeds** (stamps `ruthless_identity`; identities match).
33. `adopt_legacy_store(config)` on an **already-stamped** study raises (never overwrites).
34. `adopt_legacy_store(config)` then resume with a config whose `objective_id` **differs** raises.
35. `adopt_legacy_store(config)` then resume with a config whose `param_space` (config_fingerprint) **differs**
    raises (the adopted config_fingerprint is enforced too).
35b. `adopt_legacy_store(config)` on a `config.store.path` with **no study** raises a clear `ValueError`
    (not a leaked optuna `KeyError`); on `config.store is None` raises `ValueError` (G-SPEC-24).

**Public + CLI + cross-cutting:**
36. `GridSearchStrategy`, `GridConfig` in `_EXPECTED_PUBLIC`; `adopt_legacy_store` importable from
    `ruthless.strategies.optuna_` (and **not** in the top-level `__all__`).
37. lean-install: `import ruthless; GridSearchStrategy` pulls no `optuna`/`openevolve`; importing
    `ruthless.strategies.optuna_` (for `adopt_legacy_store`) does not import `optuna` at module load (lazy).
38. CLI: a `grid` config runs end-to-end over `InProcessBackend`.
39. `StoreConfig` required-field: constructing a store dict without `objective_id` raises; the updated
    `test_optuna_config.py` builds it with the id.
40. `test_fingerprint_golden.py` stays green unchanged (grid does not touch `_tag`) — acceptance gate.

Gate: the full existing suite green **plus** the above (with the two Optuna store tests updated for the
required field).

---

## 5. Public API, versioning, release

### 5.1 Public surface
- `ruthless/__init__.py`: import `GridSearchStrategy` (from `ruthless.strategies.grid_`) and `GridConfig`
  (from `ruthless.config`); add both to `__all__` (ruff RUF022 keeps it alphabetised — just add the names).
- `ruthless/config/__init__.py`: re-export `GridConfig`; add to `__all__`.
- `tests/test_public_api.py`: two `_EXPECTED_PUBLIC` entries.

### 5.2 Config + strategy wiring
- `ruthless/config/common.py`: `StoreConfig` gains required `objective_id: str` (+ non-empty validator).
- `ruthless/config/strategies.py`: add `GridConfig`; union →
  `RandomConfig | EvolveConfig | OptunaConfig | GridConfig`.
- `ruthless/config/space.py`: add `levels()`, `level_count()`, `grid_plan_size()`, `is_level()`.
- `ruthless/strategies/optuna_/strategy.py`: record + guard the single `ruthless_identity` study attr
  `{objective_id, config_fingerprint}` (fresh → stamp once; guarded → compare both sub-fields, mismatch
  raises; legacy attr-less + ≥1 trial → raise);
  `config_fingerprint = fingerprint_model(cfg, exclude={"store","n_trials","warm_start"})` (§3.4). `optuna_`
  does not import `fingerprint_model` today; adding the import is an allowed strategy→core edge (it is public
  core, `ruthless._fingerprint`) and pulls in no third-party dependency (G-SPEC-23).
- `ruthless/strategies/optuna_/`: add `adopt_legacy_store(config: OptunaConfig)` (in `strategy.py` or a small
  sibling module), re-exported from `optuna_/__init__.py`; `optuna` imported lazily inside it. **Not** added
  to the top-level `ruthless.__all__` (lean-install guard).

### 5.3 CLI
- `ruthless/cli.py`: one `_STRATEGY_BUILDERS` row — `GridConfig: lambda cfg, seed: GridSearchStrategy(cfg)`.

### 5.4 Version, CHANGELOG, ADR-003, AGENTS.md, release flow
- **Version:** `ruthless/_version.py` `0.6.0 → 0.7.0`, same commit as the work.
- **CHANGELOG `[0.7.0]`:**
  - `### Added`: `GridSearchStrategy` + `GridConfig` (three designs, resume, size guard, CLI).
  - `### Changed`/`### Breaking` — name each (G-SPEC-22):
    - `StoreConfig.objective_id` is now **required** (a store without it fails construction).
    - **Optuna resume is now identity-guarded:** a resume whose objective (`objective_id`) **or** config
      (`param_space`/`sampler`/`direction`/`metric`) differs from the stored study now **raises** (0.6.0
      continued silently). Remedy: use a new `store.path` for a genuinely different objective/config.
    - Resuming a **legacy** (≤0.6.0, attr-less) Optuna store now **raises**; one-line remedy
      `ruthless.strategies.optuna_.adopt_legacy_store(config)` (§3.4).
    - State that `fingerprint` caches are **not** invalidated (digest path untouched) but that a store's `fp`
      key depends on the digest (ADR-002/ADR-003), so a future `_tag` change would invalidate grid stores.
- **ADR-003** (`docs/adr/ADR-003-grid-resume-store-schema.md`) — records: the `grid_meta`/`grid_result`
  schema + columns + `schema_version`; the row key `fingerprint(params)` and its dependence on ADR-002 (a
  `_tag` change invalidates grid stores and must say so in the CHANGELOG — recorded where the next person to
  edit `_fingerprint.py` will find it); store identity = `config_fingerprint` + `objective_id`, honoured by
  **both** strategies (Grid via its sqlite meta rows; Optuna via one `ruthless_identity` study attr carrying a
  `schema` version sub-field — a malformed or unknown-`schema` identity fails loud, G-SPEC-25 — G-SPEC-18);
  legacy (attr-less) Optuna studies **fail-closed** on resume with an explicit one-shot
  `adopt_legacy_store(config)` remedy (no silent migration, no config flag); params encoding = no stored params (G-SPEC-04); durability = commit per point (G-SPEC-02);
  stability stance = a schema change bumps `schema_version`, an older store fails loud with no silent
  migration, and under 0.x takes the minor slot with a CHANGELOG line stating it invalidates existing stores;
  scope = single-process, sqlite only, multi-process resume deferred library-wide. Enforced by the golden
  test (test 28).
- **AGENTS.md:** bump "Ships at `0.6.0`" → `0.7.0`; add the ADR-003 line under "Architecture decisions".
  Keep `tests/test_agents_md_budget.py` green (the plan checks the budget before adding lines).
- **Flow:** `feat/grid-strategy` → local five-command gate green → `/final-review` (regenerates the C4) →
  **single commit on the owner's explicit approval** → PR → merge → `v0.7.0` tag → OIDC publish (owner).
  Independent review of this spec **and** the plan precedes implementation. TF-58 commit 1 raises the
  silly-kicks floor to `>=0.7.0`.

---

## 6. Non-goals

- No native float-grid spec (floats are `Choice`, decision 4) — a possible later minor.
- No parallel/concurrent dispatch (library-wide deferral, §2.4).
- No RNG/`seed` (decision 9).
- No new `StoreConfig` backend (sqlite only, matching `optuna`).
- No change to `random_`/`evolve_`, to `Result`/`report.py`, or to the `fingerprint`/`_tag` digest path.
  (`optuna_` **is** changed — full resume-identity guard + `adopt_legacy_store`, decision 12/G-SPEC-18;
  `space.py` gains additive helpers; `common.py`'s `StoreConfig` gains one required field.)

## 7. Rejected alternatives

- `OptunaConfig.sampler="grid"` — Cartesian-only; cannot satisfy Appendix A; adds `optuna` (decision 1).
- Dedup on `Candidate` equality — `id` is part of identity (§0.1 fact 4).
- `value in levels` membership — conflates `3`/`3.0`, `True`/`1` against `_tag` (§1.3).
- Materialising `levels()` for the size guard — the rev-1 defect (G-SPEC-01); guard uses `level_count`.
- Storing `params_json` — cannot encode `_tag` `Enum`/`PurePath`/`datetime`/`set` levels (G-SPEC-04).
- **`objective_id` optional / on GridConfig only** — an optional default re-opens the trap, and a
  Grid-only field leaves Optuna's identical trap open (owner directive: required, on `StoreConfig`,
  honoured by both).
- Commit-at-close durability — loses all points on a mid-run crash (G-SPEC-02); each `put` is committed
  before the next point.
- **Stamp-and-proceed on a legacy Optuna store** — permanently blesses a store the guard never checked (the
  exact hole); rejected for the fail-closed raise + one-shot `adopt_legacy_store` (§3.4).
- **A config flag** (`assume_objective_match=True`) for legacy adoption — a standing field is copied
  everywhere and never removed (Hyrum's Law), silently disabling the guard; a once-per-store decision belongs
  in a one-shot call (§3.4).
- **Refusing every legacy store with no remedy** — discards completed trials even when the objective is
  unchanged; the adoption call preserves them at the cost of one deliberate assertion (§3.4).

---

## Appendix A — the interface contract TF-58 depends on (verbatim, handoff §4)

Reproduced verbatim (change-control sentence restored, G-SPEC-06). This spec **accepts** it in full; the
additions below are additive and weaken no clause.

> **4. The interface contract TF-58 depends on (MUST)**
>
> TF-58's spec pins exactly this. Any change to it needs the owner's approval and a note to the TF-58 session.
>
> 1. **Import surface:** `from ruthless.strategies.grid_ import GridSearchStrategy` and
>    `from ruthless.config import GridConfig`. `GridConfig` is a member of the `StrategyConfig` union with
>    `kind: Literal["grid"]`.
> 2. **`GridConfig` fields (minimum):** `metric: str`, `direction: Direction`,
>    `design: Literal["cartesian", "one_at_a_time", "points"]`, `param_space: dict[str, ParamSpec]`,
>    `baseline: dict[str, Any]` (required for `one_at_a_time`), `points: list[dict[str, Any]]` (required
>    for `points`), `store: StoreConfig | None = None`.
> 3. **Validation fails loud, at construction:**
>    - a `FloatRange` in `param_space` raises (a grid needs discrete levels; discrete floats are `Choice`);
>    - `one_at_a_time` without a `baseline`, or with a baseline key missing from `param_space`, or with a
>      baseline value that is not one of that parameter's levels, raises;
>    - a `points` entry whose keys differ from `param_space`'s keys, or whose value is not one of that
>      parameter's levels, raises;
>    - `baseline` given for a non-OAT design, or `points` given for a non-`points` design, raises (a
>      silently ignored field is a bug).
> 4. **Enumeration:**
>    - `cartesian` is the full product of every parameter's levels (`Choice.choices` in order; `IntRange`
>      expanded `lo..hi` inclusive);
>    - `one_at_a_time` is the baseline point plus, for each parameter in `param_space` order, the baseline
>      with that one parameter replaced by each of its other levels;
>    - `points` is the list as given.
>    The order is deterministic, candidate ids are stable across runs, and **each distinct parameter dict
>    is evaluated exactly once** (the OAT baseline appears on every line but is evaluated once;
>    de-duplicate on the hashable `Candidate` params).
> 5. **Evaluation:** through the `ComputeBackend` port, like `RandomSearchStrategy`. If the objective is a
>    `CachedObjective`, `prepare()` runs once and every point goes through `evaluate_patch`; tuning a param
>    not in `patch_params` raises (same rule as `OptunaStrategy`).
> 6. **Resume:** with `store` set, completed evaluations persist; a rerun evaluates only the points not yet
>    completed; no point is lost or evaluated twice. Key the store by the candidate fingerprint from
>    `ruthless._fingerprint`.
> 7. **`Result`:** `best` by `metric`/`direction`; `history` holds **every** evaluated point with its full
>    `metrics` dict (TF-58 builds its sensitivity artifact from `history`, not only `best`); `diagnostics`
>    includes at least `design`, `n_points`, `n_unique`; `provenance` includes `"strategy": "grid"`, the
>    design, the direction and `**code_identity()`.
> 8. **Release:** ruthless **0.7.0** on PyPI, published by the owner. silly-kicks raises its
>    `ruthless-efficiency[optuna]` floor in the `[calibration]` and `[train]` extras to `>=0.7.0` in TF-58
>    commit 1.

**Where this spec adds to the minimum (change-control list; owner-approved; TF-58 must note the starred items):**

1. Candidate ids pinned `g{index}` in the deterministic de-duplicated plan; dedup on `fingerprint(params)`
   (§2.1). *Additive; satisfies §4.4.*
2. Type-strict, non-materialising level membership (§1.3). *Additive; refines §4.3.*
3. OAT baseline keys required to equal `param_space` keys (§1.2). *Additive; refines §4.3.*
4. `max_points` field, default `100_000` (§1.4). *Additive field.*
5. Grid store config-identity meta-guard (§3.3). *Additive; strengthens §4.6.*
6. Lazy `prepare()` — zero calls on a fully-resumed run (§2.5). *Refines §4.5.*
7. **★ `StoreConfig.objective_id`, required whenever a store is set (§3.4).** Changes `StoreConfig`'s shape
   (§4.2 lists `store: StoreConfig | None`); TF-58 must set `objective_id` on the store, and **must bump it
   per shard generation** or a resume reuses stale scores. The per-point row key (§4.6) is unchanged.
   *Owner-approved; note to TF-58.*
8. **★ Optuna gains a full resume-identity guard** (§3.4, G-SPEC-18) — both `objective_id` and
   `config_fingerprint` (`param_space`/`sampler`/`direction`/`metric`); a cross-cutting change beyond grid.
   Legacy Optuna studies fail-closed on resume with a new public `adopt_legacy_store(config)` remedy (in
   `ruthless.strategies.optuna_`). *Owner-approved.*
9. **★ ADR-003 + a golden store-schema test** (§5.4). *Owner-approved.*
