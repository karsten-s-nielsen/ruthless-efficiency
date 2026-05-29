# Ruthless Efficiency — Phase 1B (evolve + backends + consumer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** rev 3 — incorporates the lakehouse-d32 second-pass polish (L-A `run()` asserts epochs/seed too, L-B hook import-strings type-checked on resolution, L-C `run()` rejects a non-RemoteObjective cleanly, + the infra-as-worst-score docstring note). rev 2 incorporated the first-pass review (H1/H2/M1/M2/M3/L1/L3); rev 1 was written against the as-shipped Phase 1A (`0.1.0`) + spec rev 3. Backend-port reconciliation is settled: **one `ComputeBackend` port** (see "Central design decision"). The reviewer confirms rev 2's H1/H2 fixes internally consistent and verified against source; no items block execution. Tasks are in strict dependency order; each is independently green.

**Review changelog (rev 2 → rev 3):** L-A — `EvolveStrategy.run()` asserts the passed objective agrees with `cfg` on `remote_ref` **and `epochs`/`seed`** (no silent override). L-B — hook import-strings (`search_space_validator`/`validation_profile`/`pre_validate`) resolve via a shared `_resolve_hook(..., expect=)` that type-checks the result (callable / `ValidationProfile`) with a clear error, not a bare `getattr`. L-C — `run()` guards `isinstance(objective, RemoteObjective)` and raises a clear message instead of an `AttributeError`. Plus an `EvolveEvaluator` docstring note that an `infra` failure still scores 0 (can evict a good candidate; inherent to OpenEvolve).

**Review changelog (rev 1 → rev 2):**
- **H1 (error model — one rule):** backends raise ONLY transport/infra failures; *objective* failures are mapped to the OpenEvolve sentinel in exactly one place — the `EvolveEvaluator`. See the revised "Error model" below + A6/A7/A9 (marker→raise) + B3 (single mapping point).
- **H2 (evolve objective lifecycle):** `EvolveConfig` is the single serialized source of truth; the OpenEvolve worker rebuilds a **config-derived `RemoteObjective`**; consumer hooks are import-strings; `cfg.evaluation.{epochs,seed}` is canonical. See B2 (new config fields) + B4 (worker reconstruction).
- **M1:** `local_cuda` writes `candidate.program` to a temp file so `program_path` is uniformly a path-or-None (A5).
- **M2:** `RemoteObjective.evaluate()` is a real in-process fallback (entrypoint at default device); the entrypoint is the single execution path (A2 docstring).
- **M3:** documented why `epochs/seed` ride on the objective and that the strategy sets them from config (A2/B4).
- **L1:** standard-entrypoint docstring no longer over-claims signature identity (called with keyword args). **L3:** Part C delete is hard-gated (C2).

**Goal:** Add the heavy, optional half of the substrate — the multi-backend compute pool (`[backends]`) and the `EvolveStrategy` hybrid over OpenEvolve (`[evolve]`) — by extracting ~2,800 LOC of working lakehouse `src/evolve/` orchestration onto the Phase 1A ports, and make lakehouse evolve the first real consumer.

**Architecture:** Hexagonal, unchanged from 1A. The lakehouse backends are **bridged onto the single 1A `ComputeBackend.evaluate(candidate, objective, *, timeout) -> Metrics` port** (not a second `train(...)` contract). Remote execution is an explicit opt-in property of the objective: a `RemoteObjective` carries a `RemoteRef` (install spec + import entrypoint) that compute backends use to resolve and run the objective on a compute node. `EvolveStrategy` is a thin `SearchStrategy` adapter over `openevolve.run_evolution`; the evolutionary loop is OpenEvolve's, the orchestration (backends, AST sandbox, config translation, search-space validation, seed caching) is ours.

**Tech Stack:** Python ≥3.10, pydantic v2, numpy, pyyaml (core, 1A); `[backends]` adds huggingface_hub (+ docker); `[evolve]` adds openevolve (+ the AST sandbox, no extra dep). `remote_ssh` uses the system `ssh`/`scp` CLIs via `subprocess` (NOT paramiko — a 1A pyproject correction, Task A0). Tests: pytest + hypothesis; CI matrix legs per extra.

**Spec:** `docs/superpowers/specs/2026-05-28-optimization-engine-carveout-design.md` (rev 3), §9 Phase 1B.

**Extraction source (read-only oracle):** lakehouse `D:\Development\karstenskyt__luxury-lakehouse\src\evolve\` — `backends/{base,pool,local_cuda,remote_ssh,docker,hf_jobs}.py`, `remote_worker.py`, `code_validator.py`, `config.py`, `evaluator.py`, `runner.py`, and tests under `src/tests/`. Paths prefixed `[lakehouse]` below.

**Working directory:** all paths relative to the ruthless repo root unless prefixed `[lakehouse]`. No worktrees (project convention) — a feature branch in this repo. `/final-review` is the pre-commit gate. No commit without explicit user approval.

**Determinism posture (spec C-A — load-bearing):** there is **NO trajectory-identity golden** for evolve. OpenEvolve owns the stochastic loop (islands/RNG/migration) and is NOT reproduced. Behaviour-preservation is scoped to **our orchestration only** — the AST sandbox verdict and the `BackendPool` dispatch order/metrics — tested with a **fake loop** (monkeypatched `openevolve.run_evolution`) and fakes for LLM/backends. No GPU, no network, no LLM in CI.

**Out of scope (later plans):** `OptunaStrategy` / `CachedObjective` / group-scoring / TC3 migration (Phase 2); silly-kicks adoption (Phase 3); cutting `1.0`. Part C (consumer migration) is **write-only here** and executes later in the lakehouse repo (its full acceptance needs GPU + LLM infra).

---

## Central design decision — one `ComputeBackend` port (settled)

The lakehouse backends speak `train(candidate_config, target, epochs, seed, program_path) -> dict[str,float]`. Phase 1A shipped the general port `evaluate(candidate, objective, *, timeout) -> Metrics` (+ `available()`), with `timeout` pre-added (review H-C) **specifically so 1B's remote backends implement this port**. We honor that: **one port, no fork.** `train(...)` is the same concept with two fixable mismatches, both resolved here:

1. **Per-run vs per-call params.** `target/epochs/seed` are constant across every candidate in a run (verified in `remote_ssh._train_impl`/`hf_jobs._train_impl` — they are passed unchanged each call). They move to **construction config**, not the per-call signature. Only the candidate config (→ `Candidate.params`) and the Level-2 program source (→ a new `Candidate.program` field) vary per call.

2. **Remote resolvability (the real 1B design content).** The 1A port assumed a backend can call `objective.evaluate(candidate)` locally. Remote SSH/HF-Jobs backends cannot ship an arbitrary `Objective` object over the wire — the lakehouse already solved this by shipping the candidate + a `target` name and having the remote `importlib`-import the objective from the installed package. We generalise that into an explicit, injected `RemoteRef` (replacing the `shared.wheel` import + the `target` convention):

```python
# ruthless/remote.py  — core (no heavy deps; pure stdlib + typing)
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ruthless.result import Candidate, Metrics


@dataclass(frozen=True)
class RemoteRef:
    """How a compute backend resolves and runs a consumer Objective on a compute node.

    Replaces the lakehouse `shared.wheel` import + the `evolve.targets.<target>` convention
    (injected config, never an import). The resolved callable is the standard remote entrypoint,
    always invoked with KEYWORD arguments (so a positional-or-keyword def is fine — the lakehouse
    `train_and_evaluate` matches exactly):

        train_and_evaluate(candidate_config: dict, device: str, epochs: int,
                           seed: int, program_path: str | None) -> dict[str, float]

    `program_path` is ALWAYS a filesystem path to a `.py` file, or None (never raw source) — every
    caller (in-process, local_cuda, remote worker) writes Candidate.program to a temp file first (M1).
    """

    entrypoint: str             # "package.module:callable" the node imports & invokes
    package: str | None = None  # PEP-723 dependency spec the node installs, e.g.
                                #   "my-pkg[train] @ https://.../my_pkg-1.0-py3-none-any.whl".
                                #   None when the node already has the package on PYTHONPATH (SSH case).


@runtime_checkable
class RemoteObjective(Protocol):
    """An Objective (1A port) that is ALSO resolvable on a compute node.

    The remote entrypoint (`remote_ref.entrypoint` → `train_and_evaluate`) is the SINGLE execution
    path, reached two ways: InProcessBackend calls `objective.evaluate(candidate)`, which is a thin
    LOCAL invocation of that same entrypoint at a default device (a real in-process fallback, NOT dead
    code — M2); compute backends ([backends]) invoke the entrypoint directly (local_cuda in-process at
    the backend's device; ssh/hf on the node). A compute backend handed a non-RemoteObjective raises
    FatalEvaluationError.

    `epochs`/`seed` ride on the objective because the port hands a backend only `(candidate,
    objective)` — they are run knobs, not candidate knobs, so the objective is their per-run carrier
    (M3). Their single source of truth is `EvolveConfig.evaluation`; `EvolveStrategy` sets/threads them
    from config (H2.1) — a consumer must not hand-sync them. `device` is the backend's (asymmetry by
    design: where-to-run is the compute resource's property, not the objective's)."""

    def evaluate(self, candidate: Candidate) -> Metrics: ...  # 1A port; local entrypoint at default device

    @property
    def remote_ref(self) -> RemoteRef: ...

    @property
    def epochs(self) -> int: ...

    @property
    def seed(self) -> int: ...
```

**Dispatch model (one port, two backend families):**
- `InProcessBackend` (core, 1A — unchanged): `evaluate(candidate, objective, *, timeout)` → `objective.evaluate(candidate)`. For pure/CPU objectives (random, optuna). Ignores remote-ness.
- Compute backends (`local_cuda`/`remote_ssh`/`hf_jobs`/`docker`, `[backends]`): require a `RemoteObjective`. They resolve `objective.remote_ref.entrypoint` (locally for `local_cuda`, remotely for ssh/hf) and call the standard `train_and_evaluate(candidate_config=candidate.params, device=<backend>, epochs=objective.epochs, seed=objective.seed, program_path=candidate.program)`. Handed a non-remote `Objective`, they raise `FatalEvaluationError` loudly.

**Error model — ONE rule (H1).** The three lakehouse backends handle the *same* failure (the objective crashing during evaluation) three different ways — `remote_ssh`/`hf_jobs` let the node's worker pre-bake `{combined_score:0, error:1, _error_text}` and the backend returns it as a "valid" metrics dict; `local_cuda`/`InProcess` raw-propagate. That is exactly the silent-wrong-score class the taxonomy exists to kill. We collapse it to one rule:

1. **Backends never return a sentinel score.** A backend returns ONLY a genuine metrics dict from a successful objective run, or it **raises**:
   - `TransientEvaluationError` — transport/infra failures: per-candidate timeout, ssh/host unreachable, non-zero remote exit, network errors.
   - `FatalEvaluationError` — unparseable/empty worker output, missing `remote_ref` (non-RemoteObjective), **or a parsed objective-failure marker** (the worker's `{error:1}`/`_error_text` line → the backend treats it as a node-side objective crash and raises, rather than passing it through as a score).
2. **Objective crashes surface, they are not recorded by the backend.** `local_cuda`/in-process wrap the entrypoint call in `try/except` and raise `FatalEvaluationError` (with the candidate id + traceback). The remote worker (A9) still catches on the node (it must emit *something* over the wire) and emits the `{error:1, _error_text}` marker — but per (1) the backend converts that marker into a raise, never a returned score.
3. **`BackendPool`** retries `Transient` on the next backend (bounded `max_retries`), surfaces `Fatal` immediately, re-raises the last `Transient` on exhaustion.
4. **The `EvolveEvaluator` (Part B) is the SINGLE place that maps a failure to the OpenEvolve sentinel.** It wraps the pool/backend call in `try/except Exception` and returns `EvaluationResult(metrics={"combined_score":0, "error":1}, artifacts={"error": <text>})` — because OpenEvolve needs a metrics dict per candidate, and a crashed candidate *should* score worst so the search avoids it. It distinguishes (in the artifact/log) an **objective crash** (`Fatal` from the candidate) from **exhausted-transient infra** (a good candidate that couldn't be evaluated — logged loudly, not mislabeled). This is the strategy deciding its own recording (spec C1), not the backend silently scoring. No other strategy (random/optuna) records `error:1` — they surface per the 1A taxonomy.

**§8 framing:** porting the lakehouse backend tests means preserving *behaviour* (dispatch order, parsed metrics, availability gating), not the `train(...)` *signature*. Ported tests are adapted to call `evaluate(...)` and assert the same observable behaviour — faithful characterization.

---

## File Structure

```
ruthless/
  remote.py                     # NEW (core): RemoteRef + RemoteObjective Protocol + the standard remote entrypoint contract docstring
  result.py                     # MODIFY: add Candidate.program: str | None = None (Level-2 source; folded into the hash key)
  errors.py                     # 1A (Fatal/TransientEvaluationError already present) — no change
  backend.py                    # 1A port + InProcessBackend — no change
  config.py                     # MODIFY: + BackendConfig; + EvolveConfig (kind="evolve") and its nested models into the strategy union
  backends/                     # NEW sub-package  [extra: backends]
    __init__.py                 # create_backend(BackendConfig) registry + comma-string → BackendPool wiring
    base.py                     # shared helpers (metric-line parsing, the RemoteObjective guard); imports the port from ruthless.backend
    pool.py                     # BackendPool: priority-queue dispatch over the 1A evaluate() port + transient-retry contract
    local_cuda.py               # LocalCudaBackend: imports remote_ref.entrypoint in-process, runs on a CUDA device
    remote_ssh.py               # RemoteSSHBackend: ssh/scp via subprocess; per-candidate timeout
    hf_jobs.py                  # HFJobsBackend: PEP-723 UV job; remote_package injected (NO shared.wheel)
    docker.py                   # DockerBackend: not-yet-implemented stub (available()->False) — ported as-is
    remote_worker.py            # generic remote entrypoint runner: importlib-imports remote_ref.entrypoint (NO evolve.targets)
  strategies/
    evolve_/                    # NEW  [extra: evolve]
      __init__.py
      sandbox.py                # AST allow-list sandbox (ValidationProfile + validate_program) — verbatim, domain-free (ADR-001)
      evaluator.py              # EvolveEvaluator: OpenEvolve evaluator plugin; injected search-space validator; fail_metrics mapping
      strategy.py               # EvolveStrategy(SearchStrategy): config translation + openevolve.run_evolution + seed cache/resume + Result
tests/
  test_remote.py  test_candidate_program.py
  backends/  test_pool.py test_local_cuda.py test_remote_ssh.py test_hf_jobs.py test_docker.py test_create_backend.py test_remote_worker.py test_backend_timeout_retry.py
  strategies/evolve/  test_sandbox.py test_evolve_config.py test_evolve_evaluator.py test_evolve_strategy.py
  e2e/  test_evolve_orchestration_gate.py     # fake-loop orchestration golden (no GPU/LLM/network)
pyproject.toml  .importlinter  .github/workflows/ci.yml
```

**Dependency order (task order follows):** A0 pyproject/extras → A1 Candidate.program → A2 remote.py → A3 backends/base → A4 pool (+retry/timeout) → A5 local_cuda → A6 remote_ssh → A7 hf_jobs (remote_package sever) → A8 docker → A9 remote_worker → A10 config (BackendConfig) → A11 create_backend → B1 sandbox → B2 config (EvolveConfig union) → B3 EvolveEvaluator → B4 EvolveStrategy → B5 orchestration gate → C (consumer migration, write-only) → CI/import-linter.

---

## pyproject + tooling updates (Task A0)

**Files:** Modify `pyproject.toml`, `.importlinter`, `.github/workflows/ci.yml`

- [ ] **Step 1: Correct + extend extras in `pyproject.toml`.** The 1A `[backends]` listed `paramiko` — but `remote_ssh.py` uses the system `ssh`/`scp` CLIs via `subprocess`, never paramiko (verified). Replace it. `local_cuda` lazily imports `torch` only in `available()` and otherwise imports the consumer entrypoint — `torch` is the *consumer's* dependency, NOT ruthless's. Set:

```toml
[project.optional-dependencies]
optuna = ["optuna>=4.0"]                       # Phase 2
evolve = ["openevolve>=0.2.0"]                 # Plan 1B (this plan): EvolveStrategy + AST sandbox
backends = ["huggingface_hub>=0.25", "docker>=7"]  # Plan 1B: hf_jobs (+ docker stub). ssh uses system ssh/scp; local_cuda's torch is the consumer's.
dev = ["pytest>=8", "hypothesis>=6", "ruff>=0.6", "pyright>=1.1.380", "import-linter>=2.0"]
```

- [ ] **Step 2: Add import-linter contracts for the new layers.** Append to `.importlinter`:

```ini
[importlinter:contract:backends-isolation]
name = backends must not import strategies
type = forbidden
source_modules =
    ruthless.backends
forbidden_modules =
    ruthless.strategies
```

Add `ruthless.remote` to the existing `core-isolation` `source_modules` list (it is core and must not import strategies/backends). Add `ruthless.backends` to the `forbidden_modules` of `core-isolation` (core must not import the backends package; `InProcessBackend` stays in `ruthless.backend`, which is core and imports only the port).

- [ ] **Step 3: CI matrix legs per extra.** In `ci.yml`, after the core gate, add legs that install `.[dev,backends]` and `.[dev,evolve]` and run the backends / evolve test subtrees. (openevolve must resolve on PyPI; if it cannot be installed in CI, mark the evolve leg `continue-on-error` and gate only the fake-loop tests that don't import openevolve — see B5.) Keep `pyright` on `ruthless` + `tests`.

- [ ] **Step 4: Verify** — `uv pip install -e ".[dev,backends,evolve]"` resolves; `uv run lint-imports` still "Contracts: 3 kept". (If `openevolve>=0.2.0` fails to resolve, STOP and raise — the evolve extra version may need adjustment.)

- [ ] **Step 5: Commit (PAUSE)** — `chore: 1B extras (backends/evolve), import-linter backends contract, CI legs`

---

## Task A1: `Candidate.program` field (per-candidate Level-2 source)

**Files:** Modify `ruthless/result.py`; Create `tests/test_candidate_program.py`

- [ ] **Step 1: Failing test**
```python
# tests/test_candidate_program.py
from ruthless.result import Candidate


def test_candidate_program_defaults_none_and_is_backward_compatible():
    c = Candidate("c0", {"x": 1.0})
    assert c.program is None  # existing 2-arg construction still works


def test_candidate_program_participates_in_identity():
    a = Candidate("c1", {"x": 1.0}, program="def f(): return 1")
    b = Candidate("c1", {"x": 1.0}, program="def f(): return 1")
    c = Candidate("c1", {"x": 1.0}, program="def f(): return 2")
    assert a == b and hash(a) == hash(b)
    assert a != c  # different source => different candidate
    assert {a, b, c} == {a, c}
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/test_candidate_program.py -v` (unexpected `program` kwarg).

- [ ] **Step 3: Implement** — modify `ruthless/result.py` `Candidate` (keep `eq=False`, hashable, frozen):
```python
@dataclass(frozen=True, eq=False)
class Candidate:
    id: str
    params: dict[str, Any]  # values must be hashable; treat as immutable after construction
    program: str | None = None  # Level-2 candidate source (evolve code-evolution); None for config-only

    def _key(self) -> tuple[str, frozenset, str | None]:
        return (self.id, frozenset(self.params.items()), self.program)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Candidate) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())
```

- [ ] **Step 4: Run → PASS** — both new tests + the existing `tests/test_result.py` (backward compatible).

- [ ] **Step 5: Commit (PAUSE)** — `feat: Candidate.program — per-candidate Level-2 source (evolve)`

---

## Task A2: `remote.py` — RemoteRef + RemoteObjective

**Files:** Create `ruthless/remote.py`, `tests/test_remote.py`

- [ ] **Step 1: Failing test**
```python
# tests/test_remote.py
from ruthless.remote import RemoteObjective, RemoteRef
from ruthless.result import Candidate


class _Remote:  # structural — does NOT inherit the Protocol
    def evaluate(self, candidate: Candidate):
        return {"loss": 0.0}

    @property
    def remote_ref(self) -> RemoteRef:
        return RemoteRef(entrypoint="my_pkg.objectives:train_and_evaluate", package="my-pkg @ https://h/x.whl")

    epochs = 5
    seed = 42


class _Plain:
    def evaluate(self, candidate: Candidate):
        return {"loss": 0.0}


def test_remote_ref_fields():
    r = RemoteRef(entrypoint="m:f")
    assert r.entrypoint == "m:f" and r.package is None  # ssh case: no install spec


def test_remote_objective_structural_conformance():
    obj: RemoteObjective = _Remote()
    assert isinstance(obj, RemoteObjective)
    assert obj.remote_ref.entrypoint.endswith(":train_and_evaluate")
    assert obj.epochs == 5 and obj.seed == 42


def test_plain_objective_is_not_remote():
    assert not isinstance(_Plain(), RemoteObjective)  # name-only check still distinguishes remote_ref/epochs/seed
```

- [ ] **Step 2: Run → FAIL** — module not found.

- [ ] **Step 3: Implement** — `ruthless/remote.py` exactly as in the "Central design decision" section above (`RemoteRef` dataclass + `RemoteObjective` Protocol). Include the standard-entrypoint-signature docstring.

- [ ] **Step 4: Run → PASS**.

- [ ] **Step 5: Commit (PAUSE)** — `feat: RemoteRef + RemoteObjective — remotely-resolvable objective opt-in`

---

## Task A3: `backends/base.py` — shared backend helpers

**Files:** Create `ruthless/backends/__init__.py` (empty package marker for now), `ruthless/backends/base.py`, `tests/backends/__init__.py`, `tests/backends/test_base.py`

Extract the generic, backend-shared helpers (verified domain-free). The `ComputeBackend` Protocol stays in `ruthless.backend` (1A) — `base.py` only holds helpers the concrete backends share: the `RemoteObjective` guard and the stdout/log JSON-metrics parser (lifted from `[lakehouse] remote_ssh.py:361-372` + `hf_jobs.py:241-257`).

- [ ] **Step 1: Failing test**
```python
# tests/backends/test_base.py
import math
import pytest
from ruthless.backends.base import parse_last_json_line, require_remote
from ruthless.errors import FatalEvaluationError
from ruthless.remote import RemoteRef
from ruthless.result import Candidate


class _Remote:
    def evaluate(self, c): return {"loss": 0.0}
    @property
    def remote_ref(self): return RemoteRef(entrypoint="m:f")
    epochs = 1
    seed = 0


def test_parse_last_json_line_finds_metrics_among_noise():
    out = "loading...\nepoch 1\n{\"combined_score\": 0.8, \"spearman_rho\": 0.7}\n"
    assert parse_last_json_line(out) == {"combined_score": 0.8, "spearman_rho": 0.7}


def test_parse_last_json_line_raises_on_no_json():
    with pytest.raises(FatalEvaluationError):
        parse_last_json_line("no json here\nstill none\n")


def test_require_remote_returns_ref_for_remote_objective():
    ref = require_remote(_Remote(), backend="RemoteSSHBackend")
    assert ref.entrypoint == "m:f"


def test_require_remote_raises_for_plain_objective():
    class _Plain:
        def evaluate(self, c): return {"loss": 0.0}
    with pytest.raises(FatalEvaluationError):
        require_remote(_Plain(), backend="RemoteSSHBackend")


def test_program_to_path_writes_temp_file_and_cleans_up():
    from pathlib import Path
    from ruthless.backends.base import program_to_path
    with program_to_path(Candidate("c", {"x": 1.0}, program="def f(): return 1")) as p:
        assert p is not None and Path(p).read_text() == "def f(): return 1"
    assert not Path(p).exists()  # cleaned up on exit


def test_program_to_path_yields_none_without_program():
    from ruthless.backends.base import program_to_path
    with program_to_path(Candidate("c", {"x": 1.0})) as p:
        assert p is None


def test_is_objective_failure_detects_marker():
    from ruthless.backends.base import is_objective_failure
    assert is_objective_failure({"combined_score": 0.0, "error": 1}) is True
    assert is_objective_failure({"combined_score": 0.0, "_error_text": "tb"}) is True
    assert is_objective_failure({"combined_score": 0.8}) is False
```

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement**
```python
# ruthless/backends/base.py
"""Helpers shared by the compute backends ([backends] extra). The ComputeBackend port lives in
ruthless.backend (1A, core); backends import it from there. These helpers replace the lakehouse
fail_metrics() swallowing with the 1A error taxonomy (raise Fatal/Transient, never record a sentinel)."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

from ruthless.errors import FatalEvaluationError
from ruthless.remote import RemoteObjective, RemoteRef
from ruthless.result import Candidate

# The marker a remote worker emits when the OBJECTIVE crashed on the node (vs. a transport failure).
# Backends convert this into a raise (H1) rather than returning it as a score.
_OBJECTIVE_FAILURE_KEYS = ("_error_text",)


def is_objective_failure(metrics: dict) -> bool:
    """True if a parsed worker metrics dict is actually a node-side objective-failure marker (H1)."""
    return metrics.get("error") == 1 or any(k in metrics for k in _OBJECTIVE_FAILURE_KEYS)


@contextmanager
def program_to_path(candidate: Candidate) -> Iterator[str | None]:
    """Yield a temp `.py` path holding candidate.program, or None if there is none (M1).

    Gives every backend a UNIFORM `program_path` contract: a filesystem path or None, never raw
    source. The temp file is removed on exit."""
    if candidate.program is None:
        yield None
        return
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(candidate.program)
        path = tmp.name
    try:
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def parse_last_json_line(stdout: str) -> dict[str, float]:
    """Return the last non-empty line of `stdout` parsed as a JSON metrics dict.

    Mirrors the lakehouse remote backends: the worker prints exactly one JSON line; earlier lines
    may be stray warnings. Raises FatalEvaluationError if no JSON object line is present."""
    for line in reversed([ln.strip() for ln in stdout.splitlines() if ln.strip()]):
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise FatalEvaluationError(f"no JSON metrics line in worker stdout (last 200 chars): {stdout[-200:]!r}")


def require_remote(objective: object, *, backend: str) -> RemoteRef:
    """Return the objective's RemoteRef, or raise FatalEvaluationError if it is not a RemoteObjective.

    Compute backends cannot ship an arbitrary in-process Objective to a node — the objective must opt
    in to remote execution by exposing `remote_ref` (and `epochs`/`seed`)."""
    if not isinstance(objective, RemoteObjective):
        raise FatalEvaluationError(
            f"{backend} requires a RemoteObjective (with .remote_ref/.epochs/.seed); "
            f"got {type(objective).__name__}. Use InProcessBackend for non-remote objectives."
        )
    return objective.remote_ref
```

- [ ] **Step 4: Run → PASS**.

- [ ] **Step 5: Commit (PAUSE)** — `feat: backends.base — JSON-metrics parser + RemoteObjective guard (raise, not fail_metrics)`

---

## Task A4: `backends/pool.py` — BackendPool on the 1A port + transient-retry contract

**Files:** Create `ruthless/backends/pool.py`, `tests/backends/test_pool.py`, `tests/backends/test_backend_timeout_retry.py`

Behaviour-port of `[lakehouse] backends/pool.py` (priority queue, fast-backend-gets-more-work via re-enqueue, empty-pool `ValueError`, `available()=any`), **adapted to the 1A `evaluate(candidate, objective, *, timeout)` port** and extended with the transient-retry contract (1A H-C/M-E). Port the 8 tests from `[lakehouse] src/tests/test_backend_pool.py` (all PORTABLE) adapted to `evaluate(...)`.

- [ ] **Step 1: Failing tests** (dispatch + retry). Abbreviated; full set ports the lakehouse 8 + adds retry:
```python
# tests/backends/test_pool.py
import threading
import pytest
from ruthless.backends.pool import BackendPool
from ruthless.errors import FatalEvaluationError, TransientEvaluationError
from ruthless.result import Candidate

_OBJ = object()  # backends in these tests ignore the objective; a sentinel is fine
_C = Candidate("c", {"x": 1.0})


def _backend(metrics=None, *, available=True, raises=None, delay=0.0):
    class _B:
        def __init__(self): self.calls = 0
        def evaluate(self, candidate, objective, *, timeout=None):
            self.calls += 1
            if delay: threading.Event().wait(delay)
            if raises is not None: raise raises
            return dict(metrics or {"loss": 1.0})
        def available(self): return available
    return _B()


def test_single_backend_routes_and_returns():
    b = _backend({"loss": 0.5})
    assert BackendPool([b]).evaluate(_C, _OBJ)["loss"] == 0.5 and b.calls == 1


def test_empty_pool_rejected():
    with pytest.raises(ValueError, match="at least one backend"):
        BackendPool([])


def test_available_any_and_none():
    assert BackendPool([_backend(available=False), _backend(available=True)]).available() is True
    assert BackendPool([_backend(available=False)]).available() is False


def test_priority_prefers_first_backend_when_idle():
    first, second = _backend(), _backend()
    pool = BackendPool([first, second])
    pool.evaluate(_C, _OBJ); pool.evaluate(_C, _OBJ)
    assert first.calls == 2 and second.calls == 0  # idle pool always re-picks highest priority
```
```python
# tests/backends/test_backend_timeout_retry.py
import pytest
from ruthless.backends.pool import BackendPool
from ruthless.errors import FatalEvaluationError, TransientEvaluationError
from ruthless.result import Candidate

_C, _OBJ = Candidate("c", {"x": 1.0}), object()


def _flaky(seq):
    """Backend that raises/returns per a script list (exception instances or metrics dicts)."""
    it = iter(seq)
    class _B:
        def evaluate(self, candidate, objective, *, timeout=None):
            x = next(it)
            if isinstance(x, Exception): raise x
            return x
        def available(self): return True
    return _B()


def test_transient_retries_on_next_backend_then_succeeds():
    b1 = _flaky([TransientEvaluationError("ssh timeout")])
    b2 = _flaky([{"loss": 0.3}])
    assert BackendPool([b1, b2], max_retries=2).evaluate(_C, _OBJ)["loss"] == 0.3


def test_transient_exhaustion_surfaces():
    pool = BackendPool([_flaky([TransientEvaluationError("t")]), _flaky([TransientEvaluationError("t")])], max_retries=1)
    with pytest.raises(TransientEvaluationError):
        pool.evaluate(_C, _OBJ)


def test_fatal_surfaces_immediately_without_retry():
    b1 = _flaky([FatalEvaluationError("broken")])
    b2 = _flaky([{"loss": 0.0}])
    with pytest.raises(FatalEvaluationError):
        BackendPool([b1, b2], max_retries=3).evaluate(_C, _OBJ)
```

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement** — port `[lakehouse] backends/pool.py` semantics onto the port:
```python
# ruthless/backends/pool.py
"""BackendPool — priority-ordered, concurrent inter-candidate dispatch over the 1A ComputeBackend
port. Ports the lakehouse pool (queue.PriorityQueue; fast backends re-enter sooner so they take more
work; 1h acquire deadlock guard) and adds the transient-retry contract (1A H-C/M-E): a
TransientEvaluationError releases the backend and retries on the next available one up to
`max_retries`; a FatalEvaluationError surfaces immediately; transient exhaustion re-raises the last."""

from __future__ import annotations

import queue
from typing import Any

from ruthless._logging import get_logger
from ruthless.backend import ComputeBackend
from ruthless.errors import TransientEvaluationError
from ruthless.objective import Objective
from ruthless.result import Candidate, Metrics

_log = get_logger("backends.pool")
_ACQUIRE_TIMEOUT = 3600  # seconds — deadlock guard waiting for an idle backend


class BackendPool:
    def __init__(self, backends: list[ComputeBackend], *, max_retries: int = 2) -> None:
        if not backends:
            raise ValueError("BackendPool requires at least one backend")
        self._backends = list(backends)
        self._max_retries = max_retries
        self._priority: dict[int, int] = {id(b): i for i, b in enumerate(self._backends)}
        self._available: queue.PriorityQueue[tuple[int, int, ComputeBackend]] = queue.PriorityQueue()
        for b in self._backends:
            self._available.put((self._priority[id(b)], id(b), b))

    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics:
        last: TransientEvaluationError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                pri, _, backend = self._available.get(timeout=_ACQUIRE_TIMEOUT)
            except queue.Empty as exc:
                raise TransientEvaluationError(f"no backend available within {_ACQUIRE_TIMEOUT}s") from exc
            try:
                return backend.evaluate(candidate, objective, timeout=timeout)
            except TransientEvaluationError as exc:  # retryable: try the next backend
                last = exc
                _log.info("transient_retry", extra={"attempt": attempt, "error": str(exc)})
            finally:
                self._available.put((pri, id(backend), backend))
        assert last is not None
        raise last

    def available(self) -> bool:
        return any(b.available() for b in self._backends)
```
(Note: `FatalEvaluationError` is NOT caught — it propagates out of `evaluate` immediately, satisfying `test_fatal_surfaces_immediately`.)

- [ ] **Step 4: Run → PASS** (port the remaining lakehouse pool tests — `test_two_backends_concurrent`, `test_fast_backend_gets_more_work`, `test_backend_failure_does_not_crash_pool` adapted: a backend raising `TransientEvaluationError` still releases its slot and the next call/backend succeeds).

- [ ] **Step 5: Commit (PAUSE)** — `feat: BackendPool on the 1A port + transient-retry contract`

---

## Task A5: `backends/local_cuda.py` — LocalCudaBackend

**Files:** Create `ruthless/backends/local_cuda.py`, `tests/backends/test_local_cuda.py`

Behaviour-port of `[lakehouse] backends/local_cuda.py`, bridged to the port. Instead of `evolve.targets.{target}.evaluator`, it resolves `objective.remote_ref.entrypoint` (a `"module:callable"`) **in-process** via `importlib`, and calls the standard `train_and_evaluate(candidate_config, device, epochs, seed, program_path)`. `available()` returns `torch.cuda.is_available()` (lazy import; `False` on ImportError) — torch is the consumer's dep.

- [ ] **Step 1: Failing test** (a fake entrypoint module via `monkeypatch`/`sys.modules`; no torch needed for the dispatch test):
```python
# tests/backends/test_local_cuda.py
import sys, types
from ruthless.backends.local_cuda import LocalCudaBackend
from ruthless.remote import RemoteRef
from ruthless.result import Candidate


def _install_entrypoint(monkeypatch, recorder):
    mod = types.ModuleType("fake_obj_mod")
    def train_and_evaluate(*, candidate_config, device, epochs, seed, program_path):
        recorder.update(candidate_config=candidate_config, device=device, epochs=epochs, seed=seed, program_path=program_path)
        return {"loss": candidate_config["x"] ** 2}
    mod.train_and_evaluate = train_and_evaluate
    monkeypatch.setitem(sys.modules, "fake_obj_mod", mod)


class _Remote:
    def __init__(self): self._ref = RemoteRef(entrypoint="fake_obj_mod:train_and_evaluate")
    def evaluate(self, c): raise AssertionError("compute backends use the entrypoint, not evaluate()")
    @property
    def remote_ref(self): return self._ref
    epochs = 7
    seed = 11


def test_local_cuda_resolves_entrypoint_and_passes_construction_params(monkeypatch):
    rec: dict = {}
    _install_entrypoint(monkeypatch, rec)
    b = LocalCudaBackend(device="cuda:3")
    m = b.evaluate(Candidate("r0", {"x": 4.0}, program="def f(): return 1"), _Remote())
    assert m["loss"] == 16.0
    assert rec["candidate_config"] == {"x": 4.0} and rec["device"] == "cuda:3"
    assert rec["epochs"] == 7 and rec["seed"] == 11
    # M1: program_path is a FILE PATH (not raw source); its contents are the program
    assert rec["program_path"] is not None
    from pathlib import Path
    assert Path(rec["program_path"]).read_text() == "def f(): return 1"


def test_local_cuda_program_none_passes_none(monkeypatch):
    rec: dict = {}
    _install_entrypoint(monkeypatch, rec)
    LocalCudaBackend().evaluate(Candidate("r0", {"x": 1.0}), _Remote())  # no program
    assert rec["program_path"] is None


def test_local_cuda_objective_crash_raises_fatal(monkeypatch):
    import sys, types
    from ruthless.errors import FatalEvaluationError
    mod = types.ModuleType("boom_mod")
    def train_and_evaluate(**kw): raise RuntimeError("training diverged")
    mod.train_and_evaluate = train_and_evaluate
    monkeypatch.setitem(sys.modules, "boom_mod", mod)

    class _R:
        def evaluate(self, c): return {}
        @property
        def remote_ref(self): return RemoteRef(entrypoint="boom_mod:train_and_evaluate")
        epochs = 1
        seed = 0
    import pytest
    with pytest.raises(FatalEvaluationError):  # H1: objective crash -> Fatal, not raw, not a score
        LocalCudaBackend().evaluate(Candidate("r0", {"x": 1.0}), _R())
```

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement** — resolve `"module:callable"`; write `candidate.program` to a temp `.py` (M1 — uniform `program_path` is a path-or-None, never raw source) and clean it up; wrap the entrypoint call so an objective crash raises `FatalEvaluationError` (H1 — not a raw exception, not a recorded score); `require_remote` raises `Fatal` for a non-RemoteObjective. A shared helper `program_to_path(candidate)` (context manager yielding a temp path or None) lives in `backends/base.py` and is reused by `remote_ssh`/`hf_jobs` for the same write-to-file step.
```python
# ruthless/backends/local_cuda.py
"""LocalCudaBackend — runs the objective's remote entrypoint IN-PROCESS on a local CUDA device.
Bridged to the 1A port: resolves objective.remote_ref.entrypoint (module:callable) and calls the
standard train_and_evaluate(candidate_config, device, epochs, seed, program_path)."""

from __future__ import annotations

import importlib

from ruthless.backends.base import program_to_path, require_remote
from ruthless.errors import FatalEvaluationError
from ruthless.objective import Objective
from ruthless.remote import RemoteObjective
from ruthless.result import Candidate, Metrics


def _resolve(entrypoint: str):
    module_path, _, attr = entrypoint.partition(":")
    if not attr:
        raise FatalEvaluationError(f"remote_ref.entrypoint must be 'module:callable', got {entrypoint!r}")
    return getattr(importlib.import_module(module_path), attr)


class LocalCudaBackend:
    def __init__(self, device: str = "cuda:0") -> None:
        self._device = device
        self._available_cached: bool | None = None

    def evaluate(self, candidate: Candidate, objective: Objective, *, timeout: float | None = None) -> Metrics:
        ref = require_remote(objective, backend="LocalCudaBackend")
        assert isinstance(objective, RemoteObjective)
        fn = _resolve(ref.entrypoint)
        with program_to_path(candidate) as program_path:  # M1: temp .py path or None
            try:
                return fn(candidate_config=candidate.params, device=self._device,
                          epochs=objective.epochs, seed=objective.seed, program_path=program_path)
            except Exception as exc:  # H1: objective crash -> Fatal (surfaced, never a recorded score)
                raise FatalEvaluationError(f"objective entrypoint {ref.entrypoint!r} crashed on {candidate.id}: {exc}") from exc

    def available(self) -> bool:
        if self._available_cached is None:
            try:
                import torch  # consumer dependency; lazy
                self._available_cached = bool(torch.cuda.is_available())
            except ImportError:
                self._available_cached = False
        return self._available_cached
```
(local_cuda does not enforce `timeout` — in-process has no cross-call cancellation; documented. Remote backends enforce it. `program_to_path` is added to `backends/base.py` in Task A3 — add a test there: source string → temp `.py` with matching contents; `None` → `None`.)

- [ ] **Step 4: Run → PASS**.

- [ ] **Step 5: Commit (PAUSE)** — `feat: LocalCudaBackend on the 1A port (entrypoint resolution)`

---

## Task A6: `backends/remote_ssh.py` — RemoteSSHBackend (per-candidate timeout → Transient)

**Files:** Create `ruthless/backends/remote_ssh.py`, `tests/backends/test_remote_ssh.py`

Behaviour-port of `[lakehouse] backends/remote_ssh.py`. Keep the mechanism verbatim (ssh/scp via `subprocess`, stderr-streaming thread, `_active_procs` + atexit cleanup, `_kill_remote_workers`, `available()` via `ssh echo OK`). **Three changes:**
1. Signature → `evaluate(candidate, objective, *, timeout)`; `require_remote(objective)` first; read `entrypoint`/`epochs`/`seed` from objective; `program` from `candidate.program`.
2. The remote invocation becomes `python -m ruthless.backends.remote_worker candidate.json {device} {epochs} {seed} {entrypoint} [--program program.py]` (the generic worker — Task A9 — replaces `evolve.remote_worker` + the `target` arg with the `entrypoint`).
3. **Error model (H1):** on `subprocess.TimeoutExpired` → kill workers, raise `TransientEvaluationError`; on `CalledProcessError`/non-zero exit/`OSError`/SSH failure → raise `TransientEvaluationError` (network/host transient). Parse metrics via `base.parse_last_json_line` (raises `FatalEvaluationError` if absent); then if `base.is_objective_failure(metrics)` (the worker's `{error:1}`/`_error_text` marker) → **raise `FatalEvaluationError`** (a node-side objective crash — NOT returned as a score). Only a clean metrics dict is returned. The hardcoded `_warm_hf_cache(dataset)` / `"luxury-lakehouse/..."` default is **dropped** (domain; the consumer's `train_and_evaluate` handles its own data/caching). `candidate.program` is written via `base.program_to_path` and scp'd as `program.py` (M1 — uniform path contract).

- [ ] **Step 1: Failing test** — monkeypatch `subprocess.run`/`subprocess.Popen` to avoid real ssh. Assert: (a) the remote command contains the entrypoint, epochs, seed, and `--program`; (b) a `TimeoutExpired` from `communicate` raises `TransientEvaluationError`; (c) a clean stdout JSON line returns parsed metrics; (d) a plain Objective raises `FatalEvaluationError` (via `require_remote`). (Full fakes mirror `[lakehouse] test_*` patterns: patch `subprocess`.)

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement** — copy `[lakehouse] remote_ssh.py` and apply the changes. Every `return fail_metrics()` becomes a raise: transport failures → `TransientEvaluationError`; unparseable output or a parsed `is_objective_failure` marker → `FatalEvaluationError` (per bullet 3). The `train`/`_train_impl` split becomes `evaluate`/`_evaluate_impl`; the remote command uses `ref.entrypoint` in place of `target` and `ruthless.backends.remote_worker` in place of `evolve.remote_worker`; `epochs`/`seed` come from `objective.epochs`/`objective.seed`. `candidate.program` is materialised via `base.program_to_path(candidate)` and scp'd as `program.py` when not None (M1).

- [ ] **Step 4: Run → PASS**.

- [ ] **Step 5: Commit (PAUSE)** — `feat: RemoteSSHBackend on the 1A port; timeout→Transient; generic remote_worker`

---

## Task A7: `backends/hf_jobs.py` — HFJobsBackend (sever shared.wheel → injected remote_package)

**Files:** Create `ruthless/backends/hf_jobs.py`, `tests/backends/test_hf_jobs.py`

Behaviour-port of `[lakehouse] backends/hf_jobs.py`. Keep the mechanism (PEP-723 UV worker script, base64 env vars, `run_uv_job`, `_poll_job` with `JobStage`, log scraping, `available()` via `whoami`). **Critical change — sever `shared.wheel` (the two touch points + the entrypoint):**
- Delete `from shared.wheel import WHEEL_BASE_URL` (`[lakehouse] hf_jobs.py:26`).
- `_WORKER_SCRIPT` must stop being a module-level f-string baking in `WHEEL_BASE_URL`. Make it a **function `_build_worker_script(ref: RemoteRef) -> str`** that interpolates `ref.package` into the PEP-723 `dependencies = [...]` (replacing `"luxury-lakehouse[analytics,training] @ {WHEEL_BASE_URL}"`) and `ref.entrypoint` into the worker's `importlib.import_module(...)` + call (replacing `evolve.targets.{target}.evaluator`). If `ref.package is None`, raise `FatalEvaluationError` (HF Jobs needs an install spec — unlike ssh, the node is fresh).
- `evaluate(candidate, objective, *, timeout)`: `require_remote`; build env from `candidate.params` (base64 JSON), `objective.epochs/seed`, `candidate.program` (base64 → `EVOLVE_PROGRAM`); the embedded worker decodes them and calls the standard `train_and_evaluate(...)`.
- **Error model (H1):** timeout → cancel job + raise `TransientEvaluationError`; `JobStage.ERROR/CANCELED/DELETED` → `FatalEvaluationError`; no metrics line → `FatalEvaluationError` (via `parse_last_json_line` over logs); a parsed `is_objective_failure` marker (`{error:1}`/`_error_text` from the embedded worker) → `FatalEvaluationError` (node-side objective crash, never returned as a score). Program source for Level-2 is base64-encoded from `candidate.program` into `EVOLVE_PROGRAM` (the embedded worker writes it to a temp path before calling the entrypoint — uniform path contract, M1).

- [ ] **Step 1: Failing test** — port the 6 PORTABLE tests from `[lakehouse] src/tests/test_hf_jobs_backend.py` (fake `HfApi` via `unittest.mock.patch("huggingface_hub.HfApi")`, fake `JobStage`, patched `time`), adapted to `evaluate(...)`. Add: (a) the built worker script contains `ref.package` and `ref.entrypoint` and NOT `shared.wheel`/`luxury-lakehouse`; (b) `ref.package is None` → `FatalEvaluationError`; (c) ERROR stage → `FatalEvaluationError`, timeout → `TransientEvaluationError` (replacing the old `fail_metrics` assertions).

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement** — as above; the embedded worker body is the lakehouse worker with `evolve.targets.{target}.evaluator` → `importlib.import_module(ref_module)` + `getattr(.., ref_attr)` templated from `ref.entrypoint`.

- [ ] **Step 4: Run → PASS** — grep the generated script in a test to assert no `shared`/`luxury-lakehouse` literal remains.

- [ ] **Step 5: Commit (PAUSE)** — `feat: HFJobsBackend on the 1A port; sever shared.wheel → injected remote_package`

---

## Task A8: `backends/docker.py` — DockerBackend stub

**Files:** Create `ruthless/backends/docker.py`, `tests/backends/test_docker.py`

Verbatim port of `[lakehouse] backends/docker.py` (a not-yet-implemented stub), bridged to the port: `evaluate(...)` raises `FatalEvaluationError("DockerBackend not implemented")` (it cannot silently succeed), `available()` → `False`. (The lakehouse stub returned `fail_metrics()`; under the new taxonomy a not-implemented backend is a fatal config error, not a recorded score.)

- [ ] **Step 1: Failing test** — `available() is False`; `evaluate(...)` raises `FatalEvaluationError`.
- [ ] **Step 2: Run → FAIL**. — [ ] **Step 3: Implement**. — [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit (PAUSE)** — `feat: DockerBackend stub on the 1A port`

---

## Task A9: `backends/remote_worker.py` — generic remote entrypoint runner

**Files:** Create `ruthless/backends/remote_worker.py`, `tests/backends/test_remote_worker.py`

Generalise `[lakehouse] remote_worker.py`: instead of `importlib.import_module(f"evolve.targets.{target}.evaluator")`, accept the **entrypoint** `"module:callable"` as the 5th positional arg and resolve it. Keep the rest verbatim (load candidate JSON, redirect logging to stderr, call `train_and_evaluate(candidate_config, device, epochs, seed, program_path)`, on exception emit `{"combined_score":0.0,"error":1.0,"_error_text":tb}`, print one JSON line). Invocation: `python -m ruthless.backends.remote_worker candidate.json {device} {epochs} {seed} {module:callable} [--program program.py]`.

**H1 boundary:** the worker runs on the node and CANNOT raise across the wire, so on an objective crash it MUST emit the `{error:1, _error_text}` marker — this is the single cross-wire failure signal. The calling backend (A6/A7) detects it via `base.is_objective_failure` and converts it into a `FatalEvaluationError`. The worker never decides scoring; it only reports. (This is why "backends raise" and "the worker emits a marker" are consistent, not contradictory.)

- [ ] **Step 1: Failing test** — port `[lakehouse] test_evolve_evaluator.py::TestRemoteWorkerErrorCapture` (monkeypatch `importlib.import_module` to a fake that raises → assert stdout JSON has `_error_text`, `combined_score=0.0`, `error=1.0`) and add a success case (fake entrypoint returns metrics → printed JSON matches), driving `main()` via patched `sys.argv`/`sys.stdout`.

- [ ] **Step 2: Run → FAIL**. — [ ] **Step 3: Implement**. — [ ] **Step 4: Run → PASS**.

- [ ] **Step 5: Commit (PAUSE)** — `feat: generic remote_worker (entrypoint import string; no evolve.targets)`

---

## Task A10: `config.py` — BackendConfig

**Files:** Modify `ruthless/config.py`, `tests/test_config.py` (extend)

Add `BackendConfig` (port `[lakehouse] config.py:35-55`): fields `type: str`, `device: str = "cuda:0"`, `docker_image/hf_flavor/ssh_host/ssh_user/ssh_remote_dir/ssh_python_path: str | None = None`, validated against `_VALID_BACKEND_TYPES = frozenset({"local_cuda","docker","hf_jobs","remote_ssh"})` and supporting the comma-separated multi-type string. It lives in core `config.py` (a value type; no import of the `backends` package — keeps the import-linter contract).

- [ ] **Step 1: Failing test** — valid `local_cuda` default device; unknown type → `ValidationError`; comma string `"hf_jobs,hf_jobs"` parses to 2 types.
- [ ] **Step 2: Run → FAIL**. — [ ] **Step 3: Implement** (port the model + validator). — [ ] **Step 4: Run → PASS** (port the relevant cases from `[lakehouse] test_evolve_config.py::TestBackendConfig`).
- [ ] **Step 5: Commit (PAUSE)** — `feat: BackendConfig (discriminated backend types; comma multi-type)`

---

## Task A11: `backends/__init__.py` — create_backend registry + pool wiring

**Files:** Modify `ruthless/backends/__init__.py`, `tests/backends/test_create_backend.py`

Port `[lakehouse] backends/__init__.py`: `create_backend(config: BackendConfig, *, timeout: int = 900) -> ComputeBackend` with the deferred-import factory registry (`local_cuda`/`docker`/`hf_jobs`/`remote_ssh`), splitting `config.type` on commas (single → one backend; multiple → `BackendPool([...])`). Lazy backend imports keep `[backends]` deps optional per-backend.

- [ ] **Step 1: Failing test** — `create_backend(BackendConfig(type="local_cuda"))` returns a `LocalCudaBackend`; `type="hf_jobs,hf_jobs"` returns a `BackendPool` of length 2; unknown type → `ValueError`. (No torch/hf needed — construction is lazy.)
- [ ] **Step 2: Run → FAIL**. — [ ] **Step 3: Implement** (port the registry + `create_backend`). — [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit (PAUSE)** — `feat: create_backend registry + BackendPool wiring (comma multi-type)`

---

# Part B — Evolve strategy (`[evolve]` extra)

`EvolveStrategy` is a thin `SearchStrategy` adapter over OpenEvolve: OpenEvolve owns the loop; we own the AST sandbox, config translation, search-space validation, seed caching, and the `EvolveEvaluator` plugin. Per the determinism posture, all tests here use a **fake loop** + fakes — no openevolve loop execution, no GPU/LLM/network.

## Task B1: `strategies/evolve_/sandbox.py` — AST allow-list sandbox

**Files:** Create `ruthless/strategies/evolve_/__init__.py` (empty), `ruthless/strategies/evolve_/sandbox.py`, `tests/strategies/evolve/__init__.py`, `tests/strategies/evolve/test_sandbox.py`

`[lakehouse] code_validator.py` (613 LOC) is **100% domain-free** (verified: imports only `ast` + `dataclasses`; `ValidationProfile` is fully caller-parameterised; ADR-001 referenced by number only). Copy it **verbatim** to `ruthless/strategies/evolve_/sandbox.py`. Public API: `ValidationProfile` (frozen dataclass: `patch_method`, `patch_signature`, `return_shape`, `known_model_attrs`, `allowed_namespaces`, `layers_args`, `rejected_builtins`) and `validate_program(source, profile, *, code_evolution=True) -> tuple[bool, str]` (never raises; SyntaxError → `(False, ...)`).

- [ ] **Step 1: Port the 26 PORTABLE tests** from `[lakehouse] src/tests/test_code_validator.py` — `TestValidationProfile` (1), `TestValidatorAccepts` (10), `TestValidatorRejects` (15). They use a module-level generic `_TEST_PROFILE` (copy it). **Exclude** the 9 DOMAIN tests (`TestScoutGPTProfile` ×8 + `TestSeedPrograms` ×1 reading a ScoutGPT seed file) — those stay in the lakehouse (Part C). Fix imports to `from ruthless.strategies.evolve_.sandbox import ValidationProfile, validate_program`.

- [ ] **Step 2: Run → FAIL** (module not found).
- [ ] **Step 3: Implement** — copy `code_validator.py` verbatim into `sandbox.py` (no edits needed; it is domain-free). Keep ruff/pyright clean (it already is in the lakehouse; re-run the gate).
- [ ] **Step 4: Run → PASS** — `uv run pytest tests/strategies/evolve/test_sandbox.py -v` (26 pass).
- [ ] **Step 5: Commit (PAUSE)** — `feat: evolve AST sandbox (ValidationProfile + validate_program), verbatim port (ADR-001)`

---

## Task B2: `config.py` — EvolveConfig in the strategy union

**Files:** Modify `ruthless/config.py`, `tests/test_evolve_config.py`

Port the evolve config models from `[lakehouse] config.py` into `ruthless/config.py` and add `EvolveConfig` (discriminator `kind="evolve"`) to the strategy union. Models (verbatim except the one domain default): `FitnessConfig` (primary/secondary/combined_weights/minimize + sum-to-1 validator), `EvolutionConfig` (iterations/population_size/num_islands/migration_interval/parallel_evaluations/diff_based/early_stopping_patience/checkpoint_interval/code_evolution), `LLMModelConfig` (name/weight/api_base/api_key_env), `LLMConfig` (models/temperature/max_tokens + weights-sum-to-1), `EvalConfig` (epochs/timeout_seconds/seed — **drop the `dataset` field**, the only domain default at `[lakehouse] config.py:61`; the consumer's `train_and_evaluate`/`RemoteRef` owns data).

```python
class EvolveConfig(BaseModel):
    kind: Literal["evolve"]
    description: str = ""
    fitness: FitnessConfig
    evaluation: EvalConfig = EvalConfig()           # <-- the SINGLE source of truth for epochs/seed (H2.1)
    backend: BackendConfig = BackendConfig(type="local_cuda")
    llm: LLMConfig = LLMConfig()
    evolution: EvolutionConfig = EvolutionConfig()
    # NEW — everything the OpenEvolve worker subprocess needs to REBUILD the evaluator + a config-derived
    # RemoteObjective is serialisable here (H2.2). Callables are passed as "module:callable" import-strings
    # (resolved via importlib in BOTH the in-process path and the worker — same trusted-config convention
    # as the 1A CLI objective loader), because a ProcessPoolExecutor worker gets no live Python objects.
    entrypoint: str                          # "module:callable" → RemoteRef.entrypoint (consumer's train_and_evaluate)
    remote_package: str | None = None        # PEP-723 install spec → RemoteRef.package (None for ssh/local)
    seed_programs_dir: str                   # dir of seed .py programs the run starts from
    prompt_template_dir: str | None = None   # OpenEvolve prompt templates
    search_space_validator: str | None = None  # "module:callable" -> (config)->(ok, reason); None = no extra gate
    validation_profile: str | None = None    # "module:ATTR" -> a ValidationProfile constant (required if evolution.code_evolution)
    pre_validate: str | None = None           # "module:callable" -> (config)->config pre-validation hook (default identity)

StrategyConfig = Annotated[Union[RandomConfig, EvolveConfig], Field(discriminator="kind")]
```
(`target: str` from the lakehouse `EvolveConfig` is replaced by `entrypoint` + `seed_programs_dir` + the hook import-strings — the `evolve.targets.<target>` conventions become explicit, serialisable config. `EvalConfig` drops `dataset`. A `model_validator` requires `validation_profile` when `evolution.code_evolution` is True.)

- [ ] **Step 1: Failing test** — port the PORTABLE cases from `[lakehouse] test_evolve_config.py` (FitnessConfig sum-to-1, BackendConfig unknown-type, LLM weights sum-to-1, EvolutionConfig code_evolution default) into `tests/test_evolve_config.py`; add: `RuthlessConfig.model_validate({"strategy": {"kind": "evolve", "fitness": {...}, "entrypoint": "m:f", "seed_programs_dir": "seeds"}})` yields an `EvolveConfig`; the `random` kind still validates (union intact).
- [ ] **Step 2: Run → FAIL**. — [ ] **Step 3: Implement**. — [ ] **Step 4: Run → PASS** (+ existing `tests/test_config.py` random cases stay green).
- [ ] **Step 5: Commit (PAUSE)** — `feat: EvolveConfig in the strategy union (+ Fitness/Evolution/LLM/Eval; entrypoint/seed_dir injected)`

---

## Task B3: `strategies/evolve_/evaluator.py` — EvolveEvaluator (OpenEvolve plugin)

**Files:** Create `ruthless/strategies/evolve_/evaluator.py`, `tests/strategies/evolve/test_evolve_evaluator.py`

Port `[lakehouse] evaluator.py::EvolveEvaluator`, **generalised** so it has no `evolve.targets` coupling. It is the OpenEvolve evaluator plugin: OpenEvolve calls `evaluate(program_path: str) -> EvaluationResult` (from `openevolve.evaluation_result`). Changes from the lakehouse:
1. **Search-space validation is injected.** Replace the `validate_search_space(config, target)` dispatch to `evolve.targets.<target>.search_space` with a constructor-injected `search_space_validator: Callable[[dict], tuple[bool, str]] | None = None` (None = no extra search-space gate).
2. **Drop the `conditioning_type="additive"` patch** (`[lakehouse] evaluator.py:229`, ScoutGPT-specific) — if a consumer needs a pre-validation mutation, it provides an injected `pre_validate: Callable[[dict], dict] | None` hook (default identity).
3. **Backend call uses the 1A port.** Hold a `ComputeBackend` + a `RemoteObjective` (the consumer objective). For a candidate program, build a `Candidate(id=<program id>, params=config, program=<source if Level-2 else None>)` and call `backend.evaluate(candidate, objective, timeout=...)`.
4. **The SINGLE failure→sentinel mapping point (H1).** Wrap the `backend.evaluate(candidate, objective, timeout=...)` call in `try/except Exception` — this is the ONLY place a failure becomes a recorded score, because OpenEvolve needs a metrics dict per candidate (a crashed candidate must score worst so the search avoids it). Map to `EvaluationResult(metrics={"combined_score": 0.0, "error": 1.0}, artifacts={"error": <text>, "failure_kind": <kind>})`. Distinguish, for honest diagnostics: `FatalEvaluationError` → `failure_kind="objective"` (a genuinely bad candidate); `TransientEvaluationError` (pool retries exhausted) → `failure_kind="infra"` logged at WARNING (a good candidate that couldn't be evaluated — recorded as a sentinel only because OpenEvolve requires a score, NOT a real verdict on the candidate). Success → `EvaluationResult(metrics={**raw, "combined_score": <weighted>})`. Keep `_load_program`/`_extract_config`/`Program`/`_compute_combined_score` verbatim (domain-free). The evaluator's hooks (`search_space_validator`, `validation_profile`, `pre_validate`) are RESOLVED CALLABLES/objects, supplied by whoever builds the evaluator — the in-process path passes them directly; the worker (B4) resolves them from the `EvolveConfig` import-strings (via `_resolve_hook`, type-checked — L-B). The evaluator code itself never imports a consumer module. **Docstring note for the next reader (accepted trade-off):** a `failure_kind="infra"` candidate is still recorded as `combined_score=0` because OpenEvolve requires a per-candidate score — so transient infra flakiness *can* evict an otherwise-good candidate from the population. This is inherent to OpenEvolve; we mitigate only by tagging it distinctly + WARNING (strictly better than the lakehouse's undifferentiated `fail_metrics`).

- [ ] **Step 1: Failing test** — port the PORTABLE evaluator tests (`TestEvolveEvaluator` dispatch+score, `TestLoadProgram`, `TestEvaluatorValidationGate`, `TestErrorTextCapture`) adapted: backend is a fake `ComputeBackend` (records the `Candidate` it got, returns metrics); objective is a fake `RemoteObjective`; assert (a) `evaluate(program_path)` calls `backend.evaluate` with a `Candidate` carrying the parsed config in `.params` and the source in `.program` for Level-2; (b) weighted `combined_score`; (c) an `import os` in `custom_embed` is rejected by the sandbox before dispatch; (d) a backend `FatalEvaluationError` → `EvaluationResult` `combined_score=0.0` + `artifacts["failure_kind"]=="objective"` (not raised); (e) a backend `TransientEvaluationError` → sentinel with `artifacts["failure_kind"]=="infra"` (H1 distinction); (f) an injected `search_space_validator` returning `(False, "bad")` blocks dispatch.

- [ ] **Step 2: Run → FAIL**. — [ ] **Step 3: Implement** (port + the 4 generalisations; `from openevolve.evaluation_result import EvaluationResult`). — [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit (PAUSE)** — `feat: EvolveEvaluator (OpenEvolve plugin; injected search-space validator; backend via 1A port; fail_metrics mapping)`

---

## Task B4: `strategies/evolve_/strategy.py` — EvolveStrategy over OpenEvolve

**Files:** Create `ruthless/strategies/evolve_/strategy.py`, `tests/strategies/evolve/test_evolve_strategy.py`

Port `[lakehouse] runner.py` into `EvolveStrategy` implementing the 1A `SearchStrategy` port: `run(self, objective, *, backend) -> Result`. It owns the orchestration around `openevolve.run_evolution`:
- `_translate_to_openevolve_config(cfg: EvolveConfig) -> dict` — verbatim port (`max_iterations`, `diff_based_evolution`, `early_stopping_patience`, `checkpoint_interval`, `database.{population_size,num_islands,migration_interval}`, `evaluator.{parallel_evaluations,timeout}`, `prompt.template_dir` ← `cfg.prompt_template_dir`, `llm.models[*]` ← `cfg.llm`).
- **Objective lifecycle + worker reconstruction (H2 — the trickiest task, specified).** OpenEvolve runs evaluators in `ProcessPoolExecutor` workers (verified: lakehouse `runner.py` writes `_openevolve_evaluator_config.json` and each worker rebuilds the evaluator). A live `RemoteObjective` cannot cross into a worker, so **`EvolveConfig` is the single serialised source of truth** and the worker rebuilds a **config-derived `RemoteObjective`**:
  - A helper `_remote_objective_from_config(cfg: EvolveConfig) -> RemoteObjective` builds a `_ConfigRemoteObjective` whose `remote_ref = RemoteRef(entrypoint=cfg.entrypoint, package=cfg.remote_package)`, `epochs = cfg.evaluation.epochs`, `seed = cfg.evaluation.seed`, and whose `evaluate(candidate)` is the local-entrypoint fallback (M2).
  - `_write_evaluator_script(...)` emits a standalone script that imports `ruthless.strategies.evolve_.{evaluator,strategy}` (NOT `evolve.*`), loads the companion `evaluator_config.json` (the serialised `EvolveConfig`), and reconstructs: the config-derived `RemoteObjective` (via the helper), the per-worker `ComputeBackend` (`create_backend(cfg.backend)`), and the `EvolveEvaluator` with its hooks resolved from the `cfg` import-strings. Resolution uses a shared `_resolve_hook(import_string, *, expect)` that mirrors the 1A `cli.resolve_objective` pattern — `importlib.import_module` + `getattr` (**never `eval`**) — and **validates the resolved object's type with a clear error (L-B):** `search_space_validator`/`pre_validate` must be callable; `validation_profile` must be a `ValidationProfile` instance; otherwise `raise FatalEvaluationError(f"{import_string!r} did not resolve to {expect}")`. The in-process path (fake-loop tests, single-process runs) uses the SAME helper + `_resolve_hook`, so the two representations are provably identical (both derive from one `cfg`).
  - **`run(objective, *, backend)` contract:** first **guard `isinstance(objective, RemoteObjective)`** (L-C) — a plain `Objective` raises `FatalEvaluationError("EvolveStrategy requires a RemoteObjective; build one with _remote_objective_from_config(cfg)")`, never a bare `AttributeError`. `epochs/seed` are canonical from `cfg.evaluation` (H2.1). The strategy then ASSERTS the passed objective agrees with `cfg` on **all** config-derived fields — `remote_ref`, `epochs`, AND `seed` (L-A) — raising a single loud config error on any divergence (no silent cfg override of a caller's differing epochs/seed). So the object handed to `run()` and the one the workers rebuild can never diverge. (If a caller passes the config-derived objective itself — the common path — the assert is trivially satisfied.)
- Seed cache/resume — port `_eval_fingerprint` (SHA-256 of `epochs:seed` — drop `dataset`), `_load_cached_seeds`, `_evaluate_seeds`; seed program discovery reads `cfg.seed_programs_dir` (injected) instead of `evolve.targets.<target>/seed_programs`.
- `_set_api_keys(cfg)` — port (warns on unset `api_key_env`).
- Invocation — `oe_cfg = openevolve.Config.from_dict(...)`; `best = openevolve.run_evolution(initial_program=<best seed>, evaluator=<script path>, config=oe_cfg, iterations=cfg.evolution.iterations, output_dir=<results_dir>)`.
- Result mapping — `Result(best=Evaluation(Candidate(id="best", params={}, program=best.best_code), metrics=best.metrics, ok=True), history=[...seed evals...], diagnostics={"best_score": best.best_score}, provenance={"strategy": "evolve", "iterations": ..., "num_islands": ..., "checkpoint_dir": str(results_dir)})`. `openevolve` is imported lazily inside `run` (guarded `try/except ImportError` → clear message) so importing the module without the extra doesn't fail.

- [ ] **Step 1: Failing test (FAKE LOOP — the core orchestration golden)** — `monkeypatch.setattr("openevolve.run_evolution", fake)` where `fake` records its kwargs and returns a stub with `.best_code/.metrics/.best_score`; also fake `openevolve.Config.from_dict`. Assert: (a) `EvolveStrategy(cfg).run(objective, backend=fake_backend)` returns a `Result` whose `best.candidate.program` == the stub `best_code` and `best.metrics` == stub metrics; (b) `_translate_to_openevolve_config` maps `num_islands`/`iterations`/`llm` correctly (unit test, no openevolve); (c) seed-cache resume: pre-write a cached seed result with a matching fingerprint → `_evaluate_seeds` skips it (no backend call), changing `seed` invalidates it (port `[lakehouse] TestSeedResume`); (d) **H2:** `_remote_objective_from_config(cfg)` yields a `RemoteObjective` with `remote_ref.entrypoint == cfg.entrypoint`, `epochs == cfg.evaluation.epochs`, `seed == cfg.evaluation.seed`; the worker evaluator-script, given the serialised `cfg` JSON, resolves the same hooks (assert via a fake `cfg` whose `search_space_validator`/`validation_profile` import-strings point at in-test module attrs); `run()` with an objective whose `remote_ref` disagrees with `cfg` raises a loud config error. No real openevolve loop runs.
- [ ] **Step 2: Run → FAIL**. — [ ] **Step 3: Implement** (port + the injections). — [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit (PAUSE)** — `feat: EvolveStrategy over OpenEvolve (config translation + seed resume + Result mapping)`

---

## Task B5: `e2e/test_evolve_orchestration_gate.py` — standing orchestration golden (fake loop)

**Files:** Create `tests/e2e/test_evolve_orchestration_gate.py`

The standing evolve CI gate (spec C-A): proves **our orchestration** is preserved without reproducing OpenEvolve's stochastic search. One end-to-end pass with `openevolve.run_evolution` monkeypatched to a deterministic fake loop that, for a small fixed list of candidate programs, drives them through the **real** `EvolveEvaluator` (real AST sandbox + real `BackendPool` over fake in-process backends). Asserts: (a) a program with `import os` in `custom_embed` is sandbox-rejected (verdict golden); (b) valid programs dispatch through the pool in priority order and their metrics flow back; (c) a `TransientEvaluationError` from one fake backend is retried on the next (pool contract); (d) the returned `Result` aggregates best + history. No GPU, no LLM, no network, no real openevolve loop.

- [ ] **Step 1: Write the gate** (fake loop + fake backends + real evaluator/sandbox/pool).
- [ ] **Step 2: Run → PASS** — `uv run pytest tests/e2e/test_evolve_orchestration_gate.py -v`.
- [ ] **Step 3: Commit (PAUSE)** — `test: evolve orchestration gate (fake loop; sandbox verdict + pool dispatch; no GPU/LLM)`

---

# Part C — Lakehouse consumer migration (WRITE-ONLY; executes later in the lakehouse repo)

> This part is **not executed in this session** (user decision): it touches the second repo (`luxury-lakehouse`), and its full acceptance ("lakehouse evolve run reproduces a golden trajectory") needs GPU + LLM infra. It is a precise migration checklist to execute later, in the lakehouse repo, once 1B (Parts A+B) ships to PyPI/TestPyPI or is installed via a path/wheel. Granularity is intentionally coarser than A/B (no in-repo TDD here).

**Goal:** make lakehouse evolve a consumer of `ruthless[evolve,backends]`; delete the extracted general code; keep `src/evolve/targets/*` (the soccer-domain consumers).

- [ ] **C1 — Add the dependency.** Add `ruthless[evolve,backends]` to the lakehouse `pyproject.toml` (path/wheel dep until ruthless is on PyPI). Confirm `openevolve`, `huggingface_hub`, `docker` resolve transitively.
- [ ] **C2 — Delete the extracted modules; import from ruthless.** **HARD GATE (L3 — do not delete before the replacement is proven):** only proceed once (1) `ruthless[evolve,backends]` is installed and imports in the lakehouse env, (2) the ruthless B5 orchestration gate is green, and (3) C3's `RemoteObjective`s + C5's hooks are wired and the lakehouse evolve tests pass importing `ruthless.*`. First switch imports and confirm green, THEN remove the old files in a separate commit — never delete the lakehouse code before its replacement imports. Remove `[lakehouse] src/evolve/{backends/*, code_validator.py, config.py, evaluator.py, runner.py, remote_worker.py}`. Replace every `from evolve.backends... / evolve.code_validator / evolve.config / evolve.evaluator / evolve.runner / evolve.remote_worker` import (in `targets/*`, `scripts/*`) with the `ruthless.*` equivalents (`ruthless.backends`, `ruthless.strategies.evolve_.sandbox`, `ruthless.config`, `ruthless.strategies.evolve_.evaluator`, `ruthless.strategies.evolve_.strategy`).
- [ ] **C3 — Provide a `RemoteObjective` per target.** For each target (`scoutgpt`, `football2vec`, `football2vec_stage2`): wrap its existing `train_and_evaluate(candidate_config, device, epochs, seed, program_path)` (unchanged — it already matches the standard remote entrypoint contract) in a `RemoteObjective` exposing `remote_ref = RemoteRef(entrypoint="evolve.targets.<t>.evaluator:train_and_evaluate", package=<lakehouse wheel spec>)` and `epochs`/`seed` from config. Keep `evaluate(candidate)` as a thin local call to `train_and_evaluate` with a default device.
- [ ] **C4 — Sever `shared.wheel` via injected `remote_package`.** The lakehouse wheel URL that was `from shared.wheel import WHEEL_BASE_URL` becomes the `RemoteRef.package` value (e.g. `f"luxury-lakehouse[analytics,training] @ {WHEEL_BASE_URL}"`), passed through `EvolveConfig.remote_package` / the target's `RemoteRef`. `shared.wheel` stays in the lakehouse but is now READ by the consumer to build the ref — `ruthless` never imports it.
- [ ] **C5 — Provide search-space validation + sandbox profile + seed/prompt dirs as consumer config.** Each target keeps its `search_space.validate_candidate` (injected into `EvolveEvaluator` as `search_space_validator`), its `ValidationProfile` (e.g. `SCOUTGPT_PROFILE`), its `seed_programs/` dir (→ `EvolveConfig.seed_programs_dir`), and its `prompts/` dir (→ `prompt_template_dir`). The ScoutGPT `conditioning_type="additive"` patch becomes the injected `pre_validate` hook.
- [ ] **C6 — Keep the DOMAIN tests in the lakehouse.** `test_code_validator.py::TestScoutGPTProfile`/`TestSeedPrograms`, `test_evolve_evaluator.py::TestSearchSpaceValidation`/`TestPerTargetDispatch`, and `test_evolve_pin_drift.py` stay (they assert ScoutGPT/Football2Vec specifics). Rewrite their imports to `ruthless.*` for the generic symbols (`ValidationProfile`, `validate_program`, `EvolveEvaluator`).
- [ ] **C7 — Acceptance (out-of-band, infra-bound).** (a) The ruthless orchestration gate (B5) is the standing behaviour-preservation proof. (b) A one-time lakehouse smoke run — a single short evolve run (few iterations, real or fake LLM) — confirms the migrated consumer wires end-to-end and our orchestration parts (sandbox verdict, BackendPool dispatch) match pre-migration behaviour. Per spec C-A, this is **NOT** a trajectory-identity check and is **not** a recurring CI gate.
- [ ] **C8 — Commit in the lakehouse repo** (separate from this repo's history).

---

## Final: import-linter + CI + full gate (Task Z)

**Files:** verify `.importlinter`, `.github/workflows/ci.yml`

- [ ] **Step 1: Contracts** — `uv run lint-imports` → "Contracts: 3 kept" (core-isolation incl. `ruthless.remote`; strategy-isolation; backends-isolation). Confirm `strategies.evolve_` imports only the core port (`ruthless.backend`/`ruthless.remote`/`ruthless.config`/`ruthless.result`/`ruthless.errors`) + `openevolve`, never `ruthless.backends`.
- [ ] **Step 2: Full local gate** — `uv run ruff check ruthless tests && uv run ruff format --check ruthless tests && uv run pyright && uv run lint-imports && uv run pytest -v` (core + backends + evolve fake-loop legs). Expected all green.
- [ ] **Step 3: `/final-review`** (the pre-commit gate) — review code + docs, regenerate `docs/c4/architecture.html` to include the `backends` + `evolve_` containers/components.
- [ ] **Step 4: Commit (PAUSE)** — `ci: 1B import-linter + CI legs; C4 diagram refresh`

---

## Test strategy summary

- **Unit (fast, no services):** `remote.py`; `Candidate.program`; `backends.base` helpers; `BackendPool` dispatch + transient-retry (ported lakehouse 8 + retry/timeout); each backend with fakes (`subprocess`/`HfApi` patched), asserting the **bridged `evaluate` signature**, the entrypoint resolution, and the **raise-not-fail_metrics** error model; `create_backend`/`BackendConfig`; the AST sandbox (26 portable); `EvolveConfig` union; `EvolveEvaluator` (fake backend/objective); `EvolveStrategy` with the fake loop.
- **E2E (self-contained):** the evolve **orchestration gate** (B5) — fake loop + real sandbox/pool/evaluator over fake backends. The 1A determinism+convergence gate stays green (unchanged).
- **Determinism posture (C-A):** NO trajectory-identity golden; OpenEvolve's stochastic loop is not reproduced. Behaviour-preservation = our orchestration (sandbox verdict + pool dispatch) only. No GPU/LLM/network in CI.
- **Deferred:** the lakehouse domain reproduction (Part C7) is out-of-band and infra-bound; `CachedObjective`/`assert_cache_equivalence` are Phase 2.

---

## Self-Review

**Spec §9 Phase 1B coverage:** `EvolveStrategy` thin adapter over OpenEvolve → B4; `BackendPool` + SSH/HF-Jobs/Docker → A4–A8; sever `shared.wheel` (the two `hf_jobs.py` touch points + remote import path) → A7 + A9 + C4; dataset default removed → B2; AST sandbox `[evolve]` → B1; lakehouse evolve becomes first consumer → Part C; `CachedObjective` deferred → noted (Phase 2); ships 0.x → unchanged. Backend-port reconciliation (the one open 1A↔1B tension) → settled one-port, Central design decision + A2.

**Placeholder scan:** verbatim ports reference the exact lakehouse source files (the source IS the content — `code_validator.py` copied as-is; backends ported with the three enumerated changes each); new/changed code (RemoteRef/RemoteObjective, `base.py`, `BackendPool`, `local_cuda`, config models, the EvolveEvaluator generalisations, EvolveStrategy mapping) is shown in full or specified change-by-change with exact signatures. No "TBD"/"handle errors"/"similar to".

**Type consistency:** `RemoteRef(entrypoint, package=None)`; `RemoteObjective.{evaluate, remote_ref, epochs, seed}`; `Candidate(id, params, program=None)`; backend port `evaluate(candidate, objective, *, timeout=None) -> Metrics` + `available() -> bool` (1A, unchanged) across all backends; `BackendPool(backends, *, max_retries=2)`; standard remote entrypoint `train_and_evaluate(*, candidate_config, device, epochs, seed, program_path) -> dict[str,float]`; `EvolveConfig(kind="evolve", ..., entrypoint, seed_programs_dir, prompt_template_dir=None, remote_package=None)`; `EvolveStrategy.run(objective, *, backend) -> Result`; error taxonomy `Transient`/`FatalEvaluationError` (1A) used consistently (raised by backends, retried/surfaced by the pool, mapped to `EvaluationResult` by the evaluator).

**rev-2 review coverage (lakehouse-d32):** H1 → unified error model (one rule; backends raise transport-only, objective failures map to the sentinel ONLY in `EvolveEvaluator`; worker marker → backend raise) across Central decision + A3 (`is_objective_failure`) + A5/A6/A7/A9 + B3. H2 → `EvolveConfig` single source of truth + config-derived `RemoteObjective` worker reconstruction (B2 fields + B4 `_remote_objective_from_config` + run() assert; `cfg.evaluation` canonical for epochs/seed). M1 → `program_to_path` (A3) used by all backends. M2 → `evaluate()` documented as a real local fallback (A2). M3 → epochs/seed-on-objective rationale + device asymmetry (A2). L1 → entrypoint docstring no longer over-claims signature identity. L3 → Part C delete hard-gated (C2).

**Open items flagged for the user's review (write-only plan):** (1) `openevolve>=0.2.0` must resolve + import on PyPI for the `[evolve]` CI leg — if not, A0 Step 4 stops (L2); (2) Part C executes later in the lakehouse repo, behind the C2 hard-gate; (3) the `run()` assert that the passed objective's `remote_ref` matches `cfg` (B4) assumes the common path where the consumer builds the objective from the same config — confirm that ergonomics is acceptable vs. having `run()` build the objective itself.
