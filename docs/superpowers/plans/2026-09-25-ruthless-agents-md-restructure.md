# AGENTS.md Restructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: this plan is a single coupled change landing in **one commit**; execute inline with `superpowers:executing-plans` (batch with checkpoints). Subagent-driven execution is **not** used here (the single-commit surface makes it needless). Steps use checkbox (`- [ ]`) syntax. **No per-task commits** — see Global Constraints.

**Goal:** Rename the always-loaded project instruction file `CLAUDE.md` → cross-tool `AGENTS.md` behind a one-line `@import` shim, move the class-2 (why/history) content to an on-demand `docs/context/` store, and add a CI anti-bloat gate whose migration-safety oracle proves no class-1 invariant was dropped — while proving the published PyPI package's content is unchanged (no version bump).

**Architecture:** `AGENTS.md` holds terse class-1 invariants + pointers (always loaded). `CLAUDE.md` becomes `<!-- … -->\n@AGENTS.md` (empirically verified to auto-load `AGENTS.md` at Claude Code 2.1.280). Three single-purpose context files under `docs/context/` hold the moved class-2. A stdlib-only pytest module in `tests/` reads a committed pre-change snapshot (never `git show` — CI is shallow) and a committed invariant inventory to enforce byte budgets, shim purity, and per-invariant survival; it **skips outside a source checkout** so it never reds the published sdist. The `pyproject.toml` sdist `exclude` gains `/AGENTS.md` + `/docs/context`.

**Tech Stack:** Python 3.10, pytest, `uv`, ruff, pyright, import-linter, hatchling, GitHub Actions (`ci.yml`), Markdown.

**Spec:** `docs/superpowers/specs/2026-09-25-ruthless-agents-md-restructure-design.md` (APPROVED, incl. RUTHLESS-SPEC-05 strengthening). The plan argues from it; executors read both.

## Global Constraints

Exact values copied from the spec. Every task implicitly includes these.

- **Single commit for the whole cycle.** No per-step / per-task / micro-commits. Every task below ends at a *tested deliverable*, not a commit. The one commit happens only in Task 7, after `/final-review` and a full green local gate. (This overrides any "commit often" convention.)
- **`commit → push → PR → merge` are four separate owner-gated actions.** None is implied by approval of a prior one. Stop and show the diff/file-list at each gate; wait for an explicit "commit" / "push" / "open the PR" / "merge".
- **One feature branch off `main`** (never a worktree). Branch: `chore/agents-md-restructure`.
- **All file reads in test/oracle code use `encoding="utf-8"` explicitly** (`CLAUDE.md` has **108 non-ASCII bytes**; a bare `open()` on Windows defaults to cp1252 and mojibakes em-dashes/arrows → false FAIL locally and in the `core-lean-windows` CI leg).
- **Byte budgets assert `Path(...).stat().st_size`** (bytes on disk), never `len(text)`. The per-bullet cap is a **char** cap on decoded text — deliberately distinct.
- **Committed-snapshot oracle:** read the pre-change file from `tests/fixtures/claude_md_at_c2dbecd.md`, never `git show <sha>:CLAUDE.md` (CI checkout is shallow — no `fetch-depth` — so the parent blob is absent and `git show` exits 128).
- **Gate test is stdlib + pytest only** (`json`, `re`, `os`, `pathlib`, `pytest`). It imports no `ruthless` module, so it violates no import-linter contract and runs in the lean `core-lean` / `core-lean-windows` legs as well as the full `test` leg.
- **Source-checkout skip guard (RUTHLESS-SPEC-03):** the module is `pytest.mark.skipif`'d out when `AGENTS.md` is absent (an unpacked sdist), mirroring `tests/test_docs_no_digest_literals.py`'s `_IS_SOURCE_CHECKOUT`. Prevents a red published sdist.
- **Grounding is on the stable signal (RUTHLESS-SPEC-05):** `test_inventory_grounded_in_snapshot` requires ≥ 1 `symbol` per entry in the snapshot (not the anchor); the schema requires every entry to carry ≥ 1 symbol.
- **Zero information dropped.** Class-2 is *cut and pasted verbatim* into context files, not paraphrased. Any drop requires recorded owner approval first. If the terse class-1 rewrite exceeds `TARGET`, **raise `TARGET` with an owner note — never thin an invariant** (RUTHLESS-SPEC-02).
- **No behaviour change to shipped `ruthless/` code.** The sweep touches zero code (no functional `open("CLAUDE.md")` exists).
- **Packaging hard gate (RUTHLESS-SPEC-04):** `uv build` before/after; wheel file list **byte-identical**; sdist gains **only** the three new `tests/` files, **zero** instruction files. → **no version bump**, no CHANGELOG release entry.
- **Local gate == CI check set exactly** (Task 6): `uv run ruff check ruthless tests`, `uv run ruff format --check ruthless tests`, `uv run pyright`, `uv run lint-imports`, `uv run pytest -v`.
- **Scope:** the shared global `~/.claude/CLAUDE.md` is **not** touched.

---

## File structure

| File | Responsibility |
|---|---|
| `AGENTS.md` (create) | Class-1 always-loaded instructions (terse; provisional target ≤ 7680 B). |
| `CLAUDE.md` (rewrite → shim) | `<!-- … -->` comments + `@AGENTS.md`, nothing else. |
| `docs/context/phases-and-scope.md` (create) | Class-2: Phase 1A/1B/2 history + Scope map + Phase-2-convention rationale. |
| `docs/context/architecture-rationale.md` (create) | Class-2: hexagonal / backend-dispatch / timeout / unified-error-model why. |
| `docs/context/cache-identity-and-fingerprint.md` (create) | Class-2: cache identity / `_fingerprint` / `_tag` order / digest stability / provenance / `__version__` / `map_work_units` taxonomy why. |
| `tests/fixtures/claude_md_at_c2dbecd.md` (create) | Verbatim pre-change snapshot of `CLAUDE.md` @ `c2dbecd`. |
| `tests/fixtures/agents_md_invariants.json` (create) | The class-1 invariant inventory (28 entries). |
| `tests/test_agents_md_budget.py` (create) | The anti-bloat gate + migration-safety oracle (skips outside a checkout). |
| `pyproject.toml` (modify: sdist `exclude`) | Add `/AGENTS.md` + `/docs/context`, keep `/CLAUDE.md`. |
| `CONTRIBUTING.md` (modify: L78) | Repoint the LIVE conventions link `CLAUDE.md` → `AGENTS.md`. |

---

## Task 1: Committed snapshot fixture + invariant inventory

**Files:**
- Create: `tests/fixtures/claude_md_at_c2dbecd.md`
- Create: `tests/fixtures/agents_md_invariants.json`

**Interfaces:**
- Produces: the snapshot file (oracle baseline) and the inventory JSON consumed by `test_agents_md_budget.py` (Task 2). Inventory shape: `{"count": 28, "entries": [{"id","class1_anchor","symbols":[...],"home"}]}`.

- [ ] **Step 1: Copy the pre-change file verbatim into the fixture**

`c2dbecd` is the current `main` HEAD, so the working-tree `CLAUDE.md` *is* the pre-change content. Copy it byte-for-byte and verify identical:

```bash
cp CLAUDE.md tests/fixtures/claude_md_at_c2dbecd.md
diff CLAUDE.md tests/fixtures/claude_md_at_c2dbecd.md && echo IDENTICAL
python -c "import pathlib; print(pathlib.Path('tests/fixtures/claude_md_at_c2dbecd.md').stat().st_size)"   # expect 14640
```

- [ ] **Step 2: Author the invariant inventory**

Create `tests/fixtures/agents_md_invariants.json` with **exactly 28 entries**. Each `class1_anchor` is a plain phrase (no backticks/markdown) that MUST appear verbatim in `AGENTS.md` (Task 3); each `symbols` entry is a distinctive token; **every entry carries ≥ 1 symbol** and at least one of its symbols MUST appear in the snapshot (Step 3). `home` is `agents` (invariant lives fully in `AGENTS.md`) or `context:<file>` (terse anchor in `AGENTS.md`, detail-symbols in that context file).

```json
{
  "count": 28,
  "entries": [
    {"id": "arch-hexagonal-ports", "class1_anchor": "defines the ports and value types", "symbols": ["Objective", "SearchStrategy", "ComputeBackend", "Candidate", "Evaluation", "Result"], "home": "agents"},
    {"id": "arch-one-way-deps", "class1_anchor": "one-way dependency direction", "symbols": ["import-linter", "lint-imports", "core-isolation"], "home": "agents"},
    {"id": "arch-strategy-owns-loop", "class1_anchor": "each strategy owns its loop", "symbols": ["report.py", "template-method"], "home": "context:architecture-rationale"},
    {"id": "arch-backend-dispatch", "class1_anchor": "inter-candidate dispatch path", "symbols": ["InProcessBackend", "BackendPool", "RemoteObjective", "RemoteRef", "local_cuda", "remote_ssh", "hf_jobs"], "home": "context:architecture-rationale"},
    {"id": "arch-timeout-contract", "class1_anchor": "enforce the per-candidate timeout", "symbols": ["document-and-ignore"], "home": "context:architecture-rationale"},
    {"id": "arch-unified-error-model", "class1_anchor": "Backends never record a sentinel score", "symbols": ["TransientEvaluationError", "FatalEvaluationError", "EvolveEvaluator"], "home": "context:architecture-rationale"},
    {"id": "conv-scored-metric-finiteness", "class1_anchor": "Scored-metric finiteness only", "symbols": ["classify_metric"], "home": "agents"},
    {"id": "conv-fatal-vs-penalty", "class1_anchor": "Fatal errors vs. penalties are distinct", "symbols": ["ruthless.errors", "penalty_metrics"], "home": "agents"},
    {"id": "conv-candidate-hashable", "class1_anchor": "Candidate is hashable", "symbols": ["frozen", "__hash__", "params"], "home": "agents"},
    {"id": "conv-result-immutable", "class1_anchor": "treat-as-immutable once returned", "symbols": ["SearchStrategy.run"], "home": "agents"},
    {"id": "conv-map-work-units", "class1_anchor": "always attempts EVERY unit", "symbols": ["map_work_units", "WorkUnitMapError", "BrokenExecutor", "on_error"], "home": "context:cache-identity-and-fingerprint"},
    {"id": "conv-cache-exclusion-set", "class1_anchor": "Cache identity is a declared EXCLUSION set", "symbols": ["ruthless._fingerprint", "fingerprint_model", "_SEED_CACHE_EXCLUDE"], "home": "context:cache-identity-and-fingerprint"},
    {"id": "conv-tag-branch-order", "class1_anchor": "branch order is load-bearing", "symbols": ["Enum", "IntEnum", "StrEnum", "datetime", "date"], "home": "context:cache-identity-and-fingerprint"},
    {"id": "conv-digest-compat-contract", "class1_anchor": "Digest bytes are a compatibility contract", "symbols": ["fingerprint_model", "test_fingerprint_golden.py"], "home": "context:cache-identity-and-fingerprint"},
    {"id": "conv-no-md-digest", "class1_anchor": "no .md file may quote a digest", "symbols": ["test_docs_no_digest_literals.py"], "home": "context:cache-identity-and-fingerprint"},
    {"id": "conv-pydantic-pin", "class1_anchor": "digests model_dump()", "symbols": ["pydantic", "model_dump", "fingerprint_model"], "home": "context:cache-identity-and-fingerprint"},
    {"id": "conv-provenance", "class1_anchor": "Provenance never overclaims", "symbols": ["ruthless._provenance", "code_identity"], "home": "context:cache-identity-and-fingerprint"},
    {"id": "conv-version-ssot", "class1_anchor": "lives in ruthless/_version.py", "symbols": ["ruthless/_version.py", "hatchling", "dynamic"], "home": "agents"},
    {"id": "conv-config-union", "class1_anchor": "discriminated-union surface", "symbols": ["RuthlessConfig", "FloatRange", "IntRange", "Choice"], "home": "agents"},
    {"id": "conv-logging", "class1_anchor": "Library never configures root logging", "symbols": ["ruthless._logging.get_logger"], "home": "agents"},
    {"id": "conv-cli-loader", "class1_anchor": "CLI objective loader is trusted-config-only", "symbols": ["resolve_objective", "importlib", "isinstance"], "home": "agents"},
    {"id": "p2-cached-objective", "class1_anchor": "rejects tuning any param not in patch_params", "symbols": ["CachedObjective", "evaluate_patch", "patch_params", "assert_cache_equivalence"], "home": "context:phases-and-scope"},
    {"id": "p2-optuna-resume", "class1_anchor": "no lost/dup trials", "symbols": ["OptunaStrategy", "study.trials", "SQLite"], "home": "context:phases-and-scope"},
    {"id": "p2-observer", "class1_anchor": "raising observer is logged-and-isolated", "symbols": ["Observer", "ProgressEvent", "positional-only"], "home": "context:phases-and-scope"},
    {"id": "p2-groupscoring-deferred", "class1_anchor": "Group-scoring was deferred", "symbols": ["Group-scoring", "score_fn"], "home": "context:phases-and-scope"},
    {"id": "gate-local-quality", "class1_anchor": "Run all five before declaring work done", "symbols": ["lint-imports", "pyright", "ruff"], "home": "agents"},
    {"id": "workflow-approval", "class1_anchor": "No commit without explicit user approval", "symbols": ["/final-review", "worktrees"], "home": "agents"},
    {"id": "tech-pins", "class1_anchor": "pinned for RNG-stream stability", "symbols": ["numpy", "pydantic", "pyyaml"], "home": "agents"}
  ]
}
```

- [ ] **Step 3: Ground every entry in the snapshot (≥ 1 symbol present) + schema sanity**

Each entry must cite at least one symbol traceable to the pre-change file (RUTHLESS-SPEC-05: grounds on the stable signal, proves the inventory is not fabricated). Run:

```bash
python - <<'PY'
import json, pathlib, re
snap = pathlib.Path("tests/fixtures/claude_md_at_c2dbecd.md").read_text(encoding="utf-8")
inv = json.loads(pathlib.Path("tests/fixtures/agents_md_invariants.json").read_text(encoding="utf-8"))
STOP = {"the","a","an","of","to","in","on","and","or","is","are","be","for","with","that","this","it","as","at","by","so"}
bare = re.compile(r"^ADR[- ]?\d{3}$")
tok = re.compile(r"[\w'/.+-]+")
ok = True
for e in inv["entries"]:
    syms = e["symbols"]
    grounded = any(s in snap for s in syms)
    a = e["class1_anchor"]
    toks = [t for t in tok.findall(a.lower()) if t not in STOP]
    schema = bool(syms) and len(a) >= 12 and len(toks) >= 2 and not any(bare.match(s) for s in syms) and (e["home"] == "agents" or e["home"].startswith("context:"))
    if not (grounded and schema):
        ok = False
        print("BAD ", e["id"], "grounded" if grounded else "UNGROUNDED", "schema-ok" if schema else "SCHEMA-FAIL")
ids = [e["id"] for e in inv["entries"]]
print("count/len/unique:", inv["count"], len(ids), len(set(ids)) == len(ids))
print("ALL OK" if ok and inv["count"] == len(ids) == 28 and len(set(ids)) == len(ids) else "PROBLEMS ABOVE")
PY
```

Must print `ALL OK`. If any entry is `UNGROUNDED`, a symbol string is mistyped relative to the source — fix the symbol to match the snapshot exactly (do **not** invent, do not delete the entry). If `SCHEMA-FAIL`, fix the anchor/symbols per the printed reason.

- [ ] **Step 4: Exhaustiveness pass (PLAN-02) — confirm no kernel is un-inventoried**

The completeness oracle proves no *inventoried* invariant is dropped; it cannot prove the 28 are *exhaustive*. Before finalising anchors, read `CLAUDE.md` `## Architecture` + `## Key conventions` + `## Key Phase-2 conventions` once, bullet by bullet, and confirm every enforceable kernel maps to an inventory `id`. The pre-authored 28 already covers: the 6 Architecture kernels, the 15 Key-conventions kernels (`conv-*` ids — incl. the cache/fingerprint/digest/provenance sub-rules split out of the single cache-identity bullet **and** the pydantic-`<3`/`model_dump()` digest pin, `conv-pydantic-pin`), the 4 Phase-2 kernels, and the 3 local-gate / workflow / tech-pin rules (6 + 15 + 4 + 3 = 28). The `ADR-001` / `ADR-002` and `## Reference docs` pointers are load-bearing **pointers**, preserved by keeping those sections in `AGENTS.md` (spec §4.3), not by the inventory — consistent with pining. If this pass finds an un-inventoried enforceable kernel, **add** an entry (bump `count` + `INVARIANT_COUNT` together) — never leave it out.

---

## Task 2: The gate test module (written RED)

**Files:**
- Create: `tests/test_agents_md_budget.py`

**Interfaces:**
- Consumes: the two fixtures from Task 1.
- Produces: 7 tests + a module-level skip guard. `LANDED_BYTES` is a placeholder here and is pinned to the measured `AGENTS.md` size in Task 3 Step 5.

- [ ] **Step 1: Write the full test module**

```python
"""Anti-bloat gate + migration-safety oracle for AGENTS.md.

Guards that the always-loaded instruction file (AGENTS.md) stays terse
(class-1), that CLAUDE.md stays a pure @AGENTS.md import shim, and that no
class-1 invariant was dropped when class-2 content moved to docs/context/.

Stdlib + pytest only (like tests/test_docs_no_digest_literals.py): it imports no
ruthless module, so it violates no import-linter contract and runs in the lean
core-lean / core-lean-windows CI legs too.

SKIPPED OUTSIDE A SOURCE CHECKOUT. The published sdist ships tests/ but EXCLUDES
AGENTS.md / CLAUDE.md / docs/context (see the [tool.hatch.build.targets.sdist]
exclude list). Downstream packagers (Debian, conda-forge, Nix) run this suite at
build time; without the guard this module would error on a missing AGENTS.md and
red a published artifact — the exact failure tests/test_docs_no_digest_literals.py
records for the 0.4.0 sdist. AGENTS.md is the marker: absent == not a checkout.

Spec: docs/superpowers/specs/2026-09-25-ruthless-agents-md-restructure-design.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]  # tests/ -> repo root
AGENTS = REPO_ROOT / "AGENTS.md"
SHIM = REPO_ROOT / "CLAUDE.md"
CONTEXT_DIR = REPO_ROOT / "docs" / "context"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SNAPSHOT = FIXTURES / "claude_md_at_c2dbecd.md"
INVENTORY = FIXTURES / "agents_md_invariants.json"

# Source-checkout guard (RUTHLESS-SPEC-03): AGENTS.md is sdist-excluded, so its
# absence means "unpacked sdist", not a real failure. Skip the whole module there.
_IS_SOURCE_CHECKOUT = AGENTS.is_file()
pytestmark = pytest.mark.skipif(
    not _IS_SOURCE_CHECKOUT,
    reason="not a source checkout — the sdist excludes AGENTS.md / docs/context (see pyproject sdist exclude)",
)

# --- byte budgets (bytes on disk, never len(text)) ---
ORIGINAL_BYTES = 14640  # pinned: CLAUDE.md @ c2dbecd
LANDED_BYTES = 6800  # measured AGENTS.md size; PINNED in Task 3 Step 5
TARGET = 7680  # cut-verification bound: LANDED_BYTES must be <= this (RUTHLESS-SPEC-02)
CEILING = int(LANDED_BYTES * 1.15)  # future-bloat brake
CONTEXT_FILE_FLOOR = 800
CONTEXT_TOTAL_FLOOR = 4096
PER_BULLET_CHAR_CAP = 600
POINTER_BULLET_THRESHOLD = 250

# --- anti-shrink pin: dual-source with the fixture's own "count" ---
INVARIANT_COUNT = 28  # == inventory["count"] == len(entries); a fixture-only shrink fails against this

# pointer forms accepted on a long AGENTS.md bullet (RUTHLESS-SPEC-01), keyed to
# ruthless's ADR form (ADR-001 / ADR-002, hyphen 3-digit) and its doc homes:
POINTER_RE = re.compile(r"ADR[- ]?\d{3}|docs/adr/|docs/superpowers/|docs/context/|docs/[\w./-]+\.md")
# a symbols[] entry that is ONLY a bare ADR ref is rejected:
BARE_ADR_RE = re.compile(r"^ADR[- ]?\d{3}$")

STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "are",
    "be", "for", "with", "that", "this", "it", "as", "at", "by", "so",
}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")  # utf-8 explicit: 108 non-ASCII bytes


def _bullets(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.lstrip().startswith("- ")]


def test_shim_integrity() -> None:
    lines = [ln for ln in _read(SHIM).splitlines() if ln.strip() and not ln.lstrip().startswith("<!--")]
    assert lines == ["@AGENTS.md"], f"CLAUDE.md must be a pure @AGENTS.md shim; got {lines}"


def test_agents_md_byte_budget() -> None:
    # cut-verification (RUTHLESS-SPEC-02): landed over TARGET => class-2 not fully moved.
    assert LANDED_BYTES <= TARGET, f"LANDED {LANDED_BYTES} B over TARGET {TARGET} B"
    size = AGENTS.stat().st_size
    assert size <= CEILING, f"AGENTS.md {size} B exceeds CEILING {CEILING} B (LANDED x1.15)"


def test_context_conservation_floor() -> None:
    files = sorted(CONTEXT_DIR.glob("*.md"))
    assert files, "no docs/context/*.md present"
    total = 0
    for f in files:
        s = f.stat().st_size
        assert s >= CONTEXT_FILE_FLOOR, f"{f.name} {s} B below floor {CONTEXT_FILE_FLOOR} B (stub?)"
        total += s
    assert total >= CONTEXT_TOTAL_FLOOR, f"context total {total} B below {CONTEXT_TOTAL_FLOOR} B"


def test_per_bullet_char_cap() -> None:
    bullets = _bullets(_read(AGENTS))
    for b in bullets:
        assert len(b) <= PER_BULLET_CHAR_CAP, f"bullet > {PER_BULLET_CHAR_CAP} chars: {b[:80]}"
    # A long bullet must delegate detail to an ADR / docs pointer rather than
    # inline class-2 prose. Short self-contained bullets are exempt.
    for b in bullets:
        if len(b) >= POINTER_BULLET_THRESHOLD:
            assert POINTER_RE.search(b), f"long bullet lacks ADR/docs pointer: {b[:100]}"


def test_inventory_schema_valid() -> None:
    data = json.loads(_read(INVENTORY))
    entries = data["entries"]
    ids = [e["id"] for e in entries]
    assert data["count"] == len(entries) == INVARIANT_COUNT, (
        f"count pin mismatch: json={data['count']} entries={len(entries)} const={INVARIANT_COUNT}"
    )
    assert len(set(ids)) == len(ids), "duplicate invariant ids"
    for e in entries:
        anchor = e["class1_anchor"]
        assert len(anchor) >= 12, f"anchor too short: {anchor!r}"
        tokens = [t for t in re.findall(r"[\w'/.+-]+", anchor.lower()) if t not in STOPWORDS]
        assert len(tokens) >= 2, f"anchor <2 non-stopword tokens: {anchor!r}"
        assert e["symbols"], f"entry has no symbols: {e['id']}"
        for sym in e["symbols"]:
            assert not BARE_ADR_RE.match(sym), f"bare ADR symbol rejected: {sym!r}"
        assert e["home"] == "agents" or e["home"].startswith("context:"), e["home"]


def test_invariant_completeness() -> None:
    """Migration-safety oracle: every class-1 anchor survives in AGENTS.md and
    every distinctive symbol survives in AGENTS.md + context files."""
    data = json.loads(_read(INVENTORY))
    agents_text = _read(AGENTS)
    context_text = "\n".join(_read(f) for f in sorted(CONTEXT_DIR.glob("*.md")))
    haystack = agents_text + "\n" + context_text
    for e in data["entries"]:
        assert e["class1_anchor"] in agents_text, (
            f"class1_anchor missing from AGENTS.md: {e['id']} :: {e['class1_anchor']!r}"
        )
        for sym in e["symbols"]:
            assert sym in haystack, f"symbol dropped (not in AGENTS.md + context): {e['id']} :: {sym!r}"


def test_inventory_grounded_in_snapshot() -> None:
    """RUTHLESS-SPEC-05: the inventory is authored from the real pre-change file.
    Ground on the stable signal (>=1 symbol in the snapshot), not the anchor —
    the anchor is fresh terse phrasing that may not be in the old file."""
    data = json.loads(_read(INVENTORY))
    snap = _read(SNAPSHOT)
    for e in data["entries"]:
        assert any(s in snap for s in e["symbols"]), (
            f"invariant not grounded in snapshot (no symbol present): {e['id']}"
        )
```

- [ ] **Step 2: Run the module RED**

```bash
uv run pytest tests/test_agents_md_budget.py -v
```

Expected: FAILs — `AGENTS.md` and `docs/context/` do not exist yet, so `_IS_SOURCE_CHECKOUT` is **False** and the whole module **skips**. That is not the RED we want. To capture a true RED for the byte/shim/completeness checks, create an **empty placeholder** `AGENTS.md` so the guard flips on, then run:

```bash
: > AGENTS.md   # temporary empty file so _IS_SOURCE_CHECKOUT is True
uv run pytest tests/test_agents_md_budget.py -v
```

Expected now: `test_inventory_schema_valid` and `test_inventory_grounded_in_snapshot` PASS (fixtures exist from Task 1); `test_shim_integrity`, `test_context_conservation_floor`, `test_per_bullet_char_cap`, `test_invariant_completeness` FAIL (CLAUDE.md is still the full file; no context dir; empty AGENTS.md). `test_agents_md_byte_budget` passes trivially on the empty file but is not meaningful yet. Record the failures — they are the RED half of the red→green proof (Task 6). The placeholder `AGENTS.md` is overwritten by the real one in Task 3.

---

## Task 3: `AGENTS.md` class-1 rewrite + `CLAUDE.md` shim

**Files:**
- Create/overwrite: `AGENTS.md`
- Rewrite: `CLAUDE.md` (→ shim)
- Modify: `tests/test_agents_md_budget.py` (pin `LANDED_BYTES`)

**Interfaces:**
- Produces: `AGENTS.md` containing every `class1_anchor` (Task 1) verbatim; `CLAUDE.md` shim.

- [ ] **Step 1: Write `AGENTS.md` (fresh, terse class-1)**

A fresh terse rewrite (not a copy). **Every `class1_anchor` from the inventory MUST appear verbatim** (plain text, no backticks inside the anchor substring); each long Architecture/conventions bullet that delegates detail MUST carry a `docs/context/…` (or `ADR-…`) pointer; keep every bullet ≤ 600 chars. Section-by-section anchor placement (anchors quoted; symbols for `home:"agents"` entries also stay here, symbols for `home:"context:*"` entries move to their context file and are summarised here):

- **Header:** `# ruthless-efficiency`, one-line purpose, and `Ships at 0.6.0 (0.x — API unstable).` plus the one-line release note (bump `ruthless/_version.py`; the `Ships at` line here is the other hand-edit).
- **`## Architecture`** (each bullet ends with `— see docs/context/architecture-rationale.md` where detail moved):
  - hexagonal core — "defines the ports and value types"; keep symbols `Objective`, `SearchStrategy`, `ComputeBackend`, `Candidate`, `Evaluation`, `Result`.
  - "one-way dependency direction" enforced by `import-linter` / `lint-imports` (the `core-isolation` contract); keep those symbols.
  - "each strategy owns its loop" (pointer).
  - backends are the "inter-candidate dispatch path" (pointer).
  - "enforce the per-candidate timeout" for cross-process backends (pointer).
  - "Backends never record a sentinel score" (pointer).
- **`## Key conventions`:**
  - "Scored-metric finiteness only" (`classify_metric`).
  - "Fatal errors vs. penalties are distinct" (`ruthless.errors`, `penalty_metrics`).
  - "Candidate is hashable" (`frozen`, `__hash__`, don't mutate `params`).
  - `Result` is "treat-as-immutable once returned" (`SearchStrategy.run`).
  - "always attempts EVERY unit" for `map_work_units` (pointer to cache-identity file).
  - "Cache identity is a declared EXCLUSION set"; "branch order is load-bearing"; "Digest bytes are a compatibility contract"; "no .md file may quote a digest"; "digests model_dump()" (the pydantic `<3` pin, `conv-pydantic-pin` — keep `pydantic` here, move `model_dump`/`fingerprint_model` detail to the context file); "Provenance never overclaims" — each a one-line kernel with a pointer to `docs/context/cache-identity-and-fingerprint.md` and/or `ADR-002`.
  - `__version__` "lives in ruthless/_version.py" (`hatchling`, `dynamic`).
  - "discriminated-union surface" (`RuthlessConfig`, `FloatRange`, `IntRange`, `Choice`).
  - "Library never configures root logging" (`ruthless._logging.get_logger`).
  - "CLI objective loader is trusted-config-only" (`resolve_objective`, `importlib`, `isinstance`).
- **`## Key Phase-2 conventions`** (pointer to `docs/context/phases-and-scope.md`):
  - "rejects tuning any param not in patch_params" (`CachedObjective`, `evaluate_patch`, `assert_cache_equivalence` move to context).
  - "no lost/dup trials" (`OptunaStrategy` resume; `study.trials`, `SQLite` in context).
  - "raising observer is logged-and-isolated" (`Observer`, `ProgressEvent`, `positional-only` in context).
  - "Group-scoring was deferred" (context).
- **`## Local quality gate`** — keep the 5 commands; the intro line "Run all five before declaring work done" stays verbatim (keep `ruff`, `pyright`, `lint-imports`).
- **`## Workflow conventions`** — "No commit without explicit user approval"; keep `/final-review`, TDD, no `worktrees`.
- **`## Tech stack`** — keep the pins; "pinned for RNG-stream stability" (keep `numpy`, `pydantic`, `pyyaml`).
- **`## Reference docs`** and **`## Architecture decisions`** — keep the spec/plan pointers and the `ADR-001` / `ADR-002` pointers, and **add** the three `docs/context/*.md` files to Reference docs.

- [ ] **Step 2: Write the `CLAUDE.md` shim**

Replace the entire file with exactly (HTML comments, never `#`):

```bash
cat > CLAUDE.md <<'EOF'
<!-- Canonical project instructions live in AGENTS.md (cross-tool convention). -->
<!-- Claude Code auto-loads CLAUDE.md; this shim @-imports AGENTS.md so both resolve to one source. -->
@AGENTS.md
EOF
```

- [ ] **Step 3: Verify every anchor is present in AGENTS.md**

```bash
python - <<'PY'
import json, pathlib
inv = json.loads(pathlib.Path("tests/fixtures/agents_md_invariants.json").read_text(encoding="utf-8"))
agents = pathlib.Path("AGENTS.md").read_text(encoding="utf-8")
missing = [e["id"] for e in inv["entries"] if e["class1_anchor"] not in agents]
print("MISSING ANCHORS:", missing or "none")
PY
```

Must print `none`. If any anchor is missing, edit `AGENTS.md` to include the exact phrase (do **not** edit the inventory to dodge it).

- [ ] **Step 4: Verify per-bullet cap + long-bullet pointers hold**

```bash
: # ensure a context dir exists so completeness/floor can be checked later; for now just the bullet cap:
uv run pytest tests/test_agents_md_budget.py::test_per_bullet_char_cap -v
```

Expected: PASS. If a long bullet fails the pointer check, add a `docs/context/…` or `ADR-…` pointer. If a bullet exceeds 600 chars, split the detail into the context file. **If a genuinely self-contained invariant bullet exceeds 250 chars with no natural pointer and cannot be split without harming the invariant, stop and surface it to the owner** (RUTHLESS-SPEC-02 scope rule) rather than mangling it.

- [ ] **Step 5: Measure and pin `LANDED_BYTES`**

```bash
python -c "import pathlib; print(pathlib.Path('AGENTS.md').stat().st_size)"
```

Set `LANDED_BYTES` in `tests/test_agents_md_budget.py` to that exact number. **It must be ≤ 7680** (TARGET). If it exceeds 7680, first move more class-2 prose to the context files and re-measure; only if the remaining content is all irreducible class-1 invariant text, **raise `TARGET` with a one-line owner-approved note in the test** (never drop an invariant — RUTHLESS-SPEC-02). Then:

```bash
uv run pytest tests/test_agents_md_budget.py::test_agents_md_byte_budget tests/test_agents_md_budget.py::test_shim_integrity -v
```

Expected: PASS.

---

## Task 4: The three context files (verbatim class-2 moves)

**Files:**
- Create: `docs/context/phases-and-scope.md`
- Create: `docs/context/architecture-rationale.md`
- Create: `docs/context/cache-identity-and-fingerprint.md`

**Interfaces:**
- Produces: the three context files; together they must contain every `context:*`-homed symbol from the inventory.

Each file opens with a one-line back-pointer, then holds the **verbatim** class-2 prose cut from `CLAUDE.md` (cut, not paraphrase). Add `##` sub-headings for readability without altering substance.

- [ ] **Step 1: Write `docs/context/architecture-rationale.md`**

Header:

```markdown
# Architecture — rationale

> Class-2 context for the `## Architecture` section of [AGENTS.md](../../AGENTS.md). The enforceable invariants live there; this file holds the why.
```

Paste verbatim the moved rationale from `## Architecture`: the "each strategy owns its loop" / no-`template-method`-driver reasoning (mentioning `report.py`); the inter-candidate dispatch detail (`InProcessBackend`, `BackendPool`, `RemoteObjective`, `RemoteRef`, `local_cuda`, `remote_ssh`, `hf_jobs`); the timeout contract (`document-and-ignore`); the unified error model (`TransientEvaluationError`, `FatalEvaluationError`, `EvolveEvaluator`).

- [ ] **Step 2: Write `docs/context/cache-identity-and-fingerprint.md`**

Header:

```markdown
# Cache identity, fingerprint & provenance — rationale

> Class-2 context for the cache/fingerprint/provenance/version invariants of [AGENTS.md](../../AGENTS.md) and [ADR-002](../adr/ADR-002-cache-identity-and-code-provenance.md). AGENTS.md keeps the terse rules; this file holds the why.
```

Paste verbatim: the full cache-identity exclusion-set prose (`ruthless._fingerprint`, `fingerprint_model`, `_SEED_CACHE_EXCLUDE`, the `_tag` branch-order detail with `Enum`/`IntEnum`/`StrEnum`/`datetime`/`date`, the digest-bytes compatibility-contract prose with `test_fingerprint_golden.py` and `test_docs_no_digest_literals.py`, the "no .md file may quote a digest" enforcement); the provenance prose (`ruthless._provenance`, `code_identity`); the `map_work_units` `WorkUnitMapError` / `BrokenExecutor` / `on_error` taxonomy detail. **Do not quote any 16-hex digest literal** (the digest guard scans this new `.md`; the source has none, so a verbatim move stays clean).

- [ ] **Step 3: Write `docs/context/phases-and-scope.md`**

Header:

```markdown
# Phases & scope — history and rationale

> Class-2 context for the header / `## Key Phase-2 conventions` of [AGENTS.md](../../AGENTS.md). AGENTS.md keeps the current status + invariants; this file holds the phase-by-phase history and the why.
```

Paste verbatim: the intro paragraph's Phase 1A / 1B / 2 narrative; the `## Scope map` detail; and the Phase-2-convention rationale (`CachedObjective` `evaluate_patch` / `patch_params` / `assert_cache_equivalence`; the `OptunaStrategy` resume `study.trials` / `SQLite` semantics; the `Observer` / `ProgressEvent` / `positional-only` observer design; the `Group-scoring was deferred` / `score_fn` note).

- [ ] **Step 4: Verify conservation + completeness**

```bash
uv run pytest tests/test_agents_md_budget.py::test_context_conservation_floor tests/test_agents_md_budget.py::test_invariant_completeness -v
```

Expected: PASS. If `test_invariant_completeness` reports a dropped symbol, that token is neither in `AGENTS.md` nor in a context file — restore it verbatim to the correct context file. Do **not** delete an inventory entry to pass.

---

## Task 5: Reference sweep + pyproject exclude + packaging hard gate

**Files:**
- Modify: `CONTRIBUTING.md` (L78 link)
- Modify: `pyproject.toml` (sdist `exclude`)

- [ ] **Step 1: Re-run the tracked-ref sweep and bucket every hit**

```bash
git grep -l "CLAUDE\.md"
```

Expected: the 14 known files. Confirm the buckets (spec §7): repoint `CONTRIBUTING.md`; update `pyproject.toml`; leave the 12 historical (`CHANGELOG.md`, `docs/adr/ADR-002-…`, `docs/audits/…`, the 8 `docs/superpowers/{specs,plans}/*.md`, and `tests/test_docs_no_digest_literals.py` — whose two CLAUDE.md mentions stay accurate). Confirm no functional `open`:

```bash
git grep -nE "open\([^)]*CLAUDE\.md|Path\([^)]*CLAUDE\.md" -- 'ruthless/**' 'tests/**' 'scripts/**' || echo "no functional CLAUDE.md open — expected"
```

Expected: `no functional CLAUDE.md open`.

- [ ] **Step 2: Repoint the one LIVE ref in `CONTRIBUTING.md`**

Edit line 78 — the conventions link — from `[`CLAUDE.md`](CLAUDE.md)` to `[`AGENTS.md`](AGENTS.md)`. (Behaviour-preserving doc pointer.) Verify:

```bash
grep -n "AGENTS.md" CONTRIBUTING.md
grep -n "CLAUDE.md" CONTRIBUTING.md || echo "no remaining CLAUDE.md ref in CONTRIBUTING.md — expected"
```

- [ ] **Step 3: Update the sdist `exclude` (keep instruction files + context out of the package)**

In `pyproject.toml` under `[tool.hatch.build.targets.sdist]`, extend `exclude` to add `/AGENTS.md` and `/docs/context`, keeping `/CLAUDE.md`:

```toml
exclude = [
    "/.github",
    "/CLAUDE.md",
    "/AGENTS.md",
    "/docs/context",
    "/docs/superpowers",
    "/docs/audits",
]
```

(Preserve the existing explanatory comments; add a short line noting `/AGENTS.md` is the renamed instruction file and `/docs/context` is dev-facing instruction context, both kept out exactly as `/CLAUDE.md` and `/docs/superpowers` are.)

- [ ] **Step 4: Packaging hard gate — build before/after and diff (RUTHLESS-SPEC-04)**

The "before" artifacts were captured at spec time (wheel 45 entries / sdist 210 entries). Rebuild "after" and diff:

```bash
uv build --out-dir "$TMPDIR/pkg_after"
# wheel: must be byte-identical file list to before (only ruthless/** + dist-info)
python - <<'PY'
import glob, zipfile
wh = glob.glob("**/pkg_after/*.whl", recursive=True) or glob.glob("*/pkg_after/*.whl")
z = zipfile.ZipFile(sorted(wh)[0])
names = sorted(n for n in z.namelist())
print("WHEEL entries:", len(names))
bad = [n for n in names if not (n.startswith("ruthless/") or ".dist-info/" in n)]
print("NON-ruthless wheel entries (must be empty except dist-info):", bad)
PY
# sdist: must gain ONLY the 3 new tests/ files; NO AGENTS.md / CLAUDE.md / docs/context
python - <<'PY'
import glob, tarfile
sd = sorted(glob.glob("**/pkg_after/*.tar.gz", recursive=True) or glob.glob("*/pkg_after/*.tar.gz"))[0]
names = [n.split("/", 1)[1] for n in tarfile.open(sd).getnames() if "/" in n]
instr = [n for n in names if n in ("AGENTS.md", "CLAUDE.md") or n.startswith("docs/context")]
print("SDIST entries:", len(names))
print("Instruction files leaked into sdist (must be []):", instr)
print("New tests present:",
      "tests/test_agents_md_budget.py" in names,
      "tests/fixtures/claude_md_at_c2dbecd.md" in names,
      "tests/fixtures/agents_md_invariants.json" in names)
PY
```

Expected: WHEEL non-`ruthless` entries empty (→ wheel unchanged, 45); SDIST instruction leak `[]`, the 3 new tests present (→ 213, delta = tests only). If the wheel list changes at all or any instruction file leaks into the sdist, **stop** — the exclude is wrong. This proves **no version bump** is warranted (spec §8): `ruthless/_version.py` and `CHANGELOG.md` are **not** edited.

---

## Task 6: Red→green proof + full local CI gate

**Files:** none.

- [ ] **Step 1: Confirm the red→green transition**

Task 2 Step 2 captured RED. Now the full module must be green from a real checkout:

```bash
uv run pytest tests/test_agents_md_budget.py -v
```

Expected: all 7 tests PASS (module not skipped — `AGENTS.md` exists).

- [ ] **Step 2: Confirm the skip guard works outside a checkout (RUTHLESS-SPEC-03)**

Build the sdist, unpack it, and run its bundled copy of this module — it must **skip**, not fail:

```bash
uv build --out-dir "$TMPDIR/pkg_skipcheck"
mkdir -p "$TMPDIR/unpacked" && tar xzf "$TMPDIR"/pkg_skipcheck/*.tar.gz -C "$TMPDIR/unpacked"
cd "$TMPDIR"/unpacked/ruthless_efficiency-*/ && uv run --with pytest pytest tests/test_agents_md_budget.py -v; cd -
```

Expected: `7 skipped` (AGENTS.md excluded from the sdist → `_IS_SOURCE_CHECKOUT` False). If any test runs/fails, the guard is wrong. (Also confirm `test_docs_no_digest_literals.py` still passes over the new `.md` files in the checkout.)

- [ ] **Step 3: Run the exact CI check set locally (must all be green)**

```bash
uv run ruff check ruthless tests
uv run ruff format --check ruthless tests
uv run pyright
uv run lint-imports
uv run pytest -v
```

Expected: all green, including the new module and the unchanged `test_docs_no_digest_literals.py`. `pyright` covers `tests`, so the new module must be type-clean; `lint-imports` stays green (stdlib-only test).

---

## Task 7: `/final-review`, then the single commit → push → PR → merge (four owner gates)

**Files:** none created.

- [ ] **Step 1: Run the `/final-review` skill**

Invoke `/final-review` over the full change set (repo rule). It also generates/updates `docs/c4/architecture.html`; this restructure changes **no** architecture, so verify any C4 diff is empty or a legitimate re-render (Graphviz `dot`, not Smetana). Address anything flagged. Re-run Task 6 Step 3 if any file changed.

- [ ] **Step 2: Create the feature branch and stage the change**

```bash
git checkout -b chore/agents-md-restructure
git add AGENTS.md CLAUDE.md \
        docs/context/phases-and-scope.md docs/context/architecture-rationale.md docs/context/cache-identity-and-fingerprint.md \
        tests/test_agents_md_budget.py tests/fixtures/claude_md_at_c2dbecd.md tests/fixtures/agents_md_invariants.json \
        pyproject.toml CONTRIBUTING.md \
        docs/superpowers/specs/2026-09-25-ruthless-agents-md-restructure-design.md \
        docs/superpowers/plans/2026-09-25-ruthless-agents-md-restructure.md
git status
git diff --cached --stat
```

Show the staged file list + diffstat to the owner. **The spec and plan commit here, with the finished code — not earlier.** Confirm `ruthless/_version.py` and `CHANGELOG.md` are **not** staged (no version bump).

- [ ] **Step 3: Commit — OWNER GATE 1**

Stop. Show the diff. Commit **only** on the owner's explicit "commit":

```bash
git commit -m "chore: restructure CLAUDE.md into AGENTS.md + context store with anti-bloat gate

Rename CLAUDE.md -> AGENTS.md (cross-tool convention) behind an @import shim;
move class-2 rationale to docs/context/{phases-and-scope,architecture-rationale,
cache-identity-and-fingerprint}.md; add tests/test_agents_md_budget.py: byte
budget, shim integrity, and a migration-safety oracle (committed snapshot,
28-invariant inventory, dual-source count pin) proving no class-1 invariant was
dropped. Gate skips outside a source checkout so it never reds the published sdist.
pyproject sdist exclude gains /AGENTS.md + /docs/context; wheel unchanged, sdist
gains only the test + fixtures -> no version bump. No behaviour change to ruthless/.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: Push — OWNER GATE 2** (separate; not implied by the commit approval)

```bash
git push -u origin chore/agents-md-restructure
```

- [ ] **Step 5: Open the PR — OWNER GATE 3** (separate)

```bash
gh pr create --title "chore: AGENTS.md restructure + anti-bloat gate" --body "$(cat <<'EOF'
Rename CLAUDE.md → AGENTS.md behind an @import shim; move class-2 to docs/context/
(phases-and-scope, architecture-rationale, cache-identity-and-fingerprint); add the
anti-bloat + migration-safety gate (tests/test_agents_md_budget.py), which skips
outside a source checkout so it never reds the published sdist.

Packaging: wheel byte-identical; sdist gains only the test + 2 fixtures (no
instruction files); pyproject sdist exclude adds /AGENTS.md + /docs/context. No
version bump. No behaviour change to shipped ruthless/ code.

Spec: docs/superpowers/specs/2026-09-25-ruthless-agents-md-restructure-design.md
Plan: docs/superpowers/plans/2026-09-25-ruthless-agents-md-restructure.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Merge — OWNER GATE 4** (separate; after CI green)

Wait for CI green on the PR (note: `main` has no branch protection — a red job does not block, so read the checks explicitly), then on the owner's explicit "merge":

```bash
gh pr merge --squash
```

(`--admin` is omitted deliberately (PLAN-03): with no branch protection it bypasses nothing, and plain `--squash` after reading the checks is cleaner.)

---

## Self-review (plan vs spec)

- **Spec coverage:** §1 summary → Tasks 3/4; §2 measured state → Task 1 grounding + Task 5 sweep; §4.1 shim → Task 3 Step 2 + `test_shim_integrity`; §4.2 three context files → Task 4; §4.3 AGENTS.md content → Task 3 Step 1; §5 inventory (schema, ≥1-symbol, ADR-reject, `INVARIANT_COUNT` dual pin) → Task 1 + `test_inventory_schema_valid`; §6.1 snapshot oracle → Task 1 + `SNAPSHOT`; §6.2 checks 1–7 → Task 2; §6.3 source-checkout skip guard → Task 2 (`pytestmark`) + Task 6 Step 2; §7 sweep (3 buckets: 1 repoint, 1 update, 12 leave) → Task 5 Steps 1–3; §8 packaging hard gate + no bump → Task 5 Step 4; RUTHLESS-SPEC-05 grounding → Task 1 Step 3 + `test_inventory_grounded_in_snapshot`; §9 scope/verbatim/zero-drop → Global Constraints + Task 4; §10 local=CI (5 checks) → Task 6 Step 3; §11 four-gate commit discipline + C4 → Task 7. No spec requirement is unimplemented.
- **Placeholder scan:** `LANDED_BYTES = 6800` is the one deliberately-provisional value; Task 3 Step 5 pins it to a measured number with an explicit ≤ 7680 gate and a raise-with-owner-note escape (never a silent TODO). The inventory JSON, test module, shim, and pyproject edit are concrete. No "TBD"/"similar to"/"add error handling".
- **Type/name consistency:** `INVARIANT_COUNT = 28 == count == len(entries)`; `POINTER_RE`/`BARE_ADR_RE` match spec §5/§6.2 (ruthless `ADR-\d{3}` form); fixture paths (`claude_md_at_c2dbecd.md`, `agents_md_invariants.json`) identical across Tasks 1/2/7; snapshot filename identical in the module (`SNAPSHOT`) and Task 1; `test_*` names stable across Tasks 2/3/4/6; context filenames identical across the File-structure table, Task 4, and the commit message.
- **RED-capture nuance:** because the skip guard would mask the RED, Task 2 Step 2 creates a temporary empty `AGENTS.md` to flip `_IS_SOURCE_CHECKOUT` on and observe the genuine failures; Task 3 overwrites it. Documented, not a placeholder.
```