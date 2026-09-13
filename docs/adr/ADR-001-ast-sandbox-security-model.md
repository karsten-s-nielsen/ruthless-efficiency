# ADR-001: AST allowlist security model for evolve Level-2 code evolution

- **Status:** Accepted
- **Date:** 2026-05-28
- **Component:** `ruthless/strategies/evolve_/sandbox.py` (`validate_program`, `ValidationProfile`)

## Context

The `[evolve]` strategy supports *Level-2 code evolution*: an LLM proposes Python source for
`custom_embed()` / `custom_layers()` functions that are spliced into a consumer model and then
**executed for real** by a compute backend (`local_cuda` in-process, or `remote_ssh` / `hf_jobs` on a
node). LLM-generated source is untrusted: a proposal could attempt data exfiltration, arbitrary code
execution (`os.system`, `subprocess`), attribute-traversal escapes (`().__class__.__bases__…`,
`__globals__`, `__builtins__`), import of dangerous modules, or f-string-based obfuscation.

We need a screening layer that admits the narrow shape of valid candidate functions (tensor math over
`self.<known attrs>` and an allowed numeric namespace) and rejects everything else, **before** the
source is written to disk and run.

A denylist of dangerous constructs is unbounded and fails open (a construct we forgot to ban slips
through). The valid surface, by contrast, is small and enumerable.

## Decision

Use a **default-deny AST allowlist**, parameterised per consumer by a `ValidationProfile`.
`validate_program(source, profile, *, code_evolution)`:

1. **Parses** the source to an AST (syntax errors → reject).
2. **Gates on `code_evolution`**: a config-only program (no `custom_embed`/`custom_layers`) always
   passes; if either function is present and `code_evolution` is `False`, reject.
3. **Validates signatures** exactly against `profile.patch_signature` (embed) and `profile.layers_args`
   (layers); `custom_layers` must `return {…}` a dict literal, whose string keys become the dynamic
   `self.<attr>` names allowed inside `custom_embed`.
4. **Walks every node** through an allowlist visitor that admits only:
   - leaf nodes, arithmetic/comparison/boolean operators, and generic container/statement nodes
     (`BinOp`, `If`, `For`, `While`, comprehensions, assignments, `return`, …);
   - `self.<attr>` access **only** when `<attr> ∈ profile.known_model_attrs ∪ layers-keys`;
   - attribute/call chains rooted in `profile.allowed_namespaces` (e.g. `torch`, `math`) or in a
     local variable;
   - a fixed builtin allowlist (`range`, `len`, `int`, `float`, `min`, `max`, `sum`, `isinstance`, …);
   - calls to functions defined locally in the same scope.

   It **rejects**: `import` / `from … import`; f-strings (`JoinedStr` / `FormattedValue`); any dunder
   attribute or method (name starting with `__`); attribute access on an unknown namespace; unknown
   bare function calls; and any AST node type not on the allowlist (fails closed).

`profile.rejected_builtins` lets a consumer additionally ban builtins that would otherwise pass.

## Consequences

- **This is a belt, not a boundary.** The validator shrinks the attack surface of LLM-generated code;
  it is *not* a security sandbox. The validated source is still executed in-process / on a node, and
  config-only programs bypass the validator entirely. **Real isolation must come from the execution
  environment** — run untrusted candidates only inside an OS-level sandbox (container, VM, seccomp).
  Consumer documentation must state this.
- **Fails closed.** An AST node type, namespace, or builtin we did not anticipate is rejected rather
  than admitted, so the validator degrades to "too strict" (a rejected good candidate) rather than
  "too permissive" (an admitted exploit).
- **Per-consumer parameterisation.** Each consumer ships a `ValidationProfile` (the allowed attrs,
  namespaces, signature, and rejected builtins) rather than the validator hard-coding one model's
  shape — the generic validator stays in the substrate.
- **Maintenance cost.** New legitimate constructs (a new builtin, a new namespace) require an explicit
  allowlist addition; this is the intended trade-off for failing closed.

## Addendum (0.6.0) — general code evolution is default-closed

`0.6.0` generalises `EvolveStrategy` to evolve arbitrarily-named code, and reframes when this belt runs.
Source-attach is now keyed on `evolution.code_evolution`, not on the hardcoded
`custom_embed`/`custom_layers` names, which leave the core. The belt's **validation logic is unchanged** —
it still validates only `custom_embed`/`custom_layers` bodies and passes any other top-level function
through as a "config-only program". Since `validate_program` is now only ever called for code-evolution
candidates, its previously-vestigial `code_evolution` parameter (and the "code evolution disabled" rejection
branch) were removed as dead code — a signature-only change to an internal function, no allowlist behavior
affected.

Because the belt is structurally lakehouse-shaped and does not fit a general scoring function, validation
becomes **opt-out-gated rather than mandatory — but secure-by-default**: a `code_evolution=True` run is
**rejected** (at config validation *and* at `EvolveEvaluator` construction) unless it either supplies a
`validation_profile` or sets `EvolveConfig.allow_unvalidated_code=True`. Setting that opt-out runs
LLM-generated code **unsandboxed by conscious operator choice** — the same "belt, not a boundary" caveat
above applies with full force: real isolation must come from the execution environment. The default
(no profile, no opt-out) fails closed, so silent unsandboxed execution is impossible.
