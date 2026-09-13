# Spec — generalize `EvolveStrategy` for arbitrary CODE evolution

**Date:** 2026-09-12
**Status:** rev 3 — APPROVED (spec review rounds 1 + 2; records:
`D:\Development\_reviews\2026-09-12-ruthless-general-code-evolution-spec.md` and `…-spec-r2.md`). Rev 2
flipped the security posture from an **opt-in belt** to **secure-by-default with a general opt-out**
(GCE-SPEC-01, Karsten's decision — §2.3/§2.4/§4/§5 reworked) and fixed two factual/code errors (GCE-SPEC-02
the `fingerprint` snippet, GCE-SPEC-03 the openevolve version) plus three CONSIDERs (stale comment,
assign-after-validate, lakehouse-shaped-no-profile test). Rev 3 closes the round-2 cosmetic nit (GCE-SPEC-08:
§0 table rows 42/44 attribution). **Unchanged and confirmed-correct by both rounds:** Approach B, the §7
seed-cache analysis, and the §0.1 verification discipline. Implementation plan:
`docs/superpowers/plans/2026-09-12-general-code-evolution.md`.
**Baseline:** `4b03c80` (HEAD, `main`), version `0.5.0`, clean tree. Evolve suite green at baseline: 53
passed (`tests/strategies/evolve`, `tests/e2e/test_evolve_orchestration_gate.py`,
`tests/test_evolve_config.py`).
**Origin:** a change request from a silly-kicks session dogfooding `ruthless[evolve]` (v0.5.0) to evolve a
single scoring **function** — `_score(event, candidate, lookups, *, params) -> float`. (This repo pins
`openevolve>=0.2.0`, `pyproject.toml:22`, resolved to **0.2.27** in the working env; the handoff's "0.3.2"
is the silly-kicks environment's number, not ruthless's pin — see §8 and the note after Appendix A.) `EvolveStrategy` could not run it without shoehorning, so that session fell back to
driving OpenEvolve directly. The request asks ruthless to add a first-class general-code-evolution mode
so consumers don't bypass it. The originating handoff is quoted **verbatim in Appendix A** so
request-faithfulness is independently verifiable rather than resting on this paraphrase.
**User directives (this session):** breaking changes and refactoring are acceptable (the lakehouse is the
only known consumer, adjustable as needed); **the one hard constraint is that the lakehouse must not
lose existing functionality.** Design bar: best practice, long-term, gold standard.

---

## 0. Summary of decisions

| Item | Verdict | Note |
|---|---|---|
| Add a general code-evolution mode to `EvolveStrategy` | **ACCEPT** | The engine it wraps is already general; the coupling is entirely in ruthless's evaluator/objective. §1. |
| **Approach: clean reframe vs. additive flag-gated branch** | **REFRAME (Approach B)** | `code_evolution` gets ONE coherent meaning; the hardcoded `custom_embed`/`custom_layers` heuristic leaves core. Authorized by the "refactoring fine" directive. §1, §2. |
| Meaning of `code_evolution=True` | **"this run evolves CODE"** | Always attach evolved source (`program_path` always real); `config = {…}` becomes OPTIONAL. §1.1, §2.2. |
| Meaning of `code_evolution=False` | **pure HPO, unchanged** | No source attached; entrypoint gets `program_path=None`. §1.1. |
| Source-attach trigger | **the `code_evolution` flag, NOT function names** | Delete `has_custom_embed`/`has_custom_layers` detection from `evaluator.py`. §2.1, §2.3. |
| The AST sandbox (`sandbox.py`) | **UNTOUCHED; SECURE-BY-DEFAULT gate** | `validation_profile` present → validate (lakehouse: identical to today); absent → the run is **rejected** unless an explicit opt-out is set. §4. |
| `validation_profile` required when `code_evolution` | **REPLACE the validator, don't delete it** | New rule: `code_evolution=True` requires `validation_profile` **OR** an explicit `allow_unvalidated_code=True`. Fail-closed for everyone; no lakehouse carve-out. §2.4, §4. |
| Security posture of code mode without a profile | **SECURE-BY-DEFAULT + general opt-out** | Unsandboxed execution is possible only when the operator consciously sets `allow_unvalidated_code=True` per-config; silent omission is rejected. The ADR (belt-not-boundary) is updated to state the default-closed contract. §4, ADR-001. |
| `config = {…}` optionality | **ALWAYS optional (default `{}`)** | Absent config → `{}`, in every mode; a present-but-malformed `config` still maps to the load sentinel. HPO consumers that want to reject param-less candidates use the existing `search_space_validator` hook. §2.2, §6. |
| Entrypoint contract | **UNCHANGED signature** | `fn(*, candidate_config, device, epochs, seed, program_path)` already exists; code mode simply always supplies a real `program_path`. §3. |
| `strategy.py` functional change | **`_eval_fingerprint` fold + one wiring line** | Dispatch path unchanged (`_ConfigRemoteObjective.evaluate` already passes `program_path` path-or-None); `_build_evaluator` gains `allow_unvalidated_code=` wiring; `_eval_fingerprint` folds in `code_evolution` (§7). Docstrings updated. §2.5. |
| Seed-cache identity vs. the behavior change | **DECIDED: fold `code_evolution` into `_eval_fingerprint`** | `_eval_fingerprint` covered only `EvalConfig`, so a config-only seed's cache key was unchanged though its evaluated metrics can change in code mode → latent resume-staleness. Now include the flag so the key self-heals (old cache → miss → recompute, the safe direction). Golden table **unaffected** (it pins the EvalConfig base, not the composite); a deliberate one-time evolve seed-cache invalidation, stated in the CHANGELOG. §7. |
| Target release | **`0.6.0`** (minor; `0.x`) | Justified by the reframe + the seed-cache-key invalidation (§7), not by the validator (which is **superseded, non-breaking** — §2.4). New capability + config surface. Not fingerprint/digest-invalidating (primitive byte-stable; §7). §8. |
| Ceremony | **spec → plan → TDD → `/final-review` → commit on explicit approval** | New consumer-facing contract (Hyrum's Law); pin the reframed semantics before code. |

### 0.1 What the change relies on — verified, not assumed

Every claim below was verified by reading the code at baseline `4b03c80` and confirmed by the 53 green
evolve tests, not reasoned about.

1. **`_extract_config` raises on a missing `config = {…}` dict.** `evaluator.py:66`
   (`raise ValueError("No 'config = {{...}}' assignment found …")`), called unconditionally by
   `_load_program` (`:72`) at the top of `evaluate` (`:106`), caught → worst-score sentinel (`:107–108`).
   A function-only program therefore scores `combined_score=0` today.
2. **Source-attach is gated on hardcoded function names, independent of `code_evolution`.** `evaluator.py:121`
   (`if program.has_custom_embed or program.has_custom_layers:`), where those booleans come from a literal
   name check (`:73`, `:76–77`). Pinned by `test_evaluate_dispatches_and_computes_combined_score`, which
   asserts `backend.candidate.program is None` for a config-only program **even under `code_evolution=True`**
   (`test_evolve_evaluator.py:72`).
3. **The lakehouse must already run `code_evolution=True`.** In `code_evolution=False`, a program containing
   `custom_embed`/`custom_layers` is rejected by the sandbox (`sandbox.py:587–588`, Step 4). A production
   run that evolves those functions therefore cannot be in HPO mode. ⇒ the reframe (source-attach on
   `code_evolution=True`) does not disturb the lakehouse's source-passing.
4. **The AST sandbox only validates functions literally named `custom_embed`/`custom_layers`.**
   `sandbox.py:579–584`: any other function name returns `(True, "config-only program")` **without walking
   the body**. So "run the ValidationProfile on it" for an arbitrarily-named function is a silent no-op — and
   a lakehouse-shaped `ValidationProfile` (`patch_method`, `patch_signature`, `layers_args`,
   `known_model_attrs`) does not describe a general scoring function. This is why the handoff's "always run
   the profile" cannot be the contract for general code — instead validation is *either* a profile *or* the
   explicit `allow_unvalidated_code` opt-out, never a silent skip (§4).
5. **The entrypoint already receives `program_path` path-or-None uniformly.**
   `strategy.py:78–83` (`_ConfigRemoteObjective.evaluate`) writes `candidate.program` to a temp `.py` via
   `program_to_path` (`_io.py`) and calls `fn(**kw, program_path=program_path)`. The contract in the
   acceptance case — `train_and_evaluate(*, candidate_config, device, epochs, seed, program_path)` — is
   exactly today's call shape; only *whether `program_path` is `None`* changes.

---

## 1. The reframe

### 1.1 One meaning for `code_evolution`

OpenEvolve is already general: `run_evolution(initial_program, evaluator, config)` evolves any code
between `# EVOLVE-BLOCK-START/END` markers and calls an arbitrary `evaluate(program_path) -> metrics`. All
lakehouse-specific coupling lives in ruthless's `EvolveEvaluator`/`_ConfigRemoteObjective`, not in the
engine.

We collapse two overlapping notions ("is this HPO or code?" and "does this program define
`custom_embed`/`custom_layers`?") into one switch:

- **`code_evolution=True` → the run evolves CODE.** The evolved source is **always** attached to the
  `Candidate` (`program_path` is always a real file); the `config = {…}` dict is **optional** (a code
  program need not carry HPO params, though it may).
- **`code_evolution=False` → pure HPO.** No source is attached (`program_path=None`), exactly as today.

The `custom_embed`/`custom_layers` name detection becomes a lakehouse detail, expressed the same way any
other consumer expresses "validate my evolved code": by supplying a `validation_profile` (§4). It no
longer gates source-passing, and it no longer lives in core.

---

## 2. Concrete changes

### 2.1 `ruthless/strategies/evolve_/evaluator.py` — `Program` + `_load_program`

Drop the hardcoded name detection.

```python
@dataclass(frozen=True)
class Program:
    config: dict[str, Any]
    source: str
    # has_custom_embed / has_custom_layers REMOVED

def _load_program(program_path: str) -> Program:
    source = Path(program_path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=program_path)
    return Program(config=_extract_config(tree, source, program_path), source=source)
```

### 2.2 `_extract_config` — absence returns `{}`, malformed still fails

```python
def _extract_config(tree, source, filename) -> dict[str, Any]:
    for node in ast.walk(tree):
        ... # find `config = <literal>`
        raw = ast.literal_eval(value_source)
        if not isinstance(raw, dict):
            raise ValueError(f"config must be a dict, got {type(raw).__name__} in {filename}")
        return raw
    return {}   # was: raise ValueError("No 'config = {...}' assignment found …")
```

Absence of `config` is now benign (empty param set). A `config` that IS present but non-literal or
non-dict still raises → mapped to the existing load sentinel (`evaluate` `:107–108`) — a malformed literal
is a real defect, not an empty param set.

### 2.3 `EvolveEvaluator` — attach + validate keyed on the flag, fail-closed by default

`EvolveEvaluator.__init__` gains `allow_unvalidated_code: bool = False` and enforces secure-by-default as a
**defense-in-depth** guard (the primary gate is the config validator, §2.4; this makes the object honest for
any direct/programmatic construction too):

```python
def __init__(self, *, backend, objective, fitness_config, code_evolution=False,
             validation_profile=None, allow_unvalidated_code=False, ...):
    if code_evolution and validation_profile is None and not allow_unvalidated_code:
        raise FatalEvaluationError(
            "code_evolution requires a validation_profile, or an explicit allow_unvalidated_code=True "
            "to run LLM-generated code unsandboxed"
        )
    ...
```

`evaluate` replaces the name-gated block (`:120–130`) with — note **source is attached only after
validation passes** (GCE-SPEC-06: baseline set `program_source` post-check at `:130`; do not "tidy" it into
an attach-before-validate):

```python
program_source: str | None = None
if self._code_evolution:
    if self._validation_profile is not None:
        valid, reason = validate_program(program.source, self._validation_profile, code_evolution=True)
        if not valid:
            _log.warning("validation_rejected", extra={"program": program_path, "reason": reason})
            return self._sentinel(f"validation_rejected: {reason}", kind="objective")
    # profile is None here ONLY when allow_unvalidated_code=True (enforced at __init__) — conscious opt-out
    program_source = program.source

candidate = Candidate(id=Path(program_path).stem, params=config, program=program_source)
```

- Code mode attaches source **after** a passing validation (profile present) or after the conscious opt-out
  (profile absent + `allow_unvalidated_code=True`). No-profile-no-opt-out never reaches here — it fails at
  construction (`__init__`) and, upstream, at config load (§2.4).
- HPO mode attaches no source and runs no validation (nothing to validate; entrypoint gets
  `program_path=None`).
- The pre-validate and search-space hooks (`:111–118`) are unchanged and run in both modes.

### 2.4 `ruthless/config/strategies.py` — replace the validator with an opt-out-gated one (the primary gate)

This is the secure-by-default gate, and it is **non-breaking for the lakehouse** (profile present → passes
unchanged). Add the opt-out field and **replace** (do not delete) the validator:

```python
class EvolveConfig(BaseModel):
    ...
    validation_profile: str | None = None  # "module:ATTR" -> ValidationProfile; required in code mode unless allow_unvalidated_code
    allow_unvalidated_code: bool = False    # code_evolution WITHOUT a profile: run LLM-generated code UNSANDBOXED (conscious opt-out)

    @model_validator(mode="after")
    def _validation_required_for_code_evolution(self) -> EvolveConfig:
        if self.evolution.code_evolution and self.validation_profile is None and not self.allow_unvalidated_code:
            raise ValueError(
                "code_evolution=True requires a validation_profile, or an explicit allow_unvalidated_code=True "
                "(runs LLM-generated code unsandboxed)"
            )
        return self
```

- The old `_profile_required_for_code_evolution` (`strategies.py:52–56`) is superseded, not removed
  wholesale: the fail-closed guarantee it provided is **preserved and generalized** — a `code_evolution=True`
  config with no profile is still rejected, now unless the operator consciously opts out. No config that was
  valid at 0.5.0 becomes invalid (no-profile-in-code-mode was already impossible), so it is non-breaking.
- The `validation_profile` field comment loses "(required if code_evolution)" and states the new contract
  (GCE-SPEC-05 CONSIDER; also listed in §8's doc-update set).
- `allow_unvalidated_code` naming: chosen to read as a conscious risk (default `False` = secure); exact
  spelling finalizable in the plan/review.

### 2.5 `sandbox.py` untouched; `strategy.py` — only `_eval_fingerprint` changes

- **`sandbox.py`:** validation logic unchanged (the lakehouse's belt still validates
  `custom_embed`/`custom_layers` identically). The reframe makes `validate_program`'s `code_evolution=False`
  branch unreachable — it is only ever called for code-evolution candidates now — so the now-vestigial
  `code_evolution` parameter and that dead branch are **removed** (folded into this cycle per Karsten's
  "nothing deferred"; the corresponding `test_code_evolution_disabled_rejects_custom_embed` is dropped).
- **`strategy.py` — dispatch path unchanged, one wiring line added:** `_ConfigRemoteObjective.evaluate`
  already yields `program_path` path-or-None (§0.1 claim 5). `_build_evaluator` (`:106–115`) already passes
  `code_evolution` + resolved profile and now **also passes `allow_unvalidated_code=cfg.allow_unvalidated_code`**
  so the evaluator's fail-closed guard (§2.3) matches the config gate (§2.4). Docstrings describing the old
  name-gated behavior are updated.
- **`strategy.py` — the one functional change is `_eval_fingerprint`** (`:146–153`): fold
  `cfg.evolution.code_evolution` into the seed-cache identity per §7 (base EvalConfig digest composed with
  the flag via the public `fingerprint`). `_SEED_CACHE_EXCLUDE` is unchanged.

---

## 3. The entrypoint contract in code mode

Unchanged signature; `program_path` is simply always a real file in code mode:

```
train_and_evaluate(*, candidate_config: dict, device: str, epochs: int, seed: int, program_path: str) -> dict
```

The consumer's entrypoint imports the evolved symbol from `program_path`, injects it into the target
module, runs its own fitness, and returns a metrics dict. `EvolveEvaluator` computes `combined_score` from
`FitnessConfig` exactly as today (`:143–148`, `:156–160`). `candidate_config` is `{}` when the program
carries no `config` dict.

---

## 4. Validation: secure-by-default with a general opt-out (security posture)

**Decision (Karsten, 2026-09-12 — supersedes rev 1's opt-in belt):** a `code_evolution=True` run is
**fail-closed for all consumers**. It must be covered by *either* a `validation_profile` (AST-screened) *or*
an explicit `allow_unvalidated_code=True` acknowledgment. A no-profile-no-opt-out config is **rejected**, not
dispatched — enforced generally, with **no consumer-specific carve-out** and **no silent omission**.

| Config in code mode | Behavior |
|---|---|
| `validation_profile` present | `validate_program` runs (lakehouse: byte-identical validation of `custom_embed`/`custom_layers`). |
| No profile, `allow_unvalidated_code=True` | Source attached + run **unsandboxed** — a conscious, per-config operator opt-out. |
| No profile, no opt-out | **Rejected** at config load (§2.4) and at evaluator construction (§2.3). |

Enforced at two layers (defense-in-depth): the `EvolveConfig` validator (§2.4, primary, fail-fast at
`model_validate`) and the `EvolveEvaluator.__init__` guard (§2.3, catches direct/programmatic construction).

Why a general opt-out rather than mandatory validation everywhere:

- The sandbox is, by its own ADR (`ADR-001`), a *defense-in-depth belt, not a sandbox boundary*.
- It is structurally inapplicable to general code: it validates only two hardcoded names (§0.1 claim 4),
  and its restrictive allowlist (no imports, no f-strings, whitelisted namespaces only) would fight a
  general scoring function such as silly-kicks' `_score` rather than protect it.
- Forcing a mandatory lakehouse-shaped `ValidationProfile` on every consumer is meaningless; forcing
  *silent* unsandboxed execution is unsafe. The opt-out makes running unvalidated code a **visible,
  reviewable, deliberate** config line — the same fail-closed philosophy as `fingerprint`'s
  "unnecessary miss over stale hit."

**ADR-001 gets an addendum** stating that as of 0.6.0 code evolution is default-closed: no profile ⇒
rejected unless `allow_unvalidated_code=True`, and that setting the opt-out runs LLM-generated code
unsandboxed by conscious operator choice. Generalizing the AST allowlist to arbitrary functions was
considered and **declined** for this cycle (poor fit, large scope) — recorded in §9, not silently dropped.

---

## 5. Lakehouse functionality preservation (the hard constraint)

The reframe removes **two** guards that today force a `code_evolution=True` run to be AST-screened — the
config validator (`strategies.py:52–56`) and the evaluator's Level-2-without-profile rejection
(`evaluator.py:122–123`). Rev 1 replaced them with an *opt-in* belt, which silently relaxed that guarantee.
Rev 2 does **not**: the fail-closed guarantee is **preserved and generalized** by the secure-by-default gate
of §4 — with a profile present, behavior is byte-identical; with a profile absent, the run is *rejected*
unless the operator consciously opts out. Nothing that the lakehouse relies on is dropped.

| Lakehouse capability today | Under the reframe (rev 2) |
|---|---|
| Evolve `custom_embed`/`custom_layers` | Runs under `code_evolution=True` (already required — §0.1 claim 3). |
| AST validation of those functions | Identical: supply the same `validation_profile`; `validate_program` runs unchanged. |
| **A code run without a profile is refused, not silently unsafe** | **Preserved generally** — refused at config load *and* evaluator construction unless `allow_unvalidated_code=True` is consciously set. Not a lakehouse-specific rule; the same gate protects every consumer (§4). |
| Reject malicious candidates before dispatch | Identical (`test_sandbox_rejects_before_dispatch`, e2e `test_orchestration_gate` stay green). |
| Combined-score / fitness | Unchanged. |

**The one behavioral delta:** a *config-only* lakehouse candidate (no custom functions) now also receives a
real `program_path` (the seed source), where it previously got `None`. This is a capability **gain**, not a
loss. The lakehouse entrypoint must key on "does this source define `custom_embed`?" rather than
"is `program_path` non-None?"; if it currently assumes the latter, it needs a small entrypoint tweak
(refactoring, explicitly authorized). Whether the lakehouse's seeds are already Level-2 (custom functions
present, so *zero* delta) is a lakehouse-side fact to confirm during that repo's migration — it does not
block this change and is called out so the lakehouse session verifies it.

Non-breaking check: the lakehouse config sets `code_evolution=True` + `validation_profile` → passes the new
validator unchanged; no lakehouse config becomes invalid. This preservation is enforced as a regression
gate: **all existing evolve tests stay green**, and the existing `custom_embed` tests are treated as the
lakehouse-functionality gate.

---

## 6. `config` optionality — why always-optional

Rather than "optional in code mode, required in HPO mode" (a second branch keyed on the flag), `config` is
**always** optional (absent → `{}`). Rationale:

- It removes a mode-conditional branch from the hot path.
- The single legitimate use of "reject a param-less candidate" is an HPO concern the consumer already owns
  via the injected `search_space_validator` hook (`:114–118`) — no need to hardcode it.
- A *malformed present* `config` still fails loudly (§2.2), so the change only affects genuine *absence*.

Behavioral note: a pre-existing HPO run whose program legitimately lacked a `config` dict previously scored
the worst-score sentinel and now dispatches with `candidate_config={}`. No known consumer relies on the old
"absent config → sentinel" behavior (the lakehouse always carries a config); flagged here for completeness.

---

## 7. Test plan (TDD — red first)

**New — feature (drive the general mode):**

1. `test_code_mode_config_optional` — a code-mode program with **no** `config` dict → `candidate.params ==
   {}`, `candidate.program is not None`, dispatched (real `combined_score`, not the sentinel). (Uses a
   profile *or* `allow_unvalidated_code=True` so it isn't rejected by the §4 gate.)
2. **Acceptance integration test (the silly-kicks shape), through ruthless — not OpenEvolve-direct:** a seed
   whose `EVOLVE-BLOCK` is a function body, no `config`, arbitrary function name; a real entrypoint
   `train_and_evaluate(*, candidate_config, device, epochs, seed, program_path)` that imports the evolved
   function from `program_path`, runs it, and returns `{"combined_score": …, <components>}`. Trivial fitness
   ("evolve `f(x) -> x*2` to maximise a scalar") is enough to prove the plumbing:
   `_load_program` (config optional) → `Candidate(program=source)` → `InProcessBackend` → entrypoint loads
   from `program_path` → metrics → `combined_score`. (silly-kicks-shaped → sets `allow_unvalidated_code=True`.)

**New — secure-by-default, both directions pinned (§4):**

3. Config gate — `test_code_evolution_without_profile_or_optout_is_rejected`: `EvolveConfig(kind="evolve",
   … evolution={code_evolution: True})` with no `validation_profile` and no `allow_unvalidated_code` →
   `ValidationError` (the replacement validator).
4. Config gate — `test_code_evolution_optout_allows_no_profile`: same config with
   `allow_unvalidated_code=True` → validates cleanly.
5. Evaluator guard — `test_evaluator_rejects_code_evolution_without_profile_or_optout`:
   `EvolveEvaluator(code_evolution=True, validation_profile=None, allow_unvalidated_code=False)` raises
   `FatalEvaluationError` at construction (defense-in-depth).
6. Evaluator opt-out — `test_code_mode_with_optout_skips_validation`: `code_evolution=True`, no profile,
   `allow_unvalidated_code=True`, arbitrary function name → source attached, no `validation_rejected`,
   dispatched.
7. **Opt-out bypasses regardless of function names (GCE-SPEC-07)** —
   `test_optout_dispatches_lakehouse_shaped_source_unvalidated`: a program defining `custom_embed`, no
   profile, `allow_unvalidated_code=True` → source attached, **not** validated, dispatched. Pins consciously
   that the opt-out runs even lakehouse-shaped code unsandboxed (the exact case §5 is about), rather than
   leaving it implied.

**Changed (the reframe):**

8. `test_evaluate_dispatches_and_computes_combined_score` splits into two: HPO mode
   (`code_evolution=False`) → `program is None`; code mode config-only (`code_evolution=True`, with a profile
   or opt-out) → `program is not None`.
9. `test_code_evolution_requires_validation_profile` (`test_evolve_config.py:66`) is **updated, not
   inverted**: still a rejection test for no-profile-no-opt-out (per #3), and the assertion message tracks
   the new "profile OR allow_unvalidated_code" contract.

**Preserved (lakehouse-functionality regression gate — must stay green):**
`test_level2_passes_source_as_candidate_program`, `test_sandbox_rejects_before_dispatch`, the e2e
`test_orchestration_gate`, and all `tests/strategies/evolve/test_sandbox.py`. (These all supply a profile, so
they pass the §4 gate unchanged.)

**Seed-cache identity — DECIDED (fold `code_evolution` in).** `_eval_fingerprint` (`strategy.py:146–153`)
hashes only `EvalConfig`, so a config-only seed keeps the same cache key though its evaluated metrics can
now differ in code mode (it now receives `program_path`). A `resume=True` run spanning the 0.5.0→0.6.0
upgrade could therefore read a stale seed metric. **Fix:** fold `cfg.evolution.code_evolution` into the
seed-cache identity so the key self-heals (old cache → miss → recompute, the safe fail-closed direction).

Implementation and its golden-table interaction (verified against `tests/test_fingerprint_golden.py:137`):

- `_eval_fingerprint` keeps the existing `fingerprint_model(cfg.evaluation, exclude=_SEED_CACHE_EXCLUDE)`
  as its **base digest**, then composes it with the flag via the public primitive. `fingerprint` is
  **`Mapping`-only** (`_fingerprint.py:77`, body does `dict(payload)` at `:100`), so the payload must be a
  mapping — e.g. `fingerprint({"eval": base, "code_evolution": cfg.evolution.code_evolution})`. A tuple such
  as `fingerprint((base, flag))` raises `ValueError` (`dict()` tries to unpack the 16-char base string as a
  key/value pair) — GCE-SPEC-02. `_SEED_CACHE_EXCLUDE` is **unchanged** (`frozenset({"timeout_seconds"})`),
  so `test_seed_cache_exclude_matches_the_golden_table` stays green.
- **The golden table is unaffected.** Its `evolve-seed-cache` case pins
  `fingerprint_model(EvalConfig(), exclude={"timeout_seconds"})` — the base digest computed *directly*, not
  via `_eval_fingerprint`. Folding the flag changes only `_eval_fingerprint`'s composite output, not the
  pinned base. The `fingerprint`/`fingerprint_model` **primitive stays byte-stable** (no `_tag`/payload
  change); this is *not* a digest-bytes change.
- What *does* change is the persisted evolve **seed-cache key** (`_eval_fingerprint`'s output), a deliberate
  one-time invalidation of evolve seed caches at 0.6.0 — the CHANGELOG states it (§8).
- `test_eval_fingerprint_tracks_epochs_and_seed_but_not_timeout` gains a sensitivity assertion:
  `_eval_fingerprint` differs when `code_evolution` differs.

---

## 8. Version, CHANGELOG, docs

- **Version → `0.6.0`.** One-line bump in `ruthless/_version.py` (the single source). Minor under `0.x`,
  justified by the reframe + the one-time evolve seed-cache-key invalidation (§7) and the new config surface
  — **not** by the validator, which is superseded non-breakingly (§2.4). **The `fingerprint`/
  `fingerprint_model` primitive is byte-stable** (no `_fingerprint`/`_tag` payload change; golden table
  untouched). Distinctly, the evolve **seed-cache key** (`_eval_fingerprint`'s composite output) changes
  because it now folds in `code_evolution` (§7) — a deliberate, evolve-local one-time cache invalidation, not
  a primitive-digest change.
- **CHANGELOG.md** — new `## [0.6.0]` section:
  - *Added:* general code-evolution mode (`code_evolution=True` evolves arbitrary code); new
    `EvolveConfig.allow_unvalidated_code` opt-out.
  - *Changed/Breaking:* `code_evolution` reframed (source-attach keyed on the flag, not on function names);
    `config = {…}` optional; the profile-required rule is **generalized** — code mode requires a
    `validation_profile` **or** `allow_unvalidated_code=True` (secure-by-default, no consumer carve-out);
    **`_eval_fingerprint` now includes `code_evolution` → resumed evolve seed caches from ≤0.5.0 are
    invalidated once and recomputed**.
  - *Security:* code evolution is now **default-closed** — a run with no profile is rejected unless the
    operator sets `allow_unvalidated_code=True`, which runs LLM-generated code unsandboxed by conscious
    choice.
  - The primitive-digest wording stays clear that the `fingerprint`/`fingerprint_model` golden table did not
    move (§7).
- **CLAUDE.md** — bump the "Ships at `0.5.0`" line and update the `[evolve]`/`EvolveStrategy` description to
  state the general code mode and the secure-by-default gate (profile **or** `allow_unvalidated_code`).
- **`ruthless/config/strategies.py:49`** — update the stale `validation_profile` field comment
  ("(required if code_evolution)") to the new contract (GCE-SPEC-05).
- **ADR-001** — addendum per §4 (default-closed; opt-out runs code unsandboxed by conscious choice).

---

## 9. Out of scope (deferrals approved by Karsten, review round 1 disposition)

Per the review record's Disposition ("scope is not a concern, we're going for gold standard"), the
deferrals below are **approved**, not merely surfaced (GCE-SPEC-04 resolved).

- **Generalize the AST allowlist to arbitrary function names.** Considered; declined this cycle (§4). Not a
  silent deferral — recorded for a future decision if a consumer wants sandboxed general code.
- ~~Remove `sandbox.py`'s now-unreachable `code_evolution=False` branch / the `code_evolution` param.~~
  **DONE this cycle** (Karsten: "nothing deferred") — the vestigial parameter and dead branch are removed and
  the caller updated; `validate_program` is internal (not in `ruthless.__all__`), so no public-API break.
- **`_ConfigRemoteObjective`'s hardcoded `device="cpu"`** in the in-process seed path (`strategy.py:81`) —
  pre-existing, unrelated to this change; left as-is.
- **Lakehouse migration** (adopting `code_evolution=True` end-to-end, confirming its seeds/entrypoint under
  the new contract) runs in the lakehouse repo, not here.

---

## Appendix A — originating handoff (verbatim)

> A silly-kicks session is using AlphaEvolve in a way that it not currently supported. It has a suggestion
> for a change that allows us to support more, not just the lakehouse's existing use case. Investigate and
> consider, breaking changes is not an issue (the lakehouse is the only known consumer, we will adjust as
> needed), we are looking for best practice, gold standard:
>
> [HANDOFF — ruthless-efficiency: generalize EvolveStrategy for arbitrary CODE evolution
> (currently it only supports the lakehouse "config dict + custom_embed/custom_layers" shape)
>
> CONTEXT
> We're dogfooding ruthless[evolve] (v0.5.0, wrapping openevolve 0.3.2) in the silly-kicks repo to
> evolve a single scoring FUNCTION — `_score(event, candidate, lookups, *, params) -> float` — of an
> event↔tracking sync algorithm. EvolveStrategy could not run it without shoehorning, so we fell back
> to driving openevolve DIRECTLY. This handoff is to add a first-class general-code-evolution mode to
> ruthless so consumers don't have to bypass it.
>
> THE LIMITATION (precise, with code locations in the ruthless package)
> 1. ruthless/strategies/evolve_/evaluator.py :: _extract_config() REQUIRES a top-level
>    `config = {...}` literal dict in EVERY evolved program and raises
>    ValueError("No 'config = {...}' assignment found") otherwise. A program that evolves a function
>    (no HPO params) has no such dict → every candidate scores the worst-score sentinel (combined=0).
> 2. Same file, _load_program() computes has_custom_embed = "custom_embed" in func_names and
>    has_custom_layers = "custom_layers" in func_names — HARDCODED lakehouse function names.
> 3. EvolveEvaluator.evaluate(): program_source stays None UNLESS has_custom_embed or has_custom_layers;
>    only then is the source ValidationProfile-checked and attached to Candidate(program=source).
> 4. ruthless/strategies/evolve_/strategy.py :: _ConfigRemoteObjective.evaluate() then calls the
>    entrypoint as fn(candidate_config=dict(candidate.params), device=..., epochs=..., seed=...,
>    program_path=<temp .py of candidate.program OR None>). So the entrypoint receives the EVOLVED
>    SOURCE only when the program defines custom_embed/custom_layers; otherwise program_path is None
>    and the consumer literally cannot load the mutated code.
> ⇒ Net: evolving an arbitrarily-named function is impossible — (1) raises on the missing config dict,
>   and (3)/(4) never hand the evolved source to the entrypoint.
>
> THE ENGINE IT WRAPS IS ALREADY GENERAL
> openevolve.run_evolution(initial_program, evaluator, config) evolves any code between
> `# EVOLVE-BLOCK-START/END` and calls an arbitrary evaluator `evaluate(program_path) -> {"combined_score": float, ...}`.
> The coupling is entirely in ruthless's EvolveEvaluator/objective, not in openevolve.
>
> THE ASK — add a general "code" mode, keyed on the EXISTING EvolutionConfig.code_evolution flag
> (config/common.py), NOT on function names:
>   When evolution.code_evolution is True:
>    (a) make the `config = {...}` dict OPTIONAL — default to {} when absent (a code program needn't
>        carry params); keep parsing it when present (some code programs also expose scalar knobs).
>    (b) ALWAYS attach the evolved program SOURCE to the Candidate (candidate.program = source),
>        regardless of function names, and run the ValidationProfile on it (already required when
>        code_evolution is True per EvolveConfig's model_validator).
>    (c) the entrypoint contract for code mode: program_path is ALWAYS the evolved source file; the
>        consumer's entrypoint loads the mutated symbol from it, runs its own fitness, returns a
>        metrics dict (combined_score computed by EvolveEvaluator from FitnessConfig, as today).
>   The custom_embed/custom_layers detection becomes a lakehouse-specific concern (either behind
>   code_evolution=False, or an injected predicate) — it MUST NOT gate source-passing in general.
>
> BACKWARD COMPATIBILITY (hard)
> The existing lakehouse path (config = {...} + custom_embed/custom_layers, code_evolution as used
> today) must keep working byte-identically — it's in production. This is an ADDITIVE mode, not a
> rewrite. Gate: all existing evolve_ tests stay green + a new general-code-evolution test.
>
> ACCEPTANCE — the concrete use case that must run THROUGH ruthless (not openevolve-direct)
> A seed file whose evolvable EVOLVE-BLOCK is a function body, no `config` dict, an arbitrary function
> name; an entrypoint `train_and_evaluate(*, candidate_config, device, epochs, seed, program_path)`
> that imports the evolved function from program_path, injects it into the target module, runs a
> fitness, and returns {"combined_score": ..., <components>}. Add a focused integration test of exactly
> this shape (a trivial "evolve f(x)->x*2 to maximise a scalar" is enough to prove the plumbing).
>
> POINTERS
> - ruthless/strategies/evolve_/evaluator.py   (_extract_config, _load_program, EvolveEvaluator.evaluate)
> - ruthless/strategies/evolve_/strategy.py    (_ConfigRemoteObjective.evaluate, _build_evaluator, _remote_objective_from_config)
> - ruthless/config/common.py                  (EvolutionConfig.code_evolution, FitnessConfig, LLMConfig)
> - ruthless/config/strategies.py              (EvolveConfig; model_validator requiring validation_profile when code_evolution)
> - openevolve.api.run_evolution / openevolve.config (the general engine + LLMModelConfig: name, api_base, api_key, weight, max_budget_usd)
> Note: LLM OpenRouter routing already works — _translate_to_openevolve_config maps per-model
> {name, weight, api_base, api_key_env}; no change needed there.
>
> CONSTRAINTS / WORKING RULES (Karsten's standing rules — honor them)
> - TDD: failing test first, watch it fail, minimal code to green.
> - Feature branch off the ruthless default branch; NO worktrees.
> - ONE coherent commit, fully tested; NO micro-commits; commit/push ONLY on Karsten's explicit
>   per-commit approval (stop at the diff and wait).
> - Nothing deferred/cut without Karsten's approval; surface scope questions, don't pre-decide.
> - Bump ruthless-efficiency's version per its convention; the silly-kicks cycle will then pin the new
>   floor.]

**Notes on the handoff, where this spec departs from it:**

- **"byte-identical / additive" constraint** (handoff line 498–501): the handoff's own, adopted because it
  assumed it could not touch the lakehouse. The user lifted it for this session (refactoring fine; only
  lakehouse *functionality* is sacred), which is what makes the cleaner Approach-B reframe — rather than the
  handoff's additive branch — the chosen design. The acceptance test and the "all existing evolve tests stay
  green" gate are retained exactly as the handoff asked.
- **Handoff ask (b)** says the ValidationProfile is "already required when code_evolution is True." This spec
  **replaces** that mandatory-profile rule with a secure-by-default gate (profile **or**
  `allow_unvalidated_code`, §4) — a deliberate strengthening over the handoff, decided by Karsten in review
  round 1, so a general scoring function needn't carry a lakehouse-shaped profile yet the safety guarantee is
  never silently dropped.
- **openevolve version** (handoff CONTEXT + line 515): the handoff cites "openevolve 0.3.2" from the
  silly-kicks environment. This repo pins `openevolve>=0.2.0` (`pyproject.toml:22`), resolved to **0.2.27**;
  the 53-green baseline is against 0.2.27, and the plan must **not** silently re-pin to 0.3.2 (GCE-SPEC-03).
