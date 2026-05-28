# Optimization Engine Carve-Out — Design

| Field | Value |
|---|---|
| **Date** | 2026-05-28 |
| **Status** | In review (rev 3 — incorporates lakehouse review (C1–C3/H1–H3/M1–M4) + silly-kicks review (H1–H4/M1–M5/L1–L5); §4/§9 note `RandomSearchStrategy` per the Plan-1A back-port; §1/§8/§11 reconcile evolve = hybrid (our orchestration + OpenEvolve loop) per Plan-1A review C-A) |
| **Author** | Karsten Skyt |
| **Name** | **Ruthless Efficiency** (decided 2026-05-28) — Spanish Inquisition line (*"Our chief weapons are … ruthless efficiency"*), in the iconic-line→function house style (cf. "Right! **Luxury!**", "**Pining for the** Fjords"). Repo `ruthless-efficiency`; pip + import package `ruthless`. |
| **Scope** | Extract the optimization/search substrate (`src/evolve/` + the Optuna orchestration currently embedded in `scripts/run_tc3_calibration.py`) into a standalone, general-purpose library. Domain targets and data pipelines stay in their consumer repos. |

## 1. Problem

The lakehouse contains two mature, independently-built implementations of the *same abstract
activity* — "optimise a parameterised objective, resumably, across compute, with config +
diagnostics" — and a third consumer is now emerging:

1. **`src/evolve/`** (5,449 LOC) — LLM-driven evolutionary *structural* search. **It is a HYBRID
   (verified): the evolutionary loop itself (islands / migration / mutation / RNG) is the
   third-party `openevolve` library** (`runner.py` calls `openevolve.run_evolution`); **what is
   *ours* is the orchestration around it** — the multi-backend compute pool (local CUDA / SSH / HF
   Jobs / Docker), the AST-allowlist code sandbox (`code_validator`, ADR-001), config translation,
   search-space validation, and seed evaluation/caching. Our `EvolveEvaluator` is an OpenEvolve
   evaluator *plugin* that validates candidate code (our sandbox) and dispatches training to our
   `BackendPool`. Used to search ScoutGPT / Football2Vec architectures. **Consequence for this
   carve-out (resolves plan-review C-A): we *extract our orchestration* and *adopt OpenEvolve* for
   the loop — we do NOT reimplement islands. So the "hard-won asset" §3 preserves is the
   orchestration (true); but evolve determinism/resume is bounded by OpenEvolve, NOT by us (see §8).**
2. **`scripts/run_tc3_calibration.py`** (2,092 LOC) — Optuna TPE *scalar/structural calibration*
   (resumable SQLite-backed studies, warm-start, staged study pipeline, group-stratified CV
   scoring, invariant-cache/per-trial-patch decomposition, degenerate-trial guards, diagnostics).
   Calibrates **silly-kicks** tracking parameters (`infer_ball_carrier` tolerance/beta/gamma,
   `LinkParams.k3`, off-ball-run windows) against lakehouse production data.
3. **silly-kicks** — has a backlog of parameters explicitly deferred to Optuna calibration
   (`_linkage.py` LinkParams, `_ball_carrier.py`, `pressure/`, `pitch_control/`, `vaep/` — see
   TODO TF-24/TF-25). It is *running Optuna live now* but cannot own its calibration cleanly
   because the orchestration lives in a lakehouse script that reaches into silly-kicks.

Three problems follow:

- **No reuse path.** A soccer-analytics practitioner (or silly-kicks itself) who wants
  "evolutionary architecture search" or "resumable multi-backend hyper-parameter calibration"
  must vendor the whole lakehouse. The genuinely general, hard-won asset — *the orchestration* —
  is trapped.
- **Inverted ownership.** TC3 tunes silly-kicks parameters from a lakehouse script. silly-kicks
  should own its own calibration; today it can't without duplicating the study scaffolding.
- **Duplicated substrate.** evolve and TC3 independently reinvent resume, warm-start, parallel
  dispatch, results reporting, and diagnostics. New strategies (e.g. CMA-ES, grid) would
  reinvent them again.

## 2. Goals / Non-goals

**Goals**
- Extract a **general-purpose optimisation substrate** as a standalone, separately-versioned
  library with **zero dependency on the lakehouse, silly-kicks, soccer, or any domain**.
- Ship **two search strategies** on the substrate: `evolve` (LLM structural search) and `optuna`
  (Bayesian/sampler calibration), each behind a common `SearchStrategy` port.
- Preserve the **multi-backend compute orchestration** ("any combination of local GPUs + SSH +
  HF Jobs + Docker") as a first-class, **optional** capability — installable but not mandatory.
- Hexagonal architecture: pure domain core + ports + swappable adapters. Lean default install;
  heavy/optional deps behind extras.
- Make the lakehouse evolve targets, TC3 calibration, and silly-kicks calibration all
  **consumers** of the library, with their domain objectives staying in their own repos.
- Best-practice packaging, typing, and **TDD/E2E throughout** (unit per component; e2e for a
  full resumable study and a full evolve run with trivial in-process objectives; differential
  reproduction of existing TC3/evolve results as golden behaviour).

**Non-goals**
- Moving ScoutGPT / Football2Vec model architectures or training pipelines (those are
  soccer-specific consumers; see §10 — they stay, implementing the objective port). A public
  `soccer-models` showcase repo is a *separate, later, consumer-driven* decision.
- Changing optimisation *results* — extraction is behaviour-preserving; calibration outputs and
  evolve search behaviour must reproduce within tolerance.
- Re-running any calibration/search as part of the carve-out.
- Choosing the repo name (parked).

## 3. Evidence basis (what is general vs coupled — verified)

**`src/evolve/` is ~95% domain-agnostic already.** Grepping every import, the *only* lakehouse
coupling is:
- `backends/hf_jobs.py:26` → `from shared.wheel import WHEEL_BASE_URL` (one line — the wheel the
  HF-Jobs remote installs). Must become **injected config** ("what package does the remote
  install?").
- `config.py` `EvalConfig.dataset` default = `"luxury-lakehouse/scoutgpt-training-data"` (a
  default string — leaves the library).
- `targets/scoutgpt/` and `targets/football2vec/` import `analytics.*` / `ingestion.*` — these
  are the **lakehouse-specific problems**; they stay in the lakehouse as consumers.

Everything else — `runner.py`, `config.py`, `backends/{base,pool,local_cuda,remote_ssh,docker}.py`,
`code_validator.py` (AST sandbox, ADR-001), `evaluator.py`, `remote_worker.py` — has zero
lakehouse imports. The `ComputeBackend` Protocol and `BackendPool` (comma-separated type string →
priority-ordered concurrent pool) are already clean and general.

**TC3 cleanly separates generic orchestration from domain glue.** From a full read:

| Generic (→ substrate) | Domain glue (→ stays in consumer) |
|---|---|
| Resumable study: `create_study(storage=sqlite, load_if_exists=True)` + `remaining = n_trials - len(study.trials)` | `_pull_provider_data_sql` (Databricks), bronze→frames conversion (`ingestion.tracking_context`, `ingestion.spadl_adapter`) |
| Warm-start via `enqueue_trial(defaults)` (never regress below baseline) | `_enrich_match_with_params` / `_enrich_match_invariant` / `_patch_trial_columns` (silly-kicks chain) |
| **Staged pipeline** (stage 2 reads stage 1 best params) | VAEP labels, xT fit, XGBoost Brier scoring |
| **Invariant-cache / per-trial-patch** objective decomposition (~95% wall-time saved) | The specific params + ranges (tolerance_m, k3, …) |
| Group-stratified scoring (GroupKFold) — shipped as a *configurable utility* (`scoring.py`: caller chooses grouping key + weighting), NOT a core contract (M4) | Provider list, the "by-match"/equal-weight choices, `.tc3_cache` layout |
| Degenerate-trial guard (variance gate → `PENALTY_BRIER` sentinel) | |
| Diagnostics as `trial.set_user_attr` + post-hoc sensitivity scans + sub-group "needs own param" gate | |
| Results artifacts (JSON per stage, `SUMMARY.md`, provenance) | |
| Local parallel map (ThreadPool over work units) | |

**Confirmed two-tier demand:** TC3 runs **local-only** (ThreadPool, no SSH/HF-Jobs); evolve uses
the heavy backend pool for GPU candidate training. So the backend pool must be an **optional
extra**, not a core dependency — silly-kicks calibrating CPU scalars must not inherit
paramiko/huggingface_hub/docker.

## 4. Architecture — hexagon

```
ruthless/                         # DOMAIN — pure (pydantic, numpy). No optuna, no torch, no ssh.
  core/
    objective.py     # Objective port + Metrics (Phase 1, evolve-validated). CachedObjective is an
                     #   OPTIONAL param-search extension (Optuna-family; does NOT map to evolve) — Phase 2.
    strategy.py      # SearchStrategy port: strategy OWNS its loop — run(objective, *, backend, report) -> Result
    backend.py       # ComputeBackend Protocol + in-process backend + BackendPool (INTER-candidate dispatch across machines)
    result.py        # common Result (best, history, diagnostics, provenance) returned by run(); persistence is STRATEGY-owned (H1)
    config.py        # layered Pydantic: common block + strategy block (discriminated union)
    errors.py        # error taxonomy (M1): FATAL (crash/timeout/inf/NaN → retry-or-surface, never recorded)
                     #   vs DEGENERATE candidate (guards → penalty score, recorded to steer the sampler)
    parallel.py      # OPTIONAL intra-objective utility: parallel map over work-units (thread|process). NOT the
                     #   candidate-dispatch path (that's BackendPool). Consumer calls it inside its Objective (H4).
    report.py        # renders Result → standardized JSON + Markdown SUMMARY + provenance; strategy artifacts stay strategy-owned (L5)
    observability    # logging.getLogger("ruthless"); structured events: trial start/end, backend pick, error/retry, checkpoint (M3)
  strategies/
    random_/         # RandomSearchStrategy: minimal built-in, zero extra deps. First real SearchStrategy
                     #   caller (validates the port in Phase 1) + drives the dependency-free analytic golden.   [core]
    optuna_/         # OptunaStrategy: owns ask/tell loop + Optuna storage (resume = Optuna trial table);
                     #   warm-start enqueue, staged pipeline, CachedObjective, scoring utils      [extra: optuna]
    evolve_/         # EvolveStrategy: owns generational loop; island model + RNG/population checkpoint,
                     #   LLM candidate generation, AST code-exec sandbox (least-privilege — NOT core) [extra: evolve]
  scoring.py         # PROVIDED utility (not a core contract): group_stratified_cv(groups, equal_weight=...) — configurable (M4)
  backends/
    local_cuda.py  remote_ssh.py  hf_jobs.py  docker.py     # adapters             [extra: backends]
  cli.py           # thin: load config → build strategy + backend + store → run → report
```

**Dependency direction (enforced, e.g. import-linter):** `core` imports nothing from
`strategies`/`backends`. Strategies and backends depend on `core` only. No domain (soccer/lakehouse)
import anywhere. Consumers depend on `ruthless`; `ruthless` never depends on a consumer.

**Ports (the seams):**
- `Objective` (core, Phase 1) — `evaluate(candidate) -> Metrics`. The minimal port; validated by
  evolve in Phase 1.
- `CachedObjective` (Optuna-family extension, Phase 2 — H2) — adds `prepare(work_units) -> Invariant`
  (cached) + `evaluate_patch(invariant, candidate) -> Metrics` (the TC3 invariant/patch pattern,
  generalised). **It does NOT map to evolve** (evolve evaluates whole generated programs, not param
  patches), so it ships and is validated with `[optuna]` in Phase 2, not Phase 1. **Cache-correctness
  contract (H1):** a `CachedObjective` declares `patch_params: frozenset[str]`; **`OptunaStrategy`
  asserts `patch_params ⊆ param_space.keys()` at construction (M5)** and that every proposed
  candidate varies only `patch_params` — a config error, never a silent wrong score.
- `SearchStrategy` — **owns its own loop** (C1): `run(objective, *, backend, report) -> Result`.
  Optuna drives via ask/tell with its study owning trial state + storage; evolve drives generationally
  (generation → evaluate → select → migrate, with island RNG/population state). Core imposes **no**
  template-method driver — it provides *services* (parallel map, guards, reporting, error model) the
  strategy calls.
- `ComputeBackend` — `evaluate(candidate, ...) -> Metrics`, `available()`. `BackendPool` composes a
  priority-ordered set — this is the **inter-candidate** compute-dispatch path (across machines), the
  evolve mechanism. (Distinct from `parallel.py`, which is an **intra-objective** map a consumer's
  `Objective` may use internally — H4.) In-process backend is core; SSH/HF-Jobs/Docker are `[backends]`.
- **Persistence is strategy-owned — there is NO core `ResultStore` port (H1).** Optuna persists to its
  own storage (`sqlite://` single-process, or an RDB for concurrency); evolve persists a checkpoint
  dir carrying RNG + island state. Resume is therefore strategy-specific (consistent with C3). The
  unified surface for *reporting* is the common `Result` returned by `run()` — not a storage port.

**Error model (M1 — two distinct failure modes, kept separate):**
- **Fatal evaluation failure** — crash, per-candidate timeout, or an `inf`/`NaN` metric from a broken
  eval → classified transient (bounded retry; per-backend timeout = measured-per-eval × max × 2) or
  fatal (surface with candidate key). **Never recorded as a valid score** (per `orchestration.md`:
  "silent-inf metrics are always a bug").
- **Degenerate-but-evaluable candidate** — e.g. variance collapse, physically-impossible params → a
  **valid penalty score, deliberately recorded** (the `guards.py` sentinel, à la TC3 `PENALTY_BRIER`)
  so the sampler learns to avoid that region. This is *not* an error.

**Cancellation / graceful shutdown (M2):** on `SIGINT`/`SIGTERM` the strategy abandons the in-flight
candidate, ensures durable state, and exits cleanly so a later `run()` resumes. Optuna commits each
trial to storage on completion → only the in-flight trial is lost; evolve bounds loss by
`checkpoint_interval`. The resume tests (§8) exercise exactly this path.

**Observability (M3):** the library logs via `logging.getLogger("ruthless")` with structured events
at trial start/end, backend selection, error/retry, and checkpoint. Consumers attach handlers /
`basicConfig`; the library never configures root logging.

**Key invariant:** the consumer writes **only** the `Objective` (its candidate/param space, and for
`CachedObjective` the `patch_params` it varies). Everything else — search loop, resume, warm-start,
staging, candidate dispatch, error handling, cancellation, diagnostics, reporting — is the library.
This is what silly-kicks gets that it can't have today.

## 5. Configuration

Today's `EvolveConfig` bakes evolve-specifics (`llm:`, `evolution:`, `fitness:`) at top level. The
substrate needs **layered config** — a common block plus a discriminated strategy block:

```yaml
objective: my_pkg.objectives:carrier_accuracy   # import path to the consumer Objective
seed: 42
parallelism: { workers: 4 }                      # local; or backend: "local_cuda,hf_jobs"
store: { kind: sqlite, path: results/study.db }  # or { kind: checkpoint_dir, path: ... }
strategy:
  kind: optuna                                   # discriminator
  n_trials: 100
  direction: minimize
  sampler: tpe
  warm_start: { tolerance_m: 3.0, beta: 0.5 }    # enqueue baseline first
  param_space: { tolerance_m: [1.0, 8.0], beta: [0.0, 2.0] }
# strategy: { kind: evolve, iterations: 150, num_islands: 3, llm: {...}, code_evolution: true }
```

Pydantic models validate per-strategy. The HF-Jobs backend takes an injected
`remote_package` (replacing the `shared.wheel` import). YAML loader is retained from `EvolveConfig`.

**Construction (M2):** the **primary API is programmatic** — the consumer instantiates its
`Objective` and passes the object to `strategy.run(...)`; pyright verifies it satisfies the port.
The `objective: pkg:fn` import-string above is a **CLI-only convenience, documented "trusted config
only."** Threat model + mechanism (L3): it resolves via `importlib.import_module` + `getattr`
(**never `eval`**), and the resolved object is `isinstance`-checked against `Objective` before use;
`objective: os:system` would resolve a non-`Objective` and be rejected. A library that ships an AST
exec-sandbox must not make dynamic import-by-string its main entrypoint.

**Persistence config is strategy-scoped (H1):** the `store:` block is interpreted by the chosen
strategy — `optuna` reads an Optuna `storage` URL (`sqlite:///…`, or an RDB for concurrency); `evolve`
reads a `checkpoint_dir`. There is no core storage object passed to `run()`.

**Param-space validation (M5):** `OptunaStrategy` asserts `objective.patch_params ⊆ param_space.keys()`
at construction (for a `CachedObjective`), failing loudly rather than at trial time.

## 6. Packaging & extras

- `pip install ruthless` → core only (pydantic, numpy): Objective/Strategy/Store ports, config,
  in-process backend, parallel map, error model, reporting, guards. **No code-exec path (H3).**
- `ruthless[optuna]` → + optuna (OptunaStrategy + scoring/diagnostics helpers). **silly-kicks
  installs this** — lean, no SSH/HF/torch, no exec-sandbox.
- `ruthless[evolve]` → + LLM client deps (OpenAI/OpenRouter) **and the AST code-exec sandbox**
  (least-privilege: only the strategy that runs generated code carries the capability — H3).
- `ruthless[backends]` (or granular `[ssh]`/`[hf-jobs]`/`[docker]`) → paramiko, huggingface_hub,
  docker. **Lakehouse evolve installs `[evolve,backends]`.**

This keeps the boundary the evidence demands: heavy orchestration available, never mandatory.

## 7. Consumers & migration

1. **Lakehouse evolve targets** (`src/evolve/targets/*`) → import `ruthless`; each target's
   evaluator implements `Objective`; `targets/` stay in the lakehouse. The `shared.wheel` coupling
   becomes injected `remote_package` config.
2. **TC3 calibration** (`scripts/run_tc3_calibration.py`) → re-expressed as: a `CachedObjective`
   (the silly-kicks enrichment = invariant prep + k3/off-ball patch) + an `OptunaStrategy` +
   staged pipeline + group-scoring helper, all from the library. The Databricks pull and
   silly-kicks enrichment stay lakehouse-side. **~1,500 of its 2,092 lines become library calls.**
3. **silly-kicks** → installs `ruthless[optuna]`; owns objectives for its own params
   (`LinkParams`, `_ball_carrier`, `pressure`, `pitch_control`, `vaep`). No more lakehouse script
   reaching in.

## 8. Test strategy

**Honest framing (minor review note):** this is mostly **characterization + golden** of ~7,500 LOC
of *working* code, not greenfield TDD. So: **port the existing evolve/TC3 unit tests and keep them
green through the move**; add **goldens** for behaviour preservation; reserve **red-green TDD** for
the genuinely new code (layered config, generalized `CachedObjective` with `patch_params`, the
per-strategy run-loop, the error taxonomy, the store-delegation adapter).

- **Unit (pure, fast, no external services):**
  - config validation (discriminated strategy union; per-strategy required fields; HF `remote_package`).
  - `BackendPool` priority-queue dispatch + release ordering (port evolve's tests).
  - error taxonomy (M1): transient→bounded-retry, fatal→surface-with-key, **inf/NaN→raised, never recorded**;
    per-candidate timeout fires.
  - **resume — split by what each strategy can actually guarantee (C3):**
    - *evolve:* resume + determinism are **bounded by OpenEvolve** (the loop/RNG/island state are
      OpenEvolve's, not ours — C-A). We do NOT promise trial-for-trial identity. What we assert is
      that **our orchestration is preserved**: identical candidate code → identical sandbox verdict
      and identical `BackendPool` dispatch + metrics; and that an interrupted run resumes from
      OpenEvolve's own checkpoint without lost/duplicate work. (Same honesty posture as the Optuna
      RNG caveat below.)
    - *optuna:* the achievable contract — resume produces **no lost or duplicate trials**, monotone
      study growth, and convergence within tolerance. Trial-for-trial identity is **not** asserted
      because Optuna does not persist sampler RNG state across restart (see §11 risk). The test
      asserts the achievable contract and documents the non-determinism.
  - warm-start enqueue ordering; staged-pipeline best-param hand-off.
  - **`CachedObjective` correctness — two layers (H1/H3):** (1) the substrate **ships a reusable
    harness `ruthless.testing.assert_cache_equivalence(objective, candidates)`** that *consumers* call
    in their own suites to prove patch-only == full-recompute for *their* domain objective (the
    substrate cannot test consumer correctness — it has no consumer `Objective`). (2) the substrate's
    own property-based test (`hypothesis`) runs that harness against a **trivial in-repo objective**
    (e.g. `sum(params)`) over sampled candidates incl. range boundaries — validating the cache
    *dispatch + invalidation* (varying a param outside `patch_params` raises), not domain correctness.
  - guards: degenerate candidate → penalty sentinel; sanity-gate thresholds.
  - `OptunaStrategy` against a **trivial analytic objective** (minimise a quadratic): deterministic
    best within tolerance under fixed seed.
  - `EvolveStrategy` against a **fake LLM** (canned mutations) + in-process backend: generations,
    island migration, checkpoint, early-stopping — no GPU/network.
  - AST sandbox: allow-list pass/deny cases (port ADR-001 tests) — lives with `[evolve]`.
- **E2E (self-contained, no domain deps):**
  - evolve: a run produces best_program + OpenEvolve checkpoints; kill + resume continues from the
    OpenEvolve checkpoint with no lost/duplicate work (NOT trajectory-identity — C-A); our
    orchestration parts (sandbox verdict, BackendPool dispatch) are golden-tested separately with a
    fake loop, independent of OpenEvolve's stochastic search.
  - optuna: resumable study on a quadratic → run N/2, kill, resume; assert no-lost/dup trials +
    converges (the C3 optuna contract).
- **Behaviour preservation — TWO layers (H2):**
  1. **Standing CI gate — pure-substrate golden** on a fixed analytic objective (deterministic,
     **zero domain/silly-kicks dependency**). This is what proves the *orchestration* was preserved,
     and it never false-fails when a domain dependency moves.
  2. **One-time migration check — TC3 domain reproduction**, pinned to a **frozen silly-kicks
     version + frozen fixtures**, asserting reproduction of the existing study best-params +
     per-provider Brier within tolerance (`tc3_stage*.db` + `stage*_results.json` as oracle).
     **Explicitly NOT a recurring CI gate** — never gate the substrate on a silly-kicks-dependent
     Brier value (silly-kicks bumps constantly; that would conflate extraction correctness with
     domain drift). **Concrete artifact (L1):** `scripts/verify_tc3_migration.py` + committed frozen
     fixtures + a pinned silly-kicks version, with a runbook section ("run once at Phase 2 migration;
     re-run only when deliberately re-baselining"). Not "we'll run it sometime."
- **CI:** ruff + pyright (strict where feasible), pytest; `[optuna]`/`[evolve]`/`[backends]` each
  tested in their own matrix leg; coverage gate on `core`. **import-linter exact contracts (L2):**
  `core` ✗ imports `strategies.*` / `backends.*` / any consumer; `strategies.*` ✗ imports
  `backends.*` or another strategy; `backends.*` ✗ imports `strategies.*`. Layer-2 TC3 reproduction
  runs out-of-band, not on every push.

## 9. Sequencing (decomposition — each phase its own implementation plan)

This is a large carve-out; it decomposes into behaviour-preserving phases:

- **Phase 1 — Substrate + evolve.** Splits into two independently-shippable plans:
  - **Phase 1A — core + bootstrap.** Extract `core` (objective/strategy/backend/result/config/errors/
    parallel/report/guards/observability) + repo bootstrap (packaging, CI, import-linter) + a minimal
    built-in **`RandomSearchStrategy`** — a zero-dependency search that is the **first real
    `SearchStrategy` caller** (validates the port before any consumer pins it) and the driver of the
    dependency-free analytic golden (the standing CI gate). Acceptance: unit tests + analytic golden
    green; import-linter contracts (L2) green.
  - **Phase 1B — evolve + backends + consumer.** Add `EvolveStrategy` (a thin adapter over
    OpenEvolve — evolve depends on `openevolve`), `BackendPool` + SSH/HF-Jobs/Docker backends, and
    sever `shared.wheel` (inject `remote_package` — two touch points in `hf_jobs.py`: the import and
    the worker-script install spec + remote objective import path) and the dataset default.
    `CachedObjective` is **deferred to Phase 2** (Optuna-family, no evolve caller — H2). Lakehouse
    evolve becomes the first consumer (targets unchanged in behaviour). Acceptance: evolve fixed-seed
    trajectory golden green; lakehouse evolve run reproduces a golden trajectory.
  Phase 1 ships as **0.x** (ports not yet validated by Optuna/silly-kicks — H2/L4).
- **Phase 2 — Optuna strategy + TC3 migration.** Add `OptunaStrategy`, `CachedObjective`, staged
  pipeline, group-scoring + diagnostics helpers. Re-express `run_tc3_calibration.py` on the
  library. Acceptance: TC3 differential reproduces existing study results within tolerance.
- **Phase 3 — silly-kicks adoption.** silly-kicks depends on `ruthless[optuna]` and owns its
  parameter objectives (TF-24/TF-25 families). Acceptance: a silly-kicks calibration runs end-to-end
  using only the library + silly-kicks, no lakehouse import.

Plan 1A is written (`docs/superpowers/plans/2026-05-28-ruthless-efficiency-phase1a.md`); Plan 1B and
the Phase 2–3 plans get their own docs as they land.

## 10. Decisions & open questions

- **ScoutGPT / Football2Vec stay as consumers, not repos** (this round). Their architectures are
  pure and separable, but single-consumer, bespoke, and already HF-published — extraction now is
  premature. They implement the `Objective` port in place. A public `soccer-models` showcase repo
  is a separate, later decision. **CONFIRMED 2026-05-28.**
- **Repo bootstrap location — DECIDED:** the new repo exists locally at
  `D:\Development\karstenskyt__ruthless-efficiency` (with the standard `assets/` folder + hero image
  already added). Phase 1 implementation lands there, extracting code from the lakehouse.
- **Repo name — DECIDED: Ruthless Efficiency** (2026-05-28). Repo `ruthless-efficiency`; pip + import package `ruthless`.
- **Sandbox placement — DECIDED (H3): `[evolve]` extra, not `core`.** Least-privilege — only the
  strategy that executes generated code carries the exec capability; silly-kicks (CPU scalar
  calibration) never gets a code-exec path. Revisit only if a non-evolve consumer needs to exec.
- **Distribution — DECIDED (M4, refined by H2/L4): PyPI + SemVer, starting at 0.x.** Not the
  silly-kicks wheel-pin discipline (that's for private, fast-moving code). But **cut `1.0` only after
  Phase 3 validates the ports against all three consumers** — "1.0 from day one" with three-repo
  coupling forces either rapid major bumps or premature freezing. Pre-1.0: breaking changes are minor
  bumps (ports still settling). Post-1.0: ports are a public API with a published port-deprecation
  policy (breaking change = major bump + deprecation window, never silent).
- **Name discoverability (minor)** — `ruthless` is non-descriptive for public search; accepted
  tradeoff for the house-style win. Mitigate via PyPI keywords/description/classifiers
  (`hyperparameter-optimization`, `evolutionary-search`, `optuna`).
- **Optuna multi-backend** — TC3 is local-only today; the substrate *allows* dispatching Optuna
  trials over the backend pool, but no consumer needs it yet (YAGNI — ship the port, not a forced
  integration). **If enabled, Optuna concurrency requires an RDB storage (e.g. Postgres), not
  SQLite** (SQLite-under-concurrency hazard — see §11).

## 11. Risks

- **Behaviour drift during extraction.** Mitigated by the golden tests (§8): the existing TC3 study
  DBs are the optuna-side oracle; the evolve-side oracle is our orchestration (sandbox verdict +
  BackendPool dispatch) tested with a fake loop, **not** OpenEvolve's stochastic trajectory (C-A).
  Capture goldens before refactoring each consumer.
- **Over-abstraction of the strategies.** Mitigated by deriving the common ports *from real callers*:
  the `Backend`/`Objective` ports come from **our `EvolveEvaluator`** (a real caller — even though
  the loop it runs under is OpenEvolve's) **+ TC3**; the `SearchStrategy` port gains a third caller
  (`RandomSearchStrategy`) in Phase 1A before any consumer pins it. Not speculation.
- **Extras matrix complexity.** Mitigated by keeping `core` dependency-light and testing each extra
  in its own CI leg.
- **Cross-repo version coupling** (lakehouse + silly-kicks + future consumers pin `ruthless`).
  Mitigated by **SemVer on PyPI: 0.x while the ports are still being validated by the three
  consumers (through Phase 3), then 1.0 with a published port-deprecation policy** (breaking change =
  major bump + deprecation window, never silent — H2/L4/M4). Consumers add a runtime min-version
  assertion. Premature 1.0 is itself a risk here (forces rapid majors), hence the 0.x window.
- **Optuna resume is not trajectory-deterministic (C3).** Optuna does not persist sampler RNG state
  to storage, so a resumed TPE study generally does not reproduce an uninterrupted run
  trial-for-trial. The `OptunaStrategy` resume guarantee is therefore deliberately the weaker,
  *achievable* contract (no lost/duplicate trials + monotone growth + converge-within-tolerance,
  §8), documented as such so consumers don't assume determinism that isn't there. Only `evolve`
  (which checkpoints its own RNG/island state) offers trajectory identity.
- **SQLite study storage under concurrency.** Optuna's default SQLite storage is unsafe under
  concurrent writers. Single-process resume (the current TC3 pattern) is fine; if Optuna trials are
  ever dispatched concurrently over the backend pool (deferred — §10), the consumer MUST switch to
  an RDB store (Postgres). Documented at the config boundary.
- **CachedObjective silent-wrong-score (H1).** A consumer tuning a param that actually affects the
  cached *invariant* stage would get wrong scores. Mitigated by the declared `patch_params` set +
  the substrate-side assertion + the property-based equivalence test (§4, §8) — the failure mode is
  a loud config error, not a silent wrong result.
