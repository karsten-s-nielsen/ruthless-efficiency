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
red a published artifact -- the exact failure tests/test_docs_no_digest_literals.py
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
    reason="not a source checkout - the sdist excludes AGENTS.md / docs/context (see pyproject sdist exclude)",
)

# --- byte budgets (bytes on disk, never len(text)) ---
ORIGINAL_BYTES = 14640  # pinned: CLAUDE.md @ c2dbecd
LANDED_BYTES = 7262  # measured AGENTS.md size on disk at migration (Task 3 Step 5)
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
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "and",
    "or",
    "is",
    "are",
    "be",
    "for",
    "with",
    "that",
    "this",
    "it",
    "as",
    "at",
    "by",
    "so",
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
    Ground on the stable signal (>=1 symbol in the snapshot), not the anchor --
    the anchor is fresh terse phrasing that may not be in the old file."""
    data = json.loads(_read(INVENTORY))
    snap = _read(SNAPSHOT)
    for e in data["entries"]:
        assert any(s in snap for s in e["symbols"]), (
            f"invariant not grounded in snapshot (no symbol present): {e['id']}"
        )
