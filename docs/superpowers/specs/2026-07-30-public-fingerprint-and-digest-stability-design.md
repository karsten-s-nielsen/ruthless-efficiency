# Spec — public `fingerprint` API + digest-stability contract

**Date:** 2026-07-30
**Status:** rev 3 — silly-kicks review rounds 1 and 2 incorporated; **approved to implement**
**Baseline:** `20e68e5`, tag `v0.3.1`, version `0.3.1`, clean tree
**Origin:** a change request from a silly-kicks session raising two items. This spec **accepts both**,
adds one item neither raised, and records the decisions taken on release semantics.
**Review:** two rounds from the requesting silly-kicks session, both verdict *accept*. Round 1's finding
— the golden corpus spans one platform while the requesting consumer spans two — is incorporated as §5.
Round 2 raised four items, all resolved in §0's table. Every measurement either side reported was re-run
here before acceptance, which is how round 2's C2 turned out to be a documentation defect rather than a
disagreement about digests.

**Target release:** `0.4.0` — minor, because the public API gains two names.

---

## 0. Summary of decisions

| Item | Verdict | Note |
|---|---|---|
| §1 Promote `fingerprint` / `fingerprint_model` to the public API | **ACCEPT** | The trigger this project wrote down has fired. §1. |
| A public `ruthless/fingerprint.py` **module**, as this project's own §6 non-goal worded the promotion | **REJECT** | Not what the change request asked for — it asked for two `__all__` entries. Functions go public; the module stays private. A public module of that name is a live shadowing hazard. §1.2. |
| §2 Commit the 0.3.1 digest verification as a test | **ACCEPT — scope changed** | Per-`_tag`-branch coverage, not a replay of the release note's 17 payloads. §3. |
| §2 State the stability contract in the docstring | **ACCEPT — strengthened** | No carve-out, including for correctness fixes. §2. |
| **New:** `pydantic` is unpinned and `fingerprint_model` digests `model_dump()` output | **ACCEPT — pin `<3`** | Raised by neither side. The same failure arrives via a transitive bump. §4. |
| **Review finding B:** the golden corpus pins Linux bytes; the consumer spans two platforms | **ACCEPT — both remedies** | Windows CI leg **and** the contract sentence. Re-measured before acceptance. §5. |
| Review B.3: §3.2's stated reason for banning bare `Path` overstates the hazard | **ACCEPT the tightening, not the error** | The original sentence carried the qualifier; naming *parsing* as the locus is still better, and it is what surfaces §5.1. §3.2. |
| Round-2 C1: §3.4's extra-free import is what lets the lean Windows leg carry the evolve payload | **ACCEPT — recorded as a constraint** | Confirmed. Was incidental; now stated so a refactor cannot strip it silently. §3.4. |
| Round-2 C2: §5.1's digest literals are not reproducible from the spec | **ACCEPT — literals removed entirely** | Both readings were correct; the unstated payload key was the defect. Pinned bytes now live only in the golden table. §5.1. |
| Round-2 C3: "Linux-built wheels" names a provenance that does not exist | **ACCEPT** | 0.3.1 ships one universal `py3-none-any` wheel plus an sdist, confirmed against the PyPI API. §7. |
| Round-2 C4: `pytest`'s source under `.[dev]` could not be located | **PREMISE CORRECTED — no action** | `pytest>=8` is in the `dev` extra in `pyproject.toml`, on the same line as ruff/pyright/import-linter. Nothing implicit, nothing to check. |

### 0.1 What the change request got right, verified rather than assumed

Both claims were checked against this tree before any design work:

1. `ruthless/__init__.py` has no `fingerprint` export, and `tests/test_public_api.py`'s
   `_EXPECTED_PUBLIC` pins the surface without it. Confirmed.
2. `tests/test_fingerprint.py` is **entirely relational** — every assertion is `a != b` or `a == a`.
   Not one digest byte is pinned. Confirmed by reading all 220 lines, not by grep alone. (The sole
   non-comparison assertion, `assert fingerprint_model(_Rich())`, is a truthiness check.)
3. The trigger is written down verbatim in
   `docs/superpowers/specs/2026-07-29-parallel-error-model-and-cache-identity.md` §6: *"No public
   fingerprint API. `_fingerprint` is private, absent from `__all__`. Promotion is a later, additive
   decision that should wait for a second real caller."*
4. `CHANGELOG.md:13-15` claims byte-identity across 17 payloads. That verification was performed by
   hand during the 0.3.1 cycle and never entered the suite. Confirmed.

The gap is real and is exactly as characterised: the right check was run once, then not institutionalised.

---

## 1. Public surface

### 1.1 What changes

`ruthless/__init__.py` gains one import and two `__all__` entries:

```python
from ruthless._fingerprint import fingerprint, fingerprint_model
```

Signatures are **unchanged**. `fingerprint(payload: Mapping[str, object], *, length: int = 16) -> str`
and `fingerprint_model(model: BaseModel, *, exclude: frozenset[str] = frozenset(), length: int = 16)
-> str` are already the shapes a public caller wants. The consumer absorbs the `Mapping` shape on
their side, which they proposed and which serves `fingerprint_model`'s "declare what determines the
content" rule — named inputs are self-documenting where a positional sequence is not.

### 1.2 The implementation stays in `ruthless/_fingerprint.py`

Promoting the *functions* is additive. Renaming the *module* to `ruthless/fingerprint.py` is not, and
would be actively harmful: `import ruthless.fingerprint` anywhere in the process rebinds the
parent-package attribute from the re-exported function to the module object, so
`from ruthless import fingerprint` would yield different objects depending on unrelated import order.

Private module, public functions. This is already the repo's stated convention — `__init__.py`'s own
docstring declares that deep submodule paths are implementation detail and the curated top-level
namespace is the supported surface.

Consequence: `.importlinter` needs no edit. `ruthless._fingerprint` stays listed under
`core-isolation`, because the module has not moved and the core still must not import strategies or
backends.

### 1.3 Files touched by the promotion

(Scoped to §1. `pyproject.toml` is touched by §4, `.github/workflows/ci.yml` by §5, and the test/doc
files by §2–§3; the implementation plan carries the consolidated list.)

| File | Change |
|---|---|
| `ruthless/__init__.py` | Import + two `__all__` entries |
| `tests/test_public_api.py` | Two entries in `_EXPECTED_PUBLIC` |
| `ruthless/_fingerprint.py` | Module docstring: its first paragraph currently asserts "absent from `ruthless.__all__`", which this change makes false |

---

## 2. The digest-stability contract

### 2.1 The rule, as written

Stated in `fingerprint`'s docstring, in ADR-002, and in CLAUDE.md's cache-identity convention:

> The digest is a **persisted cache key in consumer storage**. Any change that alters the digest of a
> payload that already fingerprinted is **breaking, not additive** — regardless of motive, including a
> correctness fix. It takes the minor slot under `0.x`, and its CHANGELOG entry must state explicitly
> that it invalidates existing caches. Extending `_tag` to a new type is additive **only if** every
> already-supported payload digests identically.
>
> The guarantee is over the **logical value**, not over how the caller constructed it. `Path(str)` in
> particular parses per-platform — a backslash is a separator on Windows and an ordinary character on
> POSIX — so a caller spanning platforms must pass `PurePosixPath` or normalise before fingerprinting.
> Constructing the value is the caller's responsibility; digesting it identically everywhere is ours.

### 2.2 Why no carve-out

A carve-out for correctness fixes is the loophole every future digest change would be argued into, and
it buys nothing for the consumer: an orphaned cache is equally silent whether the digest moved for a
good reason or a careless one. The escape valve is deliberately **social** rather than procedural —
changing a digest requires editing the golden table in §3, and that edit is the visible, reviewable
moment the whole mechanism exists to manufacture.

This is not a new standard. 0.3.0 already behaved this way; its CHANGELOG entry distinguishes itself
from 0.3.1 precisely on whether caches were invalidated. §2.1 converts an observed practice into a
written rule that does not depend on who happens to be editing.

### 2.3 Why this matters downstream, in the consumer's terms

silly-kicks' `scripts/_driver.py` keys corpus-shard resume on the digest. A silent digest change
orphans every shard generation, and each driver then full-recomputes over a corpus that takes hours,
with nothing reporting it. That is the expensive-silent failure class this project's error model
exists to eliminate. It also means the `0.x` "API may change" caveat now has a downstream that depends
on **digest bytes**, not merely on function signatures — a Hyrum's Law surface that was previously
untested and undeclared.

---

## 3. The golden corpus

### 3.1 Shape

New file `tests/test_fingerprint_golden.py`. Digests are **literals in the test source**, not a
checked-in data file the test can regenerate. A regenerable fixture is exactly what a contributor
regenerates to make CI green; the friction is the mechanism, not an inconvenience to design away.

### 3.2 Coverage: per-`_tag`-branch, not a replay of the 17

The release note's 17 payloads are not recorded anywhere and would have to be reconstructed. More
importantly, they were selected to prove one thing — 0.3.0→0.3.1 additivity — and not to cover the
branch table. The failure this test exists to catch is a `_tag` edit, so coverage follows `_tag`'s
branches:

- Every scalar branch: `int`, `bool` (both), `float` including `-0.0`, `0.0`, `nan`, `inf`, `-inf`,
  `str`, `None`.
- `PurePath`: `PurePosixPath` and `PureWindowsPath` forms of the same logical path. Golden entries use
  these two explicitly and **never bare `Path`**. The hazard is narrower than "`Path` is
  platform-dependent" and worth naming exactly: `_tag` normalises via `as_posix()`, so a *digested*
  path is already platform-independent — `PurePosixPath("a/b")` and `PureWindowsPath("a/b")` digest
  identically. What diverges is **`Path(str)` parsing**, which is resolved at construction time,
  before `_tag` ever sees the value. Naming the flavour explicitly removes the construction step from
  the table. Measured in §5.1.
- All three enum flavours: plain `Enum`, `IntEnum`, `StrEnum`, plus two enum classes sharing a value.
- `datetime` naive, `datetime` aware, `date`.
- Every container: `list`, `tuple`, `set`, `frozenset`, nested `Mapping`, and non-`str` mapping keys
  (`int`, `bool`, `float`, `PurePath`, `Enum`).
- Both `length` values: the default 16 and an explicit 8.
- `fingerprint_model`: a plain model, a model with an exclusion applied, and a model carrying
  `Path`/`Enum`/`datetime` fields (see §4). The `Path`-typed field's value must be a **forward-slash
  literal** (`Path("runs/a")`), which `as_posix()` normalises identically on both platforms. A
  backslash literal here would be the one place §3.2's ban can be evaded — the annotation is `Path`, so
  pydantic constructs the platform-native flavour on validation — and would fail §5.2's Windows leg on
  its first run.

### 3.3 The subclass-order traps must be pinned as equalities

`tests/test_fingerprint.py` already asserts that `IntEnum` does not collide with `int`, `bool` with
`int`, and `datetime` with `date`. Those are **inequality** assertions, and a `_tag` reordering that
breaks the contract changes *both* sides of the pair — the inequality can survive while every consumer
digest moves. Only pinned bytes catch that. The golden table therefore pins **both sides of each
pair**, and this reasoning is recorded in the file so it is not later "simplified" back into an
inequality.

### 3.4 Evolve's real seed payload

Pinned via core `EvalConfig` (which lives in `ruthless/config/common.py`, not the evolve strategy
package) — the same model `_eval_fingerprint` digests, since it fingerprints `cfg.evaluation` — and an
explicit `exclude=frozenset({"timeout_seconds"})`, so the golden file needs no
`[evolve]` extra and no import from a strategy package. A single assertion in the evolve suite pins
that `_SEED_CACHE_EXCLUDE` still equals that set, so the two cannot drift apart silently.

**This is load-bearing for §5.2 and must not be "simplified" later.** The extra-free import was chosen
before §5 existed, purely to keep the golden file lean. It is also the only reason the lean Windows leg
can carry the evolve payload at all: `core-lean` installs `.[dev]` and its `--ignore` list names
directories and specific files, so a top-level `tests/test_fingerprint_golden.py` runs there — but only
while its imports stay within core. Rewriting §3.4 to import `_eval_fingerprint` from the strategy
package would keep every test passing on Linux and silently strip the most realistic payload from the
cross-platform gate.

### 3.5 Failure message

The assertion failure names the contract rather than merely reporting a mismatch: it must tell a
contributor who has just edited `_tag` that they have made a breaking change, point at §2.1, and state
that regenerating the value is a release-semantics decision, not a test fix.

### 3.6 Rejected alternative

Auto-generating the table into a JSON fixture the test compares against. It makes the corpus trivial
to extend, and removes the only thing that makes it work.

---

## 4. `pydantic` is unpinned — raised by neither side

`fingerprint_model` digests `model_dump()` output, and `pyproject.toml:15` declares `pydantic>=2` with
no upper bound. Pydantic's python-mode serialisation of `Path` and `Enum` is precisely the kind of
behaviour that can shift across a major version. If it shifts, **every consumer digest moves without
anyone touching `_fingerprint.py`** — silly-kicks' orphaned-shard failure arriving through a transitive
dependency bump rather than a code edit.

Two responses, both taken:

1. The golden corpus includes a `fingerprint_model` case carrying `Path`, `Enum` and `datetime`
   fields, so a pydantic-induced shift fails ruthless's CI instead of a consumer's corpus.
2. `pydantic` is pinned `<3`, with a comment naming the guarantee it protects. The precedent is in the
   same line of the same file: `numpy>=1.24,<3` is already pinned, with a comment naming the
   determinism gate it protects. This is the same class of guarantee.

The pin must be stated back to the consumer, so their own dependency resolution accounts for it before
they adopt `0.4.0`.

---

## 5. The cross-platform axis (review finding B)

**ruthless CI is Linux-only.** `.github/workflows/ci.yml` — both jobs are `runs-on: ubuntu-latest`,
no matrix. Confirmed by reading the file. silly-kicks spans a Windows dev box, a Linux DGX, and both
OSes in its own CI, and keys corpus-shard resume on the digest.

So a golden table alone pins Linux bytes and **can never observe a platform-dependent digest**. §3.2's
prescription keeps platform-dependent values out of the table, which keeps the table stable — but that
makes the table *silent* on cross-platform equality rather than *establishing* it. Cross-platform
divergence is the same orphaned-shard failure §2.3 describes, arriving through platform instead of
version, and §2.1's rule as originally written spoke only of algorithm changes and release slots.

### 5.1 The residual dependence, measured

Re-measured on this Windows box against the working tree rather than taken on report:

```
input       PurePosixPath.as_posix()   PureWindowsPath.as_posix()   digests agree
'a/b'       'a/b'                      'a/b'                        yes
'a\b'       'a\b'                      'a/b'                        no
'C:\x\y'    'C:\x\y'                   'C:/x/y'                     no
```

`_tag` returns `["path", value.as_posix()]`, so two paths digest identically exactly when their
`as_posix()` forms are equal. The third column therefore follows from the second by construction — it
is a consequence, not a separate measurement.

The same *logical* path digests identically everywhere: that is what `as_posix()` buys, and it is why
§3.2's original claim needed tightening rather than reversing. The divergence is entirely in
`Path(str)` **parsing**: `Path("a\b")` is a two-component path on Windows and a single filename
containing a backslash on POSIX. Identical source line, identical input string, two digests, with no
version changed and nothing in ruthless moved.

**No digest literal appears in this spec, deliberately.** Rev 2 quoted two, and a reviewer could not
recompute them because the payload key was never stated — the values were correct for `{"k": …}` and
the reviewer reasonably guessed `{"p": …}`. Both readings are right; the document was the problem. The
deeper reason not to fix this by stating the key is that `tests/test_fingerprint_golden.py` is the
**single source of truth** for pinned bytes, and a spec is a historical document that cannot be kept in
step with it. A digest quoted here would eventually disagree with the table, or worse, be lifted into
it on the assumption it had been checked. The argument above needs no hex to stand.

### 5.2 Both remedies, not one

1. **A Windows CI leg**, mirroring `core-lean` on `windows-latest`: `[dev]` extra only, same core test
   subset, no `[backends]`/`[evolve]`/`[optuna]` heavy dependencies. This converts cross-platform
   digest equality from an assumption into a gate, and — unlike keeping platform-dependent values out
   of the table — it also catches a *future* `_tag` branch that is accidentally platform-sensitive.
   Scoping it to `core-lean`'s shape rather than the full `test` job is deliberate: matrixing the full
   job would install `openevolve`/`docker`/`huggingface_hub` on Windows and risk turning a fingerprint
   release into a third-party Windows-compatibility exercise.
2. **The contract sentence** in §2.1, stating that the guarantee is over the logical value and that
   construction is the caller's responsibility.

Neither alone suffices. The CI leg without the sentence leaves a correct-but-undocumented property the
next contributor need not realise is load-bearing; the sentence without the CI leg leaves the guarantee
resting on every future consumer having read a docstring.

**Incidental benefit, stated so it is not mistaken for scope creep:** ruthless is *developed* on
Windows and has never once been CI-tested there. The leg closes that standing gap at the cost of one
job that installs no heavy dependencies.

---

## 6. Release

`0.4.0`. Minor rather than patch because the public API gains two names — the inverse of the
0.3.1 entry's opening line ("Patch, not minor: no public API changed").

Per this project's release convention, the one-line `ruthless/_version.py` bump lands in the **same
commit** as the work it describes, alongside a `0.4.0` CHANGELOG section. Feature branch →
`/final-review` → single commit → PR → merge → `v0.4.0` tag → OIDC publish.

The CHANGELOG entry must state that this release does **not** invalidate existing caches — the digest
algorithm is untouched. Under §2.1 that sentence is now a required part of any release that touches
`_fingerprint`.

---

## 7. Verification beyond the suite

The five-gate local quality run (`ruff check`, `ruff format --check`, `pyright`, `lint-imports`,
`pytest`) is necessary but does not establish the one thing that matters here: that the pinned bytes
are what consumers actually installed, rather than merely what this tree emits.

Two executable checks, run against wheels fetched from PyPI:

1. Recompute the entire golden table under published `ruthless==0.3.1` and diff against the pinned
   literals. This proves the corpus pins the shipped bytes.
2. Recompute the **entire** table under published `ruthless==0.3.0` too — **every case, no skip list** —
   classifying each as *raised* / *identical* / *differs*. This puts the CHANGELOG's hand-run
   byte-identity claim under something executable for the first time.

> **Corrected after execution.** Item 2 originally said to recompute only "the subset of the table that
> 0.3.0 supported — excluding `Path`, `Enum`, `datetime` and `date`, which raised `TypeError` before
> 0.3.1". That premise is **false for two of those types, and the falsehood is the whole finding.**
> 0.3.0 had no `enum` branch at all, so only *plain* `Enum` raised: an `IntEnum` member fell through to
> the `int` branch and a `str`-subclassing `Enum` member to the `str` branch. Both digested successfully
> — identically to the bare `int`/`str` value they wrap — and 0.3.1's new `enum` branch then moved them.
>
> A skip list keyed on the prefix `enum-` would have skipped exactly the two cases that reveal this, and
> reported a clean `mismatches=0`. Measured, all 44 cases, under published 0.3.0: **12 raised, 32
> digested, of which 30 byte-identical and 2 differ** (`IntEnum`, str-`Enum`). So **0.3.1 was not purely
> additive**, and under §2.1's contract should have been classed cache-invalidating for those payload
> shapes. The `[0.3.1]` CHANGELOG entry now carries a correction saying so.
>
> The generalisable lesson, and the reason this is corrected in place rather than quietly fixed: a
> verification whose skip list is derived from the *belief being tested* cannot falsify that belief. Run
> the whole corpus and classify the outcomes; let the failures be data, not exclusions.

Both are one-off verifications reported in the PR, not CI steps; installing historical releases on
every run would buy nothing once the literals are pinned.

Both run on the **Windows** dev box, which is a free strengthening rather than a limitation: the
pinned literals are authored on Windows and verified there against the **published universal wheel**,
while §5.2's CI leg checks the reverse direction on every push. Neither check is meaningful alone.

"Universal" is the precise word and matters here. 0.3.1 publishes exactly two artifacts —
`ruthless_efficiency-0.3.1-py3-none-any.whl` and an sdist (confirmed against the PyPI API) — so there
is no per-platform build and no build provenance to appeal to. One artifact runs everywhere, which is
why the only platform question is where it *executes*, and why §5.2's leg is the thing that answers it.

---

## 8. Non-goals

- **No digest-algorithm version constant.** Considered and declined: it adds public surface beyond
  what was asked, and §2.1 plus §3 already make an unannounced digest change fail in ruthless's own CI.
- **No change to `fingerprint` / `fingerprint_model` signatures or behaviour.** This release is a
  visibility and contract change. Any behaviour change would, by §2.1, be breaking.
- **No promotion of other private core modules.** `_io`, `_logging`, `_provenance` and `_version` have
  no second caller and no consumer-persisted output. The trigger has not fired for them.
- **No consumer-side work.** silly-kicks' `token_inputs` reshaping to a `Mapping` runs in that repo.
