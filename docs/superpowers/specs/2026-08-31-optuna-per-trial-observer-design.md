# Spec — neutral per-trial observer for `OptunaStrategy`

**Date:** 2026-08-31
**Status:** rev 2 — spec review round 1 (resume-path wording) and the plan review's round 1 both
incorporated. The plan review surfaced that §1.1's `Observer.__call__` was declared with a *named*
parameter, which under pyright basic is NOT satisfied by `list.append`/`lambda e` (the "any callable"
claim was false); fixed here to POSITIONAL-ONLY (`event: ProgressEvent, /`), verified with pyright
basic (0 errors). Design/translator/field set otherwise unchanged.
**Baseline:** `4406e84`, tag `v0.4.0`, version `0.4.0`, clean tree
**Origin:** a change request from a lakehouse session. Consumers migrating raw-Optuna workflows onto
`OptunaStrategy` lose Optuna's per-trial callbacks (progress bars, live metric sinks such as MLflow).
The request asks for an optional neutral observer on `OptunaStrategy.run`. This spec **accepts** it,
locks four design decisions the requester left open (naming, fault policy, port scope, ceremony), and
records the Optuna callback semantics that were **measured, not assumed**. The originating request is
quoted **verbatim in Appendix A** so request-faithfulness is independently verifiable rather than
resting on this paraphrase.
**Target release:** `0.5.0` — minor, because the public API gains two names (`Observer`, `ProgressEvent`)
and `OptunaStrategy.run` gains an optional keyword argument. Nothing is removed or renamed; **no digest
bytes change**, so this release is *not* cache-invalidating.
**Design bar (user directive):** best practice, long-term, gold standard in general — applied as a lens
in §1.4 (why the types are strategy-agnostic) and §2.4 (why the port stays honest rather than uniform).

---

## 0. Summary of decisions

| Item | Verdict | Note |
|---|---|---|
| Add an optional per-trial observer to `OptunaStrategy.run` | **ACCEPT** | The capability is general and the guardrails are met. §2. |
| A neutral event **value type** + an `Observer` **Protocol** in the core | **ACCEPT** | Both are pure stdlib; core gains no optuna/MLflow/logging-sink dependency. §1. |
| Event name — requester proposed `TrialEvent` | **REJECT `TrialEvent` → `ProgressEvent`** | "Trial" is Optuna's noun; the core's vocabulary is Candidate/Evaluation. A neutral name keeps the leak out of the public surface. §1.2, confirmable at review. |
| Observer that raises mid-run | **CATCH + LOG + CONTINUE** | Measured: a raw callback exception aborts `study.optimize` (§0.1 claim 5). A telemetry sink must never abort the search. Logged at `warning`, not silent. §2.4. |
| Port scope — Optuna-only kwarg vs. add to the `SearchStrategy` port | **OPTUNA-ONLY, port unchanged** | Not YAGNI — *honesty*. A port-level `observer` that random/evolve accept-and-ignore is a silent no-op interface. §2.5. |
| `state` representation on the event | **NEUTRAL `str`, not Optuna's `TrialState`** | A core enum leak would break `core-isolation`; a `str` is forward-compatible (a future backend state is a new string, not a public-enum extension). §1.2, confirmable at review. |
| Ceremony | **spec → plan → TDD → `/final-review` → commit on approval** | New public-API surface is a Hyrum's-Law compatibility surface (as `fingerprint` became); pin naming + the resume/fault contract before code. |

### 0.1 What the change request relies on, verified rather than assumed

The request's correctness hinges on Optuna's `study.optimize(callbacks=[...])` semantics. All five load-
bearing claims were **executed** against the installed `optuna==4.8.0` (the project pins `optuna>=4.0`)
in a throwaway probe, not reasoned about. Verbatim outcomes:

1. **Fires once per trial, fully populated.** 3 trials → 3 callbacks, each `FrozenTrial` carrying
   `number`, `params`, `value` (the scored metric), **all** `user_attrs` (`loss` *and* the auxiliary
   `aux`), and `state == COMPLETE`. So the neutral event can be built entirely from the frozen trial,
   and it can carry every metric — not just the scored one.
2. **Resume fires only the newly-run trials.** With a SQLite store and `load_if_exists=True`: run 1
   (`n_trials=2`) → callbacks for trials `[0, 1]`; a fresh process resuming the same store and running
   2 more → callbacks for `[2, 3]` **only**. The persisted trials do **not** re-fire. The observer is a
   *live* per-trial hook; it is **not** a replay of the store. (`Result.history`, reconstructed from
   `study.trials`, still spans the whole store — the two are deliberately different surfaces. §3.2.)
3. **The warm-start enqueued trial fires** as trial `0`, with the enqueued params (`{"x": 7.5}`).
4. **A raising objective (default `catch=()`) does not fire the callback for the failed trial and the
   exception propagates.** Trial 1 raised → callbacks fired for `[0]` only (state `COMPLETE`), and the
   `RuntimeError` propagated out of `optimize`. This matches the strategy's existing fatal-metric
   contract: a non-finite scored metric raises `FatalEvaluationError`, aborts the study, and is never
   recorded — and now, never observed either.
5. **An exception raised inside a callback propagates out of `optimize`.** This is the entire
   justification for §2.4's wrapper: without fault isolation, a buggy progress sink kills the search.

The probe is throwaway and is not part of the library; §4 institutionalises each claim as a test.

---

## 1. The core contract

Two additions to the pure core, both stdlib-only. The core's dependency-lightness is preserved and the
`core-isolation` import-linter contract is untouched (§1.3).

### 1.1 `Observer` — the port

A minimal single-method port, placed with the other strategy-execution port (`SearchStrategy`) in
`ruthless/strategy.py`:

```python
class Observer(Protocol):
    """A per-candidate progress sink. Called once per completed evaluation, in evaluation order,
    with a ProgressEvent. `event` is POSITIONAL-ONLY (the `/`) so ANY one-argument callable conforms
    regardless of its own parameter name — a function, a `lambda`, or a bound method like
    `list.append`. Implementations MUST NOT assume they see every candidate a run produced: they
    observe only the candidates evaluated in the call they were passed to (see the resume semantics in
    the OptunaStrategy docstring). An Observer that raises must not be able to abort the search — the
    strategy isolates it (logs and continues)."""

    def __call__(self, event: ProgressEvent, /) -> None: ...
```

Design notes (gold-standard rationale):

- **Single-abstract-method / callable protocol, with a positional-only parameter.** Any plain
  function, lambda, `functools.partial`, or bound method (`list.append`) satisfies it structurally —
  the ergonomic "one obvious way" for a progress sink — while it is still a *named port type* in the
  core, satisfying the change request's guardrail that "the event type + Protocol live in the
  core/ports" (Appendix A). This is the GoF Observer pattern reduced to its Pythonic minimum. **The
  `/` is load-bearing:** under pyright basic (this project's mode), a protocol whose `__call__`
  parameter is *named* `event` is only satisfied by callables whose own parameter is also named
  `event`, so `list.append` and `lambda e: …` would silently stop conforming. Declaring `event`
  positional-only removes the name from the contract. Verified with pyright basic (0 errors for
  `list.append`, `lambda e`, `def f(event)`, and `def f(e)`); a test in the plan pins it so a future
  removal of the `/` fails the type gate.
- **Not `runtime_checkable`.** Unlike `Objective` (which the CLI isinstance-guards), an `Observer` is
  never isinstance-checked; a `runtime_checkable` `__call__` protocol would make `isinstance(x, Observer)`
  true for *any* callable, which is a misleading guard. Its absence is deliberate and will carry a
  one-line comment saying so.
- **No lifecycle methods now (`on_run_start`/`on_run_end`).** Deliberately deferred, not forgotten
  (§6). A single per-candidate event is the minimal neutral primitive; lifecycle hooks, if ever needed,
  are an additive second protocol or additional event types — they do not force a change here.

### 1.2 `ProgressEvent` — the value type

An immutable value object, placed with the other value types (`Candidate`, `Evaluation`, `Result`) in
`ruthless/result.py`:

```python
@dataclass(frozen=True)
class ProgressEvent:
    """One observation of a completed candidate evaluation, handed to an Observer. Neutral across
    strategies: it names no strategy-specific concept. `number` is the STUDY-GLOBAL trial number — it
    matches `Candidate.id` (`t{number}`) and the returned `Result.history`, and does NOT reset on
    resume (a resumed run observes continued numbers such as 20..49, never a fresh 0..29). `metrics`
    carries every recorded metric (the scored one plus any auxiliaries), so a sink need not know which
    key the strategy optimises. `state` is a neutral lowercase string (e.g. "complete"), never a
    backend's own state enum."""

    number: int
    candidate: Candidate
    metrics: Metrics
    state: str
```

Rationale for each field and the rejected shapes:

- **`number` is the study-global trial number, not a per-call counter.** It equals the integer in
  `Candidate.id` (`t{number}`) and the matching `Result.history` entry, and it does **not** reset on
  resume: a resumed call that runs trials 20–49 fires events with `number` 20…49. This is proven in the
  tree — `tests/e2e/test_optuna_resume_gate.py:43,62` assert the store's trial numbers span `range(n)`
  across a resume — and it is exactly the value Optuna's callback passes (`ft.number`, §0.1 claim 2).
  **Consequence for the headline use case:** a progress-bar sink wanting a *per-run* fraction must
  count the events it receives, not compute `number / budget` — the latter exceeds 100% on every
  resumed study. The translator is correct; this bullet exists so the docstring never again implies a
  per-run ordinal.
- **`candidate` + `metrics` mirror `Evaluation` exactly** (`_to_eval` already builds `Candidate(id=…,
  params=dict(t.params))` and `metrics=dict(t.user_attrs)`), so the observer sees the same values the
  returned `Result.history` will. The scored metric is `event.metrics[<the metric you configured>]` —
  identical to Optuna's `frozen_trial.value` (the strategy writes both from the same number). We do
  **not** duplicate a `score` field: it would be a second source of truth for a value already present.
- **`state` is a `str`, not an enum.** Optuna's `TrialState` cannot appear on a core type without
  breaking `core-isolation`. A neutral `str` is also the more forward-compatible choice: a future
  strategy/backend state ("pruned", "failed") is a new string, not a public-enum extension every
  consumer must now handle. The one value emitted today is `"complete"` (§0.1 claim 1). A str-enum
  (like the existing `Direction(str, Enum)`) was considered and declined for a single-member enum;
  this is confirmable at review if you prefer the typed form.
- **Named `ProgressEvent`, not `TrialEvent`/`EvaluationEvent`/`CandidateEvaluated`.** `TrialEvent`
  leaks Optuna's noun into a neutral type. `EvaluationEvent` near-collides with the existing
  `Evaluation` value type (reader confusion). `CandidateEvaluated` (a DDD past-tense domain event) is
  the strongest alternative and is a fine second choice; `ProgressEvent` is recommended because it
  pairs cleanly with `Observer` and reads unambiguously as the observability signal. **This naming is
  the one item most worth your explicit confirmation at review.**

### 1.3 Placement keeps `.importlinter` and the lean import untouched

Both names live in modules already listed under the `core-isolation` contract's `source_modules`
(`ruthless.result`, `ruthless.strategy`), so **no `.importlinter` edit is required** and no new
core module is introduced. `strategy.py` already imports from `result.py`, so `Observer`'s reference to
`ProgressEvent` adds no new edge. `import ruthless` continues to pull neither optuna nor MLflow —
guaranteed by the existing `test_top_level_import_does_not_require_optional_extras` and reinforced by
the new sink-free test (§4).

### 1.4 Why the types are strategy-agnostic though only Optuna wires them

The gold-standard, long-term shape is a *neutral* observability contract in the core that **any**
strategy could adopt faithfully and additively, paired with wiring only where the semantics are honest
today (§2.5). The types name no Optuna concept: `number`/`candidate`/`metrics`/`state` describe "a
candidate was evaluated", which is true of every strategy. So `RandomSearchStrategy` or a future
strategy can grow an `observer=` parameter later with **zero change** to `Observer`/`ProgressEvent` and
no break to consumers. The contract is designed once, correctly; the wiring rolls out incrementally.

---

## 2. The Optuna translation

All of §2 lives in `ruthless/strategies/optuna_/strategy.py`. It imports the two core types (allowed:
strategy → core); the core imports nothing back.

### 2.1 Signature

```python
def run(self, objective: Objective, *, backend: ComputeBackend, observer: Observer | None = None) -> Result:
```

Keyword-only (after the existing `*`), defaulting to `None`. `observer=None` reproduces **today's exact
call** (`callbacks=None`, §2.3) — byte-for-byte the current behaviour, which is what makes the change
non-regressing. The added optional parameter is a compatible widening of the `SearchStrategy.run`
signature, so `OptunaStrategy` remains structurally a `SearchStrategy` (verified under pyright in §4).

### 2.2 `FrozenTrial → ProgressEvent`

A private translator mirroring the existing `_to_eval` so the observer and `Result.history` never
disagree about a candidate's values:

```python
def _to_event(ft: Any) -> ProgressEvent:
    return ProgressEvent(
        number=ft.number,
        candidate=Candidate(id=f"t{ft.number}", params=dict(ft.params)),
        metrics=dict(ft.user_attrs),   # every recorded metric — matches _to_eval
        state=ft.state.name.lower(),   # neutral string; "complete" in practice (§0.1 claim 1)
    )
```

At callback time every field is populated: the strategy's `_objective` calls `trial.set_user_attr(k, v)`
for every metric **before** returning, and Optuna invokes callbacks after the trial is stored, so
`ft.user_attrs`, `ft.value`, `ft.params`, `ft.number`, and `ft.state` are all present (§0.1 claim 1).

### 2.3 Wiring via `study.optimize(callbacks=...)`

```python
def _observer_callback(study: Any, ft: Any) -> None:
    try:
        observer(_to_event(ft))
    except Exception:  # noqa: BLE001 — a telemetry sink must never abort the search (§2.4)
        _log.warning("observer_failed", extra={"trial": ft.number}, exc_info=True)

callbacks = [_observer_callback] if observer is not None else None
if remaining:
    study.optimize(_objective, n_trials=remaining, callbacks=callbacks)
```

`callbacks=None` is Optuna's own default, so the `observer is None` path is identical to today. The
callback is a strategy-local closure over the consumer's `observer`; the strategy therefore owns the
fault policy rather than handing the raw observer to Optuna.

### 2.4 Fault isolation — measured, not defensive-by-habit

§0.1 claim 5 executed the failure: an exception inside a callback propagates straight out of
`study.optimize`. Without the wrapper, a consumer's buggy MLflow sink aborts a multi-hour search and
loses the completed trials from the returned `Result`. The wrapper catches `Exception` (not
`BaseException` — `KeyboardInterrupt`/`SystemExit` must still stop the run), logs at `warning` with
`exc_info=True` via the library logger (`ruthless.strategies.optuna`, no root-logging config — the
house convention), and continues. This is not silent: the failure is on the record with the trial
number and traceback. The `# noqa: BLE001` is a sanctioned blind-except carrying its justification
inline — the same pattern the codebase already uses where a broad catch is correct (confirmed present
in-tree by the reviewer).

### 2.5 Why the port stays honest (Optuna-only, restated as the gold-standard choice)

The tempting "uniform" design — add `observer=` to the `SearchStrategy` port and have every strategy
accept it — is rejected because it manufactures a **silent no-op interface**: a consumer passing an
observer to `EvolveStrategy` would get nothing and no error, because evolve delegates its loop to
OpenEvolve (which has its own callback mechanism) and never produces ruthless `FrozenTrial`s. Random
search's every candidate is already fully present in `Result.history` (it is a fast batch, not a long
live run), so a live hook there is near-valueless and, wired trivially, still misleads. An interface
that lies about what it does is the opposite of gold standard. The port therefore stays unchanged;
consumers reach the observer by narrowing to `OptunaStrategy`, exactly as they already narrow to reach
`OptunaConfig`-specific features (`warm_start`, `store`). If a strategy ever gains a *faithful* live
loop, it adopts the **already-designed** neutral types (§1.4) additively — no retrofit.

---

## 3. The semantics contract (documented on `OptunaStrategy.run`)

The probe results (§0.1) become the observer's written contract, so a consumer does not discover them
by experiment:

1. **Live, per-completed-candidate, in order, sequential.** One call per completed trial, in trial
   order. The strategy calls `study.optimize` **without an `n_jobs` argument**, so it runs sequentially
   on Optuna's default (`n_jobs=1`) and ordering is deterministic; this is stated because a future
   `n_jobs>1` would void it. (The code does not set `n_jobs`; it relies on the default.)
2. **Resume shows only newly-run candidates, with study-global numbers.** On a resumed SQLite study the
   observer sees the trials run in *this* call, not the persisted ones — but their `event.number`
   values continue the store (e.g. 20…49 on a resume), they do not restart at 0 (§1.2). This is
   distinct from `Result.history`, which is reconstructed from `study.trials` and spans the whole
   store. The docstring names both surfaces so the difference is a documented choice, not a surprise.
3. **The warm-start baseline is observed** (as the first trial of a fresh study).
4. **A fatal scored metric is neither recorded nor observed.** It raises `FatalEvaluationError`, aborts
   the study, and propagates out of `run`; the observer does not fire for that trial. Consistent with
   the existing scored-metric-finiteness contract.
5. **The `CachedObjective` fast path fires identically.** The callback attaches to `study.optimize`,
   not to the objective path, so `evaluate_patch` trials are observed exactly like full-`evaluate`
   trials.
6. **Observer exceptions are isolated** (§2.4): logged and swallowed; the search completes and returns
   its `Result`.

---

## 4. Tests (TDD — each written failing first)

Location: extend `tests/strategies/optuna_/test_optuna_strategy.py` for the unit behaviours; the
resume behaviour joins the existing `tests/e2e/test_optuna_resume_gate.py` neighbourhood; the public
surface and sink-free checks join `tests/test_public_api.py`. Test function names are lowercase
(`per-file-ignores = ["S101"]` does **not** waive `N802`, so an uppercase name would fail lint).

1. `test_observer_fires_once_per_completed_trial` — N trials → N events, ascending `number`, each
   `state == "complete"`, params present. (§0.1 claim 1)
2. `test_observer_event_carries_all_metrics_not_only_scored` — an objective returning a scored + an
   auxiliary metric ⇒ both present in `event.metrics`. (§0.1 claim 1)
3. `test_observer_none_is_unchanged` — `observer=None` returns an equivalent `Result` and touches
   nothing (the current path).
4. `test_observer_resume_fires_only_new_continued_numbers` — SQLite store; run 2 then resume 2 ⇒ the
   second run's observer fires exactly twice, and its events carry the CONTINUED store-global numbers
   (`{2, 3}`), NOT a fresh zero-based `{0, 1}`. This is the test that pins the blocking-fix contract:
   the persisted trials do not re-fire, and `number` does not reset on resume. (§0.1 claim 2, §1.2)
5. `test_observer_fires_for_warm_start_trial` — `warm_start={…}` ⇒ first event carries the enqueued
   params. (§0.1 claim 3)
6. `test_fatal_metric_neither_records_nor_observes_and_propagates` — one trial returns a non-finite
   scored metric ⇒ `FatalEvaluationError` propagates from `run`, and the observer never saw that trial.
   (§0.1 claim 4)
7. `test_observer_exception_is_isolated` — an observer that always raises ⇒ the study still completes
   and returns a full `Result`; assert a `warning` was logged (via `caplog`). (§0.1 claim 5, §2.4)
8. `test_observer_fires_on_cached_objective_fast_path` — a `CachedObjective` ⇒ the observer fires per
   trial on the `evaluate_patch` path. (§3.5)
9. `test_optuna_strategy_still_conforms_to_search_strategy` — a module-level TYPED assignment
   `_s: SearchStrategy = OptunaStrategy(_cfg())` in the test file. pyright runs over `tests/`, so this
   statically verifies the added optional `observer` parameter keeps `OptunaStrategy` structurally a
   `SearchStrategy` — the real widening guard. The runtime `isinstance(..., SearchStrategy)` is
   name-only under `runtime_checkable` and cannot catch a signature regression, so it is kept only as a
   secondary check. A `run(obj, backend=…)` call with no observer must also type-check. (§2.1)
10. **Public surface** — add `Observer`, `ProgressEvent` to `_EXPECTED_PUBLIC` in
    `tests/test_public_api.py` (covers both the `__all__` and importability tests).
11. **Core stays sink-free** — a subprocess assertion (mirroring
    `test_top_level_import_does_not_require_optional_extras`): `import ruthless`, construct a
    `ProgressEvent`, reference `Observer`, and assert `optuna` is absent from `sys.modules`. The
    optuna-absence is the meaningful guard — it proves the new core types pull no strategy dependency
    into the lean install. (`mlflow` is never a ruthless dependency, so asserting its absence would be
    vacuous; the guardrail it stands for — no consumer sink in the core — is enforced by this
    optuna-absence check plus the `.importlinter` `core-isolation` contract, not by naming `mlflow`.)
12. `test_observer_isolated_when_it_raises_on_one_trial_only` — an observer that raises on exactly one
    trial (not on every call) ⇒ the study still completes all `n_trials`, the events for the other
    trials are delivered, and exactly one `warning` is logged. Guards that isolation is per-invocation
    (§2.4), not a global "observer disabled after its first error" off-switch.
13. `test_resume_with_no_remaining_trials_fires_zero_events` — resume a study that already holds
    `n_trials` completed candidates ⇒ `remaining == 0`, `study.optimize` is not called, the observer
    fires zero times, and `Result` is still reconstructed from the store. Boundary on the
    `if remaining:` guard — proves the observer is wired to the optimize call, not to the store
    reconstruction path.

Baseline note: the request cites a "158-test baseline"; that count is **stale** — the tree is at ~282
tests as of 0.4.0. The gate is "the full suite stays green plus the above", measured against whatever
`pytest` reports on this branch, not against 158.

---

## 5. Public API, versioning, release

- `ruthless/__init__.py`: import `Observer` from `ruthless.strategy` and `ProgressEvent` from
  `ruthless.result`; add both to `__all__`.
- `tests/test_public_api.py`: two entries in `_EXPECTED_PUBLIC` (§4.10).
- **Version:** bump the single line in `ruthless/_version.py` `0.4.0 → 0.5.0`, in the **same commit** as
  the work (release convention). Minor, because the public API gains two names and a parameter; nothing
  is removed.
- **CHANGELOG:** a `0.5.0` section describing the observer, and — following the practice set by the
  0.3.0/0.3.1/0.4.0 entries, each of which states its cache impact — an explicit sentence that this
  release **does not invalidate caches** (the fingerprint/digest path is untouched). This is the
  CHANGELOG *convention*, not a hard CLAUDE.md mandate: that rule requires the cache-impact statement
  when a release *touches* the fingerprint path, which this one does not.
- **CLAUDE.md:** update the "Ships at" line to `0.5.0` and add a one-line note to the Phase-2 conventions
  that `OptunaStrategy.run` accepts an optional neutral `Observer`.
- Flow: this feature branch → `/final-review` (regenerates the C4 diagram) → single commit **on your
  explicit approval** → PR → merge → `v0.5.0` tag → OIDC publish.

No ADR: this is a small additive port, not an architecture decision on the scale of ADR-002's cache
identity. The rationale lives in this spec and the docstrings. (Confirmable at review — say the word and
an ADR-003 gets written instead.)

---

## 6. Non-goals

- **No observer lifecycle hooks** (`on_run_start`/`on_run_end`/`on_error`). A single per-candidate event
  is the requested primitive; lifecycle is additive later (§1.1) and unrequested now — deferring it is a
  scope decision recorded here, not a silent drop.
- **No MLflow / progress-bar / logging sink in the library.** MLflow logging is a consumer-side
  `Observer` implementation, exactly as the batch harness stayed in silly-kicks. The core imports no
  sink; §4.11 enforces it.
- **No observer on `RandomSearchStrategy` or `EvolveStrategy`.** §2.5 — honesty over uniformity. The
  neutral types are ready if either grows a faithful live loop.
- **No `observer` in `RuthlessConfig` or the CLI.** An observer is a runtime *code* object, not
  declarative config; the CLI is trusted-config-only and loads no consumer code by design. Adding it
  there would reintroduce code-loading the CLI deliberately avoids.
- **No change to `Result`, `report.py`, or the digest/fingerprint path.** The observer is a side channel;
  the returned `Result` is byte-identical to today's for a given seed.

## 7. Rejected alternatives

- **`observer` on the `SearchStrategy` port** — silent no-op interface for evolve/random (§2.5).
- **Passing the raw `observer` to Optuna as a callback** — loses fault isolation (§0.1 claim 5); a buggy
  sink aborts the search.
- **A `score` field on `ProgressEvent`** — a second source of truth for `metrics[metric]`; declined.
- **Optuna's `TrialState` (or a new core enum) for `state`** — the enum leaks/over-specifies; a neutral
  `str` keeps `core-isolation` intact and stays forward-compatible (§1.2).
- **Replaying the whole store to the observer on resume** — conflates the live hook with `Result.history`
  and would re-fire persisted trials; the measured Optuna behaviour (§0.1 claim 2) is the correct one.
- **An auto-regenerable observer fixture / golden** — not applicable; there are no digest bytes here.

---

## Appendix A — the originating change request, verbatim

Recorded verbatim so request-faithfulness is independently verifiable (review SHOULD-FIX 2); §Origin and
§0's decisions are the acceptance of *this* text, not a substitute for it. Received from a lakehouse
session:

> ruthless-efficiency — add a neutral per-trial observer to OptunaStrategy (general capability).
> Motivation: consumers migrating raw-Optuna workflows onto OptunaStrategy lose Optuna's per-trial
> callbacks (e.g. progress, live metric sinks). Add an optional observer (a `Callable[[TrialEvent],
> None]`, or a small Observer Protocol) to `OptunaStrategy.run(..., observer=None)` — translate each
> Optuna FrozenTrial into a neutral TrialEvent (trial number, params, scored metric(s), state) and fire
> it; wire via `study.optimize(callbacks=[...])`. Charter guardrails: the event type + Protocol live in
> the core/ports; the Optuna translation lives in strategies/optuna_; the core imports no MLflow/logging
> sink (MLflow logging is a consumer-side Observer impl, not upstreamed — same reasoning that kept the
> batch harness in silly-kicks). Random/evolve strategies can grow the same hook later or leave it
> Optuna-only for now. Repo gotchas (from prior cross-repo cycles): tests per-file-ignores is `["S101"]`
> only → N802 fails uppercase test names; ruff E includes E402 (no imports mid-file in appended blocks);
> pyright is basic; package is at repo root (`ruthless/`), 3 importlinter contracts; keep the 158-test
> baseline green + add observer-fires-per-trial and core-stays-sink-free tests.

Where this spec **departs** from the request's letter, and why (all recorded above, gathered here for
the reviewer):

- **`TrialEvent` → `ProgressEvent`** (§1.2): the request's own guardrail says the type must be neutral
  in core; "Trial" is Optuna's noun. Name changed, intent honoured.
- **"trial number" is study-global, not per-run** (§1.2): the request says "trial number"; the spec
  pins that this is the store-global number and must not be read as a per-run ordinal (review BLOCKING).
- **"scored metric(s)"** is delivered as the full `metrics` dict (§1.2), a superset of the scored
  metric — the request asked for scored metric(s); the event carries those plus auxiliaries.
- **158-test baseline** is stale — the tree is at ~282 (§4). The request's other repo-gotchas
  (per-file-ignores, E402, pyright basic, package root, 3 importlinter contracts) are all confirmed
  accurate and are respected.
- **Fault policy, port scope, naming, state-repr, ceremony** were left open by the request and are
  locked in §0's decisions table per the human's confirmation.
