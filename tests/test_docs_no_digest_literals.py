"""Guard: no `.md` file in this repository may quote a `fingerprint` digest literal.

WHY THIS EXISTS. `tests/test_fingerprint_golden.py` is the single source of truth for pinned digest
bytes (see `ruthless.fingerprint`'s stability contract and ADR-002). A digest sitting loose in prose
is a hazard in one specific direction: a later reader lifts it back into the golden table on the
assumption it had already been checked, and the table then pins a documented value rather than what
the algorithm actually produces. Docs also drift silently — nothing re-runs a spec.

WHY IT IS A TEST AND NOT A SENTENCE. The rule was written into `CLAUDE.md` before this file existed.
A rule enforced only by whoever happens to be editing is the same failure mode that let 0.3.1 ship a
false "purely additive" claim, so it is enforced here instead. This mirrors the move the 0.4.0
release makes everywhere else: pin it, do not assert it in prose.

THE REGEX, AND THE FALSE-POSITIVE TRAP IT EXISTS TO AVOID
---------------------------------------------------------
A naive `\\b[0-9a-f]{16}\\b` is WRONG. `README.md`'s quick-start output line is

    {'x': 2.9969320310963994} {'loss': 9.412433193460362e-06}

and the naive pattern matches twice inside it: `9969320310963994` (the 16 digits of the mantissa of
`2.9969320310963994`) and `412433193460362e` (15 digits plus the exponent marker of
`9.412433193460362e-06`). `\\b` does not help, because `.` is itself a non-word character and so a
digit run after a decimal point starts on a word boundary. A guard that flags the README's own
worked example is a guard the next person deletes, which is why both strings are pinned as
regression cases in `test_regex_ignores_the_readme_float_and_exponent_forms`.

The lookarounds are the fix: a hex run that is preceded or followed by a word character OR a dot is
part of a longer token (a number, an identifier, a filename) and is not a digest. Digests in this
repo's docs appear inside backticks or code fences, neither of which is `[\\w.]`.

WHAT THIS DOES NOT CATCH — stated so nobody reads it as total coverage:
  * `fingerprint(..., length=N)` for N != 16. The default is 16 and every digest in this repo uses
    it, so this is a strong guard, not a complete one.
  * A bare (un-backticked) digest ending a sentence, e.g. `... is 0123456789abcdef.` — the trailing
    dot suppresses the match. Blocking that would re-admit filename-shaped false positives; the
    repo's convention of backticking digests keeps the real cases inside the guard.
  * Anything under `_SKIP_DIRS`.

This is a repository-hygiene test: it needs the source tree, not an installed package. It uses only
the standard library and pytest, so it runs in the lean `core-lean` / `core-lean-windows` CI legs.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

# Repo root from THIS FILE, never `os.getcwd()` — the test must give the same answer whichever
# directory pytest was invoked from.
_REPO_ROOT = Path(__file__).resolve().parents[1]

# The published sdist ships `tests/` but NOT `/docs/superpowers` or `/CLAUDE.md` — see the `exclude`
# list under `[tool.hatch.build.targets.sdist]`. Every current entry in `_ALLOWED_DIGEST_LITERALS`
# lives under that excluded tree, so in an unpacked sdist the file is absent for a PACKAGING reason
# rather than a stale one, and `test_every_exclusion_is_still_present` would fail on a decision that is
# working as intended. Measured before this gate existed: the 0.4.0 sdist ran 1 failed / 181 passed
# with this test the only failure — a red suite inside a published artifact, which downstream
# packagers (Debian, conda-forge, Nix) do run as a build-time check.
#
# `CLAUDE.md` is the marker because it is on that same sdist `exclude` list, so "absent" means exactly
# "not a source checkout" rather than anything about this test's subject. The gate costs nothing where
# it matters: CI and the local quality gate both run from a checkout, so the staleness check is always
# live there, and a skip is visible in `pytest -v`.
_IS_SOURCE_CHECKOUT = (_REPO_ROOT / "CLAUDE.md").is_file()

# Directories never scanned. Everything here is either not ours (`.venv`, `node_modules`), not
# content (`.git`, tool caches, build output), or deliberately a place where digests belong:
# `.superpowers/` holds gitignored per-task agent reports whose whole job is to record measured
# output, digests included. Those are working notes, not repository documentation, and are never
# published or read as a spec — the lifting hazard this guard exists for does not apply to them.
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        ".superpowers",
        ".claude",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".import_linter_cache",
        "__pycache__",
        "build",
        "dist",
    }
)

# See the module docstring for why the lookarounds are load-bearing. Do not "simplify" to `\b`.
_DIGEST_RE = re.compile(r"(?<![\w.])[0-9a-f]{16}(?![\w.])")


# Known-historical digest literals, keyed on (repo-relative POSIX path, digest value) so that adding
# a NEW literal to an already-listed file still fails. Fail-closed and declared, exactly like
# `fingerprint_model(exclude=...)` and evolve's `_SEED_CACHE_EXCLUDE`: every entry carries the reason
# it is safe, and `test_every_exclusion_is_still_present` fails on a stale one rather than letting it
# sit there doing nothing.
#
# The one entry below lives in the completed decision record for the work-unit error model and cache
# identity. It is EVIDENCE INSIDE THAT RECORD'S ARGUMENT — the measured collision that justified tagging
# mapping keys — and it is a REJECTED-algorithm value, so it is inert: no shipped `_tag` can produce it.
# That inertness is the whole basis of the exemption. The record's other two digests were
# current-algorithm values and therefore exactly the liftable kind this guard exists to stop; they were
# paraphrased out of the spec rather than exempted, and its argument survives intact without them.
_SPEC_2026_07_29 = "docs/superpowers/specs/2026-07-29-parallel-error-model-and-cache-identity.md"

_ALLOWED_DIGEST_LITERALS: frozenset[tuple[str, str]] = frozenset(
    {
        # REJECTED-ALGORITHM value (§0.3 and §2.3.1). The digest of BOTH `{"cfg": {1: "x"}}` and
        # `{"cfg": {"1": "x"}}` under the spec's rev-1 `_tag`, which stringified mapping keys instead of
        # tagging them. That is the measured collision (F1) the fix exists to close, so no shipped
        # version of `_tag` can produce it — today those two payloads digest differently. Unambiguously
        # historical: lifting it into the golden table would fail the table's own assertion immediately.
        (_SPEC_2026_07_29, "61d5e46087f14893"),
    }
)


_FOUND_MESSAGE = """
Digest literal(s) found in Markdown:

{found}

`tests/test_fingerprint_golden.py` is the SINGLE SOURCE OF TRUTH for pinned digest bytes, and no
`.md` file may quote one — see the stability contract on `ruthless.fingerprint` and ADR-002.

A digest in prose drifts silently (nothing re-runs a spec) and, worse, invites a later reader to lift
it into the golden table on the assumption it had already been checked. That would pin a documented
value instead of the algorithm's actual output, which is the one thing the table exists to prevent.

FIX by deleting the literal, or by describing the digest rather than quoting it ("the two digests
differ", "byte-identical to 0.3.1"). Add an entry to `_ALLOWED_DIGEST_LITERALS` only for a value that
is evidence inside a COMPLETED decision record, with a comment saying which situation it is and why
it cannot be mistaken for a current pinned byte.
"""


def _markdown_files() -> list[Path]:
    """Every `.md` file under the repo root, pruned by `_SKIP_DIRS`. Includes untracked files: a
    digest is just as liftable before it is committed, and `git` is not a dependency here."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(_REPO_ROOT):  # followlinks=False → no symlink loops
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for name in sorted(filenames):
            if name.lower().endswith(".md"):
                found.append(Path(dirpath) / name)
    return found


def _relative_posix(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def _scan() -> list[tuple[str, int, str]]:
    """All digest-shaped literals as (repo-relative posix path, 1-based line number, value)."""
    hits: list[tuple[str, int, str]] = []
    for path in _markdown_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _DIGEST_RE.finditer(line):
                hits.append((_relative_posix(path), lineno, match.group(0)))
    return hits


def test_no_markdown_file_quotes_a_digest_literal() -> None:
    offenders = [hit for hit in _scan() if (hit[0], hit[2]) not in _ALLOWED_DIGEST_LITERALS]
    found = "\n".join(f"  {path}:{lineno}: {value}" for path, lineno, value in offenders)
    assert not offenders, _FOUND_MESSAGE.format(found=found)


@pytest.mark.parametrize(
    "text",
    [
        "{'x': 2.9969320310963994} {'loss': 9.412433193460362e-06}",
        "2.9969320310963994",  # mantissa is 16 digits: `9969320310963994`
        "9.412433193460362e-06",  # 15 digits + the exponent marker: `412433193460362e`
    ],
)
def test_regex_ignores_the_readme_float_and_exponent_forms(text: str) -> None:
    """Regression pins for the false positives a naive `\\b[0-9a-f]{16}\\b` produces on README.md's
    quick-start output. If a future "simplification" of `_DIGEST_RE` drops the lookarounds, this
    fails loudly instead of the guard being deleted for crying wolf."""
    assert _DIGEST_RE.findall(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "`0123456789abcdef`",  # the repo's convention: digests are backticked
        "0123456789abcdef",
        "case-name: 0123456789abcdef",
        "  0123456789abcdef  COLLIDE",  # code-fence style, as in the historical spec
    ],
)
def test_regex_matches_a_genuine_digest(text: str) -> None:
    """The other half of the trade-off: the lookarounds must not have narrowed the pattern to the
    point of catching nothing. The value here is synthetic, never a pinned byte."""
    assert _DIGEST_RE.findall(text) == ["0123456789abcdef"]


@pytest.mark.skipif(
    not _IS_SOURCE_CHECKOUT,
    reason="not a source checkout — the sdist excludes /docs/superpowers, where the exclusions live",
)
@pytest.mark.parametrize(("relative_path", "digest"), sorted(_ALLOWED_DIGEST_LITERALS))
def test_every_exclusion_is_still_present(relative_path: str, digest: str) -> None:
    """A stale exclusion silently exempts nothing and misleads the next reader into thinking the file
    still contains it. `fingerprint_model` raises on an exclusion naming a non-existent field for the
    same reason; this mirrors that.

    Source-checkout only — see `_IS_SOURCE_CHECKOUT`. The files an exclusion names are dev docs the
    sdist deliberately drops, so outside a checkout their absence proves nothing about staleness."""
    path = _REPO_ROOT / relative_path
    assert path.is_file(), f"_ALLOWED_DIGEST_LITERALS names a missing file: {relative_path}"
    assert digest in _DIGEST_RE.findall(path.read_text(encoding="utf-8")), (
        f"_ALLOWED_DIGEST_LITERALS exempts {digest!r} in {relative_path}, but that value is no longer "
        f"there. Delete the entry — a stale exclusion exempts nothing and misleads."
    )
