"""Private core code-identity capture for `Result.provenance`.

THE TRAP THIS EXISTS TO AVOID: `git rev-parse HEAD` returns the same SHA whether or not the working tree
is modified, so a bare SHA stamped on an artifact built from a dirty tree is verifiable-looking FALSE
provenance - strictly worse than recording nothing. Therefore a commit is NEVER reported without a state,
and a missing/failing git NEVER degrades to "clean".

Scope: this identifies RUTHLESS's own tree, not the consumer's objective code - hence the `ruthless_`
key prefix, so a reader cannot mistake it for full run provenance.

The repo is resolved from this file's location AND the enclosing repo must be proved to TRACK this module
as source (`_repo_tracks_module`). The containment check is not belt-and-braces, it is load-bearing: a
wheel installed into a project-local venv lives at `<consumer-repo>/.venv/Lib/site-packages/ruthless/`,
which is INSIDE the consumer's repo, so a bare `git rev-parse HEAD` from here returns THEIR commit
(measured). Being gitignored does not help - git walks up for `.git` and never consults ignore rules.
Without the check, this module would stamp a consumer's SHA under a key whose prefix asserts it is
ruthless's: exactly the verifiable-looking false provenance the paragraph above exists to prevent.

Expected and correct: a wheel install reports "unknown", with `ruthless_version` carrying the identity. A
source checkout and a `pip install -e` both report a real SHA + state."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from ruthless._logging import get_logger
from ruthless._version import __version__

_log = get_logger("provenance")
_TIMEOUT_S = 5

_MODULE = Path(__file__).resolve()


def _run_git(args: list[str], repo_root: Path) -> str | None:
    """Stdout of `git <args>` in `repo_root`, or None on ANY failure (absent git, non-repo, timeout)."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        proc = subprocess.run(  # noqa: S603 - `git` resolved via shutil.which; args are literals
            [git, *args], cwd=repo_root, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _repo_tracks_module(module_file: Path) -> bool:
    """True only if the enclosing git repo TRACKS `module_file` as source.

    Separates "ruthless's own checkout" (including `pip install -e`, where `__file__` still points at the
    source) from "somebody's venv that happens to sit inside their repo". See the module docstring for the
    measured failure this prevents.

    Asking git rather than comparing paths keeps this layout-agnostic - a `src/` layout would break a
    path comparison against a hardcoded package-relative path, in a LEGITIMATE checkout. It also subsumes
    the "is there a repo at all" question, so one git call answers both."""
    return _run_git(["ls-files", "--error-unmatch", str(module_file)], module_file.parent) is not None


def code_identity(*, repo_root: Path | None = None) -> dict[str, Any]:
    """Ruthless's own code identity, for merging into `Result.provenance`.

    Returns `ruthless_version`, `ruthless_git_commit` (40-char SHA or None) and `ruthless_git_state`
    ("clean" | "dirty" | "unknown"). "unknown" means the tree could not be established and is as
    untrustworthy as "dirty" - it never means clean."""
    ident: dict[str, Any] = {
        "ruthless_version": __version__,
        "ruthless_git_commit": None,
        "ruthless_git_state": "unknown",
    }
    root = repo_root if repo_root is not None else _MODULE.parent
    # An explicit repo_root is a trusted test seam; auto-discovery is not, so it must prove the repo it
    # landed in actually holds ruthless's SOURCE and is not a consumer repo containing an installed copy.
    if repo_root is None and not _repo_tracks_module(_MODULE):
        return ident
    sha = _run_git(["rev-parse", "HEAD"], root)
    if sha is None:
        return ident
    status = _run_git(["status", "--porcelain"], root)  # --porcelain, so untracked files count as dirty
    if status is None:
        _log.warning("provenance_state_unknown", extra={"repo_root": str(root)})
        return ident
    ident["ruthless_git_commit"] = sha.strip()
    ident["ruthless_git_state"] = "dirty" if status.strip() else "clean"
    return ident
