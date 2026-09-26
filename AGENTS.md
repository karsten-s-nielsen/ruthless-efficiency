# ruthless-efficiency

A general optimisation/search substrate: a pure hexagonal core + pluggable search strategies +
pluggable compute backends. Ships at 0.6.0 (0.x — API unstable). On release, bump the one line in
`ruthless/_version.py`; the only remaining hand-edits are the "Ships at" line here and the CHANGELOG
section header.

The phase-by-phase history, the scope map, and the *why* behind every convention live in
`docs/context/` (see Reference docs). This file is the terse, always-loaded set of enforceable
invariants and pointers.

## Architecture

- **Hexagonal.** The pure core defines the ports and value types: ports `Objective`, `SearchStrategy`, `ComputeBackend` (structural `Protocol`s); value types `Candidate`, `Metrics`, `Evaluation`, `Result`. Core deps: `pydantic` + `numpy` + `pyyaml`.
- **Dependency direction.** A strict one-way dependency direction: strategies/backends depend on the core, never the reverse or each other. Enforced by `import-linter` (3 contracts incl. `core-isolation`); `lint-imports` stays green.
- **Strategy loop.** No template-method driver: each strategy owns its loop and returns a `Result`. See docs/context/architecture-rationale.md.
- **Backends are the inter-candidate dispatch path** — one evaluation, one compute resource, on `evaluate(candidate, objective, *, timeout) -> Metrics`. See docs/context/architecture-rationale.md.
- **Timeout contract.** Cross-process backends enforce the per-candidate timeout; in-process ones accept it for port compatibility but document-and-ignore. See docs/context/architecture-rationale.md.
- **Unified error model.** Backends never record a sentinel score — they raise `TransientEvaluationError` or `FatalEvaluationError`; `EvolveEvaluator` alone maps failure to the sentinel. See docs/context/architecture-rationale.md.

## Key conventions

- **Scored-metric finiteness only.** `classify_metric` raises on an inf/NaN optimisation-target; diagnostic metrics may be non-finite — never pass them to `classify_metric`.
- **Fatal errors vs. penalties are distinct.** Fatal failures (`ruthless.errors`) are never recorded as a score; degenerate-but-valid candidates get a finite `penalty_metrics`.
- **Candidate is hashable** (frozen; order-independent `__eq__`/`__hash__` over `params`) so it is a cache/dedup key. Do not mutate `params`.
- **`Result` is treat-as-immutable once returned** by `SearchStrategy.run`.
- **`map_work_units` always attempts EVERY unit** — `workers` is a speed knob; failures aggregate into `WorkUnitMapError`, a dead pool raises `BrokenExecutor`. See docs/context/cache-identity-and-fingerprint.md.
- **Cache identity is a declared EXCLUSION set**, never an inclusion list; `ruthless._fingerprint` is the one impl, `fingerprint_model(exclude=...)` fails-closed. See docs/context/cache-identity-and-fingerprint.md and ADR-002.
- **`_tag` branch order is load-bearing:** `Enum` first, `bool` before `int`, `datetime` before `date`. See docs/context/cache-identity-and-fingerprint.md.
- **Digest bytes are a compatibility contract** (public since 0.4.0; `test_fingerprint_golden.py` pins them); no .md file may quote a digest (enforced by `test_docs_no_digest_literals.py`). See docs/context/cache-identity-and-fingerprint.md and ADR-002.
- **`pydantic` is pinned `<3`** because `fingerprint_model` digests model_dump(). See docs/context/cache-identity-and-fingerprint.md.
- **Provenance never overclaims** — `ruthless._provenance.code_identity` never emits a SHA without a tree state. See docs/context/cache-identity-and-fingerprint.md and ADR-002.
- **`__version__` lives in ruthless/_version.py** — the single source; `pyproject.toml` sets `dynamic` and `hatchling` reads it, so packaging and runtime cannot drift.
- **Config is a discriminated-union surface:** `RuthlessConfig` carries a discriminated strategy union and a param-space union (`FloatRange` / `IntRange` / `Choice`).
- **Library never configures root logging.** Use `ruthless._logging.get_logger`; consumers own handlers.
- **The CLI objective loader is trusted-config-only.** `resolve_objective` uses `importlib` + `getattr` (never `eval`) and `isinstance`-checks against `Objective`.

## Key Phase-2 conventions

- **`CachedObjective`** — full `evaluate` + `prepare()` + `evaluate_patch` + `patch_params`; `OptunaStrategy` uses the fast path and rejects tuning any param not in patch_params (`assert_cache_equivalence` proves fast==full). See docs/context/phases-and-scope.md.
- **`OptunaStrategy` resume:** no lost/dup trials + monotone + converge (NOT trajectory identity); `best`/`history` from `study.trials`; SQLite is single-process. See docs/context/phases-and-scope.md.
- **`OptunaStrategy` observer:** fires per completed trial; `ProgressEvent.number` is study-global; a raising observer is logged-and-isolated; `Observer.__call__` is positional-only. See docs/context/phases-and-scope.md.
- **Group-scoring was deferred** (the consumer runs CV in its own `score_fn`). See docs/context/phases-and-scope.md.

## Local quality gate (mirrors CI exactly)

Run all five before declaring work done (Shift Left — catch it locally, not in CI):

```bash
uv run ruff check ruthless tests
uv run ruff format --check ruthless tests
uv run pyright
uv run lint-imports
uv run pytest -v
```

`pyright` runs on both `ruthless` and `tests` (`[tool.pyright] include`).

## Workflow conventions

- **TDD** — write the failing test first, then implement (red → green per change).
- **`/final-review`** is the mandatory pre-commit quality gate for every work cycle (it also generates/updates the C4 diagram at `docs/c4/architecture.html`).
- **No commit without explicit user approval.**
- **No git worktrees** — project convention; work on a feature branch in this repo.

## Tech stack

Python ≥3.10 (CI on 3.10), pydantic v2, numpy, pyyaml. numpy (`<3`, pinned for RNG-stream stability of
the determinism gate) and pydantic (`<3`, see Key conventions). Dev: pytest + hypothesis, ruff,
pyright, import-linter, hatchling.

## Reference docs

- Spec: `docs/superpowers/specs/2026-05-28-optimization-engine-carveout-design.md`
- Phase 1A/1B plans: `docs/superpowers/plans/2026-05-28-ruthless-efficiency-phase1a.md`,
  `docs/superpowers/plans/2026-05-28-ruthless-efficiency-phase1b.md`
- Phase 2 plan: `docs/superpowers/plans/2026-05-28-ruthless-efficiency-phase2-library.md`
- Error model + cache identity:
  `docs/superpowers/specs/2026-07-29-parallel-error-model-and-cache-identity.md`,
  `docs/superpowers/plans/2026-07-29-parallel-error-model-and-cache-identity-plan.md`
- Public fingerprint + digest stability:
  `docs/superpowers/specs/2026-07-30-public-fingerprint-and-digest-stability-design.md`,
  `docs/superpowers/plans/2026-07-30-public-fingerprint-and-digest-stability-plan.md`
- Context (the *why* / history): `docs/context/phases-and-scope.md`,
  `docs/context/architecture-rationale.md`, `docs/context/cache-identity-and-fingerprint.md`

## Architecture decisions

- `docs/adr/ADR-001-ast-sandbox-security-model.md` — AST allowlist for evolve Level-2 code evolution.
- `docs/adr/ADR-002-cache-identity-and-code-provenance.md` — cache identity as a core primitive with an exclusion-set scope; provenance never emits a SHA without a tree state.
