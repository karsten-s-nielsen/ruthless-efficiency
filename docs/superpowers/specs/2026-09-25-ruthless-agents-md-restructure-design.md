# Design — `AGENTS.md` restructure for ruthless-efficiency

- **Date:** 2026-09-25
- **Author session:** ruthless-efficiency
- **Independent reviewer:** `karstenskyt__silly-kicks_part-deux` (spec / plan / impl)
- **Pattern origin:** the validated `AGENTS.md` restructure shipped in part-deux and APPROVED (two review rounds each) for luxury-lakehouse and pining-for-the-data. Reports at `D:\Development\_reviews\2026-09-25-{lakehouse,pining}-agents-md-restructure-{spec,plan,impl}[-r2].md`; the delivered pining artifacts (`AGENTS.md`, `CLAUDE.md` shim, `docs/context/*.md`, `src/tests/test_agents_md_budget.py`, `src/tests/fixtures/agents_md_invariants.json`) are the golden template. **This document is the ruthless adaptation.** Every hard-won lesson from those rounds is carried verbatim in intent and re-derived against ruthless's measured reality; §§6.3, 7, 8 record the ruthless-specific deltas that neither lakehouse nor pining had (both are unpackaged; ruthless is a published PyPI package consumed downstream, and it ships `tests/` in the sdist).

---

## 1. Summary

Partition the always-loaded project instruction file into:

1. **Class-1** — current, terse, enforceable invariants and pointers — which stays always-loaded.
2. **Class-2** — the *why*, the history, and the measurements behind those invariants — which moves to an on-demand context store under `docs/context/`.

Rename the always-loaded file from `CLAUDE.md` to the cross-tool **`AGENTS.md`**, and leave a one-line `CLAUDE.md` shim that `@`-imports it so Claude Code keeps auto-loading the instructions. Add a CI anti-bloat gate whose migration-safety oracle mechanically proves that no class-1 invariant was dropped in the move.

The durable value is the **rename** (cross-tool `AGENTS.md` consistency across ruthless-efficiency, luxury-lakehouse, pining-for-the-data, and silly-kicks) and the **gate** (keeps the file lean forever). The context tree is sized by the measured split (§2.1) — not forced to a fixed shape.

This is a docs/infra change with **one intentional non-doc edit** — the `pyproject.toml` sdist `exclude` list (§8) — which is behaviour-preserving packaging metadata. **No shipped `ruthless/` code changes.** The one live-reference repoint (`CONTRIBUTING.md`, §7) is a behaviour-preserving doc pointer.

## 2. Current state (measured at `c2dbecd`, this repo's `main` HEAD)

| Fact | Value | How measured |
|---|---|---|
| `CLAUDE.md` size | **14640 bytes on disk / 199 lines** | `Path("CLAUDE.md").read_bytes()` length; line count |
| Non-ASCII bytes | **108** (UTF-8 em-dashes `—`, arrows `→`, `≈`, `≥`, etc.) | `sum(1 for b in read_bytes() if b > 127)` |
| Nested instruction files | **none** — single top-level `CLAUDE.md` only | `git ls-files | grep -i claude.md` → `CLAUDE.md` |
| 16-hex digest literals inside `CLAUDE.md` | **none** | the digest guard's own regex `(?<![\w.])[0-9a-f]{16}(?![\w.])` over the file |
| ADR home | **`docs/adr/`** — `ADR-001-…`, `ADR-002-…` (hyphen form, 3-digit) | tree layout; `grep` for `ADR-\d{3}` in `CLAUDE.md` |
| Tracked files referencing `CLAUDE.md` | **14** (see §7 for the three-bucket breakdown) | `git grep -l "CLAUDE\.md"` |
| Functional `open()`/`Path()` of `CLAUDE.md` in code | **0** | `git grep -nE "open\(...CLAUDE\.md\|Path\(...CLAUDE\.md" -- ruthless/** tests/** scripts/**` → NONE |
| Test dir / config | `testpaths = ["tests"]`; fixtures at `tests/fixtures/` **exists** | `pyproject.toml [tool.pytest.ini_options]`; `ls tests/fixtures` |
| pyright scope | **both** `ruthless` and `tests` | `pyproject.toml [tool.pyright] include = ["ruthless", "tests"]` |
| CI checkout | `actions/checkout@v7.0.1`, **no `fetch-depth`** → shallow clone | `.github/workflows/ci.yml` |
| Version source | single-sourced in `ruthless/_version.py` (`[tool.hatch.version] path`, `dynamic`); no bump script | `pyproject.toml`; `ruthless/_version.py` (`0.6.0`) |
| Packaged? | **Yes** — published to PyPI (consumed by silly-kicks + lakehouse). Wheel = `packages = ["ruthless"]` only; sdist has an `exclude` list. See §8. | `pyproject.toml [tool.hatch.build.targets.{wheel,sdist}]` |
| `@import` mechanism | **empirically verified** at Claude Code **2.1.280** (this running version) — a `CLAUDE.md` shim of `<!-- … -->\n@AGENTS.md` in a scratch project caused a headless `claude -p` to load `AGENTS.md` and emit its unique sentinel `IMPORT_OK_RUTHLESS_7F3A9QZ` (exit 0) | canary run 2026-09-25, `claude --version` |
| Packaging baseline (before) | **wheel: 45 entries** (`ruthless/**` + `dist-info`, no docs, no tests); **sdist: 210 entries** (ships `ruthless/**`, `tests/**` incl. `tests/fixtures/{__init__.py,objectives.py}` + `tests/test_docs_no_digest_literals.py`, `docs/adr/**`, `docs/c4/**`; does **not** ship `CLAUDE.md`, `docs/superpowers`, `docs/audits`, `.github`) | `uv build`; `tar tzf` the sdist, `zipfile` the wheel |

### 2.1 Measured class-1 / class-2 split

Per-`##`-section byte measurement (UTF-8, on-disk):

| Section | Bytes | Class | Disposition |
|---|---:|---|---|
| Title + intro paragraph (phase-by-phase history) | 1436 | mostly 2 | keep one-line purpose + "Ships at" line class-1; **move** the Phase 1A/1B/2 narrative |
| `## Architecture` | 2525 | mixed | terse invariants stay class-1; deep rationale moves |
| `## Key conventions` | 5927 | mixed | invariants stay class-1; the heavy rationale (cache identity / `_tag` / digest stability / provenance / `__version__` / `map_work_units` taxonomy) moves — the biggest cut |
| `## Local quality gate` | 354 | 1 | keep (the 5 imperative commands) |
| `## Workflow conventions` | 408 | 1 | keep (TDD, `/final-review`, no-commit-without-approval, no-worktrees) |
| `## Tech stack` | 430 | 1 | keep terse; long pin-rationale may move |
| `## Scope map` | 977 | 2 | **move** (Phase 1A/1B/2 status/history) |
| `## Key Phase-2 conventions` | 1369 | mixed | invariants stay class-1; rationale moves |
| `## Reference docs` | 825 | 1 | keep (the load-bearing spec/plan pointers) |
| `## Architecture decisions` | 389 | 1 | keep (ADR-001 / ADR-002 pointers) |
| **TOTAL** | **14640** | | |

**Estimated class-1 after a fresh terse rewrite ≈ 7 KB; class-2 to move ≈ 7.6 KB, concentrated in `## Key conventions` and the phase history.** This measurement — not a target shape — sizes the context tree (§4.2) and the byte budget (§6.2).

## 3. Goals / non-goals

**Goals**
- `AGENTS.md` is the single always-loaded, terse, enforceable class-1 file.
- `CLAUDE.md` is a shim that `@`-imports `AGENTS.md`; Claude Code behaviour is unchanged (verified §2).
- Every class-2 fact is preserved verbatim in `docs/context/`; **zero information dropped** without recorded owner approval.
- A CI gate keeps `AGENTS.md` under a byte ceiling and mechanically proves invariant survival on every future change.
- **The published package is provably unchanged in runtime content**: the wheel file list is byte-identical, and the sdist gains only the new test + fixtures (zero instruction files). No version bump.

**Non-goals**
- No change to the shared global `~/.claude/CLAUDE.md` (out of scope, explicitly left).
- No behaviour change to shipped `ruthless/` code.
- No new strategy/backend, no API change, no dependency change.

## 4. Target layout

```
AGENTS.md                                     # class-1, always-loaded (target ≤ ~7.5 KB, §6.2)
CLAUDE.md                                     # shim → @AGENTS.md
docs/context/phases-and-scope.md              # class-2: phase-by-phase history + Scope map + Phase-2 rationale
docs/context/architecture-rationale.md        # class-2: hexagonal / backend-dispatch / unified-error-model why
docs/context/cache-identity-and-fingerprint.md# class-2: cache identity / _tag / digest stability / provenance / __version__ / map_work_units taxonomy why
tests/fixtures/claude_md_at_c2dbecd.md        # committed pre-change snapshot (the oracle's baseline)
tests/fixtures/agents_md_invariants.json      # the invariant inventory
tests/test_agents_md_budget.py                # the anti-bloat gate + migration-safety oracle
```

### 4.1 The shim (`CLAUDE.md`)

Exact content — two HTML-comment lines then the import, nothing else:

```
<!-- Canonical project instructions live in AGENTS.md (cross-tool convention). -->
<!-- Claude Code auto-loads CLAUDE.md; this shim @-imports AGENTS.md so both resolve to one source. -->
@AGENTS.md
```

**HTML comments (`<!-- … -->`), never `#`** — a `#` line in a Markdown file is an H1 heading, not a comment. The `@AGENTS.md` line is the sole functional line. This is the exact shape the empirical canary (§2) validated.

### 4.2 Context store: three single-purpose files (gold-standard)

A context store groups by **recall domain** — one purpose per file — so a reader pulls exactly one focused file. The measured class-2 (§2.1) is three distinct domains, and the mass in each clears the non-stub floor (§6.2) comfortably; two files would fuse unrelated domains, four would create a near-stub `provenance/version` file that trips the floor. So three:

- **`docs/context/phases-and-scope.md`** — the intro paragraph's Phase 1A / 1B / 2 narrative and the `## Scope map` status detail, plus the *why* behind the Phase-2 conventions (`CachedObjective` fast-path reasoning, C3-resume semantics, the observer's Optuna-only-by-design justification). The "what shipped when" history.
- **`docs/context/architecture-rationale.md`** — the deep rationale under `## Architecture`: the hexagonal one-way-dependency reasoning, the backend inter-candidate-dispatch model (why `InProcessBackend`/`local_cuda` document-and-ignore `timeout` while cross-process backends enforce it), and the unified-error-model reasoning (why `EvolveEvaluator` is the single place mapping failure to the OpenEvolve sentinel).
- **`docs/context/cache-identity-and-fingerprint.md`** — the largest class-2 mass: cache identity as an exclusion set, `_fingerprint` as the one hashing implementation, `_tag`'s load-bearing branch order (Enum/bool/datetime), the digest-bytes compatibility contract (public since 0.4.0; the golden-table single-source rule; the "no `.md` may quote a digest" rule and its enforcing test), provenance never-overclaims reasoning, the `__version__`/core-isolation reasoning, and the `map_work_units` `WorkUnitMapError` taxonomy detail.

Each context file opens with a one-line back-pointer to `AGENTS.md` and is discoverable from the `AGENTS.md` bullet that summarises it (`… — see docs/context/<file>.md`).

### 4.3 `AGENTS.md` class-1 content

A fresh, terse rewrite (not a copy) preserving every enforceable invariant and every load-bearing pointer:

- **Header** — title `# ruthless-efficiency`, one-line purpose, and the `Ships at <version> (0.x — API unstable)` line (the release-process note that this line and the `_version.py` line are the hand-edits on release stays class-1).
- **`## Architecture`** — one terse bullet per structural invariant, each pointing to `docs/context/architecture-rationale.md` for the *why*: hexagonal core defines the ports + value types; one-way dependency direction enforced by import-linter (3 contracts, `lint-imports` green); each strategy owns its loop; backends are the inter-candidate dispatch path on the single `evaluate(candidate, objective, *, timeout) -> Metrics` port (`InProcessBackend` core; `RemoteObjective`/`RemoteRef`; cross-process enforce `timeout`, in-process document-and-ignore; `BackendPool` priority + bounded transient-retry); the unified error model (`TransientEvaluationError` / `FatalEvaluationError`; `EvolveEvaluator` the single sentinel-mapper).
- **`## Key conventions`** — the enforceable kernels stay, each long one delegating detail to `docs/context/cache-identity-and-fingerprint.md` or an ADR: scored-metric finiteness only (`classify_metric` raises on inf/NaN target; diagnostics may be non-finite); fatal errors vs penalties distinct; `Candidate` hashable (frozen; don't mutate `params`); `Result` treat-as-immutable; `map_work_units` always attempts EVERY unit; cache identity is a declared EXCLUSION set (`ruthless._fingerprint` single impl; `fingerprint_model(exclude=...)`; fail-closed; naming a non-existent field raises; `_tag` branch order load-bearing; digest bytes a compatibility contract — ADR-002); provenance never overclaims; `__version__` lives in `ruthless/_version.py` (single source); config is a discriminated-union surface; library never configures root logging (`ruthless._logging.get_logger`); the CLI objective loader is trusted-config-only.
- **`## Local quality gate`** — the 5 commands, verbatim.
- **`## Workflow conventions`** — TDD; `/final-review` mandatory pre-commit; no commit without approval; no worktrees.
- **`## Tech stack`** — Python ≥3.10, pydantic v2 (`<3`), numpy (`<3`), pyyaml; the pin *reasons* may compress into `cache-identity-and-fingerprint.md` / `phases-and-scope.md`, but the pins themselves stay.
- **`## Key Phase-2 conventions`** — the `CachedObjective` / OptunaStrategy-resume / observer invariants stay (kernel), with rationale in `phases-and-scope.md`.
- **`## Reference docs`** and **`## Architecture decisions`** — kept: the spec/plan pointers and the ADR-001/ADR-002 pointers.

## 5. The invariant inventory (`agents_md_invariants.json`)

A committed JSON fixture enumerating every class-1 invariant that must survive the migration. Schema per entry:

```json
{
  "id": "kebab-case-stable-id",
  "class1_anchor": "a ≥12-char, ≥2-non-stopword-token phrase from the imperative that MUST appear in AGENTS.md",
  "symbols": ["distinctive tokens — fn/const/path/ADR names — that must survive in AGENTS.md ∪ context files"],
  "home": "agents" | "context:<file>"
}
```

Rules (validator-enforced, §6.2):
- `class1_anchor` is a distinctive phrase (≥ 12 chars **and** ≥ 2 non-stopword tokens) — rejects vacuous anchors that could match `AGENTS.md` boilerplate by accident.
- `symbols` must be **distinctive** — a bare ADR reference in ruthless's form (matched by `^ADR[- ]?\d{3}$`, e.g. `ADR-002`) is **rejected** (ADR numbers recur across the file; matching on them alone would pass vacuously). Each symbol is a function/const/path name (`fingerprint_model`, `ruthless._fingerprint`, `classify_metric`, `WorkUnitMapError`, `ruthless/_version.py`, `RemoteRef`, `CachedObjective`, `patch_params`, `ProgressEvent`, …) or a distinctive multi-word phrase.
- **Every entry carries ≥ 1 symbol.** Symbols are the stable anti-fabrication signal that grounding (§6.2 check 7) keys on — this is a restructure, so every class-1 invariant already exists in the old file and has at least one real token there (RUTHLESS-SPEC-05).
- The fixture carries a top-level `"count"`, and the test carries a module-level `INVARIANT_COUNT` constant; **both** are set to the enumerated N, and the test asserts `count == len(entries) == INVARIANT_COUNT`. This **dual-source anti-shrink pin** is what makes a silent shrink (delete an entry *and* decrement `count`) fail. The concrete inventory and N are produced in the plan/impl (estimated **N ≈ 20–24**, reflecting ruthless's high invariant density — larger than pining's 18).

**`RUTHLESS-SPEC-01` — pointer forms keyed to ruthless.** ruthless uses the hyphen 3-digit ADR form (`ADR-001`, `ADR-002`) and the doc homes `docs/adr/`, `docs/superpowers/{specs,plans}/`, and (new) `docs/context/`. Therefore:
- `POINTER_RE = ADR[- ]?\d{3}|docs/adr/|docs/superpowers/|docs/context/|docs/[\w./-]+\.md` — accepts ruthless's ADR form (tolerating a future space form) and every doc-home path.
- `BARE_ADR_RE = ^ADR[- ]?\d{3}$` — the symbols reject.
A pining-style `\d{3,4}` or a lakehouse-style hyphen-only `ADR-\d+` would either over-match or, if too narrow, false-fail a kept bullet; ruthless's forms are `\d{3}`.

## 6. The CI anti-bloat gate + migration-safety oracle

New test module `tests/test_agents_md_budget.py`, collected by the existing `testpaths = ["tests"]`. **Every file read uses `encoding="utf-8"` explicitly** (the file has 108 non-ASCII bytes; a bare `open()` on the Windows dev box defaults to `cp1252` and mojibakes em-dashes/arrows — a false FAIL on exactly the machine §10's local gate runs on; the Linux `test` leg would hide it, but the `core-lean-windows` leg would not).

**Stdlib + pytest only.** Like `tests/test_docs_no_digest_literals.py`, the module imports only the standard library and `pytest` (`json`, `re`, `os`, `pathlib`). This (a) violates no import-linter contract (the contracts govern `ruthless.*` layering; a stdlib-only test is irrelevant to them), and (b) lets it run in the lean `core-lean` / `core-lean-windows` CI legs, not only the full `test` leg. It imports no `ruthless` module.

### 6.1 Committed-snapshot oracle — never `git show`

The oracle reads a **committed fixture** `tests/fixtures/claude_md_at_c2dbecd.md` (a verbatim byte-copy of `CLAUDE.md` at `c2dbecd`, the pre-change content), via `read_text(encoding="utf-8")`. It must **never** shell out to `git show <sha>:CLAUDE.md` — ruthless CI checks out shallow (no `fetch-depth`, §2), so the parent blob is absent and `git show` exits 128. This is the load-bearing lesson carried from lakehouse/pining.

### 6.2 Checks

Byte budgets assert `Path(...).stat().st_size` (bytes on disk), never `len(text)`. The per-bullet cap is a **char** cap on decoded text — deliberately distinct. Provisional constants (re-pinned at impl, §6-note):

```
ORIGINAL_BYTES        = 14640   # pinned: CLAUDE.md @ c2dbecd
LANDED_BYTES          = <measured AGENTS.md size>   # pinned in impl once the rewrite exists
TARGET                = 7680    # cut-verification bound (~52% of ORIGINAL); LANDED must be ≤ this
CEILING               = int(LANDED_BYTES * 1.15)    # future-bloat brake
CONTEXT_FILE_FLOOR    = 800
CONTEXT_TOTAL_FLOOR   = 4096    # expected ~7 KB class-2; floor proves it landed, not deleted
PER_BULLET_CHAR_CAP   = 600
POINTER_BULLET_THRESHOLD = 250
INVARIANT_COUNT       = <N>     # == inventory["count"] == len(entries)
```

1. **`test_shim_integrity`** — read `CLAUDE.md`; keep non-blank lines whose `lstrip()` does **not** start with `<!--`; assert the survivors are exactly `["@AGENTS.md"]`. (Strips `<!--` HTML comments — not `#`.)
2. **`test_agents_md_byte_budget`** — `AGENTS.md.stat().st_size`:
   - hard **CEILING** = `LANDED_BYTES × 1.15` — the operative anti-bloat brake against *future* growth.
   - **TARGET** = 7680 B — the cut-verification bound. At migration `LANDED_BYTES` **must** be ≤ TARGET or the gate hard-FAILs; thereafter TARGET sits below CEILING as the visible warning line.
   - **`RUTHLESS-SPEC-02` — measured-derived TARGET, no invariant pressure.** TARGET is sized from the measured class-1 slice (§2.1, ~7 KB), *not* a fixed small number. If, at impl, the terse class-1 rewrite legitimately exceeds TARGET because the invariants demand it, the resolution is to **raise TARGET with a recorded owner note** — **never to drop or thin an invariant to hit a number** (owner's standing scope rule: nothing dropped below the agreed bar without explicit approval). The real proof that *this* migration cut the ~7.6 KB of class-2 is the conservation floor (check 3) + the completeness oracle (check 6), not the byte number alone. TARGET is soft only while `LANDED ≤ TARGET`; a landed size above it fails the gate and triggers the raise-or-move decision.
3. **`test_context_conservation_floor`** — each `docs/context/*.md` `stat().st_size ≥ CONTEXT_FILE_FLOOR` (non-stub) **and** their combined size `≥ CONTEXT_TOTAL_FLOOR` (proves the class-2 actually landed there rather than being deleted). Anti-hollowing companion to the completeness check.
4. **`test_per_bullet_char_cap`** — split `AGENTS.md` into `- ` bullets; assert each bullet's **decoded-`str` length ≤ `PER_BULLET_CHAR_CAP`**; and that every bullet ≥ `POINTER_BULLET_THRESHOLD` chars carries a pointer matched by `POINTER_RE` (RUTHLESS-SPEC-01). Short self-contained bullets are exempt; the threshold is 250 (a ruthless kernel bullet can name a `ruthless/…` path or a function without a docs pointer at ≤ 250). Keeps class-2 prose from creeping back into a bullet while accepting every legitimate pointer form.
5. **`test_inventory_schema_valid`** — load `agents_md_invariants.json`; assert `count == len(entries) == INVARIANT_COUNT`; every `class1_anchor` satisfies the ≥12-char / ≥2-non-stopword-token rule; **every entry has ≥ 1 symbol**; no `symbols` entry is a bare ADR number (`BARE_ADR_RE`); all ids unique; every `home` is `agents` or `context:*`.
6. **`test_invariant_completeness`** (the migration-safety oracle) — for each inventory entry: the `class1_anchor` substring appears in the UTF-8-decoded `AGENTS.md`; every `symbol` appears in `AGENTS.md ∪ docs/context/*.md`. A dropped invariant fails this test.
7. **`test_inventory_grounded_in_snapshot`** (`RUTHLESS-SPEC-05`) — for each entry, **at least one `symbol` appears in the committed snapshot** (ground on the stable signal, not the anchor). The `class1_anchor` is fresh terse phrasing that may legitimately not be in the old file, so it is the wrong thing to ground on; symbols are real pre-existing tokens, so requiring ≥ 1 in the snapshot is the true anti-fabrication check, and it composes with the schema rule (§5, every entry has ≥ 1 symbol) so no entry can dodge it. *Precedent note:* pining's delivered test grounded on `anchor OR ≥1 symbol`, and lakehouse has **no** snapshot-grounding test at all — there is no "all tokens in snapshot" precedent; this is a deliberate strengthening over both, adopting the reviewer's stable-signal option.

All substring matching runs on UTF-8-decoded text so a non-ASCII anchor matches.

### 6.3 `RUTHLESS-SPEC-03` — source-checkout skip guard (the packaged-sdist trap)

This is the standout ruthless-specific requirement; lakehouse and pining are unpackaged and their tests never ship, so neither faced it.

**The trap.** ruthless ships `tests/` in the published sdist (§2, §8), and downstream packagers (Debian, conda-forge, Nix) run that suite at build time. But `AGENTS.md`, `CLAUDE.md`, and `docs/context/` are **excluded** from the sdist (§8). So a new `tests/test_agents_md_budget.py` running inside an unpacked sdist would find `AGENTS.md` absent and every check would error — turning a published artifact's suite red. This is the **exact** failure `tests/test_docs_no_digest_literals.py` already documents and guards against: its comment records that the 0.4.0 sdist ran "1 failed / 181 passed" before its `_IS_SOURCE_CHECKOUT` skip was added.

**The fix (mirror the existing, reviewed control — Chesterton's Fence).** The module skips entirely when it is not a source checkout:

```python
_IS_SOURCE_CHECKOUT = (REPO_ROOT / "AGENTS.md").is_file()
pytestmark = pytest.mark.skipif(
    not _IS_SOURCE_CHECKOUT,
    reason="not a source checkout — the sdist excludes AGENTS.md / docs/context (see pyproject sdist exclude)",
)
```

`AGENTS.md` is the natural marker — it is this gate's subject and is sdist-excluded, so "absent" means exactly "not a source checkout" rather than anything about the gate's subject. In CI and the local quality gate (both run from a checkout) the guard is always live; a skip is visible in `pytest -v`. Rejected alternative: excluding the new test + fixtures from the sdist. That is not the repo's established pattern (`tests/` ships wholesale and the checkout-only tests skip), would make the shipped suite inconsistent, and is more fiddly than the one-line marker.

**Digest-guard interaction (verified safe).** `tests/test_docs_no_digest_literals.py` walks **every** `.md` under the repo root. After the restructure it will newly scan `AGENTS.md`, `docs/context/*.md`, and the snapshot `tests/fixtures/claude_md_at_c2dbecd.md`. All three are verbatim moves/copies of `CLAUDE.md`, which contains **no** 16-hex digest literal (§2) — so the digest guard stays green. The snapshot filename's `c2dbecd` is 7 hex chars and cannot match the 16-hex pattern. Keeping `/CLAUDE.md` on the sdist exclude list (§8) also preserves that test's own `_IS_SOURCE_CHECKOUT = (REPO_ROOT / "CLAUDE.md").is_file()` marker and the comment that explains it.

## 7. Reference sweep (three buckets)

`git grep -l "CLAUDE\.md"` (tracked only) → **14 files**. Unlike pining ("repoint zero"), ruthless has **two functional refs** (one repoint, one packaging update). Buckets:

- **LIVE rule-text ref → REPOINT to `AGENTS.md`:**
  - `CONTRIBUTING.md:78` — "The conventions above are detailed in [`CLAUDE.md`](CLAUDE.md)". Points a contributor to the live conventions doc; repoint the link text + target to `AGENTS.md` (behaviour-preserving doc pointer).
- **FUNCTIONAL packaging ref → UPDATE (§8):**
  - `pyproject.toml` — `/CLAUDE.md` in the sdist `exclude`; add `/AGENTS.md` and `/docs/context`, keep `/CLAUDE.md`.
- **HISTORICAL (records of past cycles) → LEAVE unchanged:**
  - `CHANGELOG.md` (3 hits — release-history prose, incl. the note that the "Ships at" line lives in the instruction file; historical entries are not rewritten).
  - `docs/adr/ADR-002-…md`; `docs/audits/2026-05-28-audit-cleanup.md`; the 8 `docs/superpowers/{specs,plans}/*.md` files (4 plans + 4 specs).
  - `tests/test_docs_no_digest_literals.py` — its docstring/comments mention `CLAUDE.md` twice: L9 ("the rule was written into CLAUDE.md before this file existed") is a past-tense historical statement (leave); L63–67 uses `CLAUDE.md` as the `_IS_SOURCE_CHECKOUT` marker and the comment stays **accurate** after the change (the shim remains, remains sdist-excluded) — leave (Chesterton's Fence: a working control). **No functional edit to this file.** Impl re-confirms these are the only two mentions and that both stay correct.

Impl re-runs the grep, re-buckets every hit, and confirms **0** functional `open("CLAUDE.md")` in code. Any surprise LIVE ref is repointed and recorded.

## 8. Packaging & versioning (`RUTHLESS-SPEC-04` — hard gate)

ruthless is published to PyPI and consumed by silly-kicks + lakehouse, so "did the package content change?" is a **hard gate proven with the built artifact**, not an assumption.

**The wheel** uses `packages = ["ruthless"]` — it contains only `ruthless/**` (+ `dist-info`). `AGENTS.md`, `CLAUDE.md`, and `docs/context/` are outside that package and were never in the wheel; no `ruthless/` code changes. → **wheel file list byte-identical before/after** (baseline: 45 entries).

**The sdist** has the `exclude` list under `[tool.hatch.build.targets.sdist]`, currently `["/.github", "/CLAUDE.md", "/docs/superpowers", "/docs/audits"]`. Edit:
- **add `/AGENTS.md`** — the renamed instruction file must stay out of the package exactly as `/CLAUDE.md` did.
- **add `/docs/context`** — the new dev-facing instruction context is like `/docs/superpowers` (already excluded); it must not newly ship.
- **keep `/CLAUDE.md`** — the shim stays excluded (required for the digest test's `_IS_SOURCE_CHECKOUT` marker and for consistency).

After the edit, the sdist gains **only** the three new files under `tests/` (which ships): `tests/test_agents_md_budget.py`, `tests/fixtures/claude_md_at_c2dbecd.md`, `tests/fixtures/agents_md_invariants.json` — baseline 210 → 213 entries. It gains **zero** instruction files (AGENTS.md / CLAUDE.md / docs/context).

**Version decision — no bump.** The wheel (what consumers `pip install` and import) is byte-identical, and the sdist delta is test-only — the same class of change as any test addition, which ruthless ships without a bump beyond the feature it tests. Adding a test is not a runtime-content change. → **no `_version.py` bump, no CHANGELOG release entry.** (A CHANGELOG *Unreleased* note is optional and owner-decided.)

**Proof (impl gate).** `uv build` before and after; diff the wheel file lists (must be **identical**) and the sdist file lists (must differ by **exactly** the three `tests/` files, with **no** `AGENTS.md`/`CLAUDE.md`/`docs/context` entry). If the wheel list changes at all, or the sdist gains any instruction file, stop — the exclude is wrong or something leaked into `ruthless/`.

## 9. Scope & safety

- Verbatim moves — class-2 is **cut** from `CLAUDE.md` and pasted into the context files, not paraphrased.
- **Zero drops by default.** If any class-2 fact is judged redundant and dropped rather than moved, it is recorded in the inventory with its reason and requires explicit owner approval first (an approved drop, not a silent one). This includes the TARGET decision (RUTHLESS-SPEC-02): raise the budget rather than thin an invariant.
- The class-1 rewrite is *fresh* (terse), so `AGENTS.md` is smaller than the class-1 slice of the original; conservation of the *moved* material is guaranteed by the completeness check (§6.2 check 6) + the context floor (check 3), not by total byte parity.
- Global instruction file untouched. No behaviour change to shipped `ruthless/` code. The one packaging edit (§8) is behaviour-preserving metadata, proven by the artifact diff.

## 10. Acceptance criteria — local gate mirrors CI exactly

Run ruthless's **exact** five-check gate (CLAUDE.md "Local quality gate"), all green, before the work is declared complete:

1. `uv run ruff check ruthless tests`
2. `uv run ruff format --check ruthless tests`
3. `uv run pyright` (both `ruthless` and `tests` — the new test must be pyright-basic clean)
4. `uv run lint-imports` (must stay green; the stdlib-only test violates no contract)
5. `uv run pytest -v` (collects `tests/test_agents_md_budget.py`; it is at `tests/` root, so it runs in the full `test` leg **and** the `core-lean` / `core-lean-windows` legs)

Plus:
- a **red→green proof**: the gate test is written and shown RED (against the un-migrated tree) before the restructure, and green after;
- the **packaging artifact diff** (§8) green;
- the **digest guard** (`test_docs_no_digest_literals.py`) still green over the new `.md` files.

## 11. Workflow & commit discipline

- One **feature branch** off `main` (never a worktree); commits accumulate there; PR opens from it. Branch: `chore/agents-md-restructure`.
- A **single commit** for the whole cycle — the restructure + the gate + the context files + the sweep repoint + the pyproject edit + the spec + the plan, as one fully-tested coherent state. **No per-step / micro-commits.**
- **`/final-review` runs before the commit** (repo rule). It also generates/updates `docs/c4/architecture.html`; this restructure changes **no** architecture, so the C4 diagram is expected to be diff-free — if `/final-review` regenerates it, verify the diff is empty (or a legitimate render) and that Graphviz `dot` (not Smetana) rendered, per the global C4 rule. A spurious C4 diff is investigated, not blindly committed.
- `commit → push → PR → merge` are **four separate owner-gated actions.** None is implied by approval of a prior one. The session stops and shows the diff / file list at the commit gate and waits for an explicit "commit"; likewise for push, PR, and merge.
- The spec and plan documents commit **with** the finished code in that single commit (not earlier).

## 12. Review checkpoints (independent)

`karstenskyt__silly-kicks_part-deux` reviews at spec, plan, and impl; reports land in `D:\Development\_reviews\` as `2026-09-2X-ruthless-agents-md-restructure-{spec,plan,impl}.md`. This session delivers each artifact, stops, and hands off. This session reads those reports and revises; it does not self-approve.

## 13. Risks / could-not-verify

- **Exact invariant set / N** — enumerated in the plan/impl from the committed snapshot; the spec fixes only the schema, the dual-source count pin, and the estimate (N ≈ 20–24).
- **`LANDED_BYTES` / TARGET** — provisional (7680 B); pinned at impl to the measured `AGENTS.md` size. If the terse class-1 legitimately exceeds TARGET, TARGET is **raised with an owner note**, never met by dropping an invariant (RUTHLESS-SPEC-02).
- **`@import`** verified at 2.1.280 (this version); a future Claude Code changing import semantics would need re-verification, but the shim + `AGENTS.md` satisfies the cross-tool `AGENTS.md` convention independent of Claude Code's importer.
- **Downstream sdist suite** — the skip guard (§6.3) is the safeguard; impl should, if practical, build the sdist and run its bundled `pytest` to confirm the new module *skips* (not fails) outside a checkout, matching the digest test's precedent.
- **C4 regeneration noise** — `/final-review` may re-render the diagram; §11 requires verifying any resulting diff is legitimate before it enters the single commit.
```