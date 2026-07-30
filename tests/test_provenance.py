"""Tests for code-identity capture (spec §4.3).

The load-bearing property is NEGATIVE: a bare SHA from a dirty or unknown tree is verifiable-looking
FALSE provenance, which is strictly worse than recording nothing. So `ruthless_git_state` must never
degrade to "clean", and `ruthless_git_commit` must never appear without a state."""

import shutil
import subprocess
from pathlib import Path

import pytest

from ruthless import _provenance
from ruthless._provenance import _repo_tracks_module, code_identity

# `_provenance` treats absent git as a supported state ("unknown"), so the tests that need a real repo
# skip rather than fail — otherwise the suite would be stricter about git than the module under test.
_GIT = shutil.which("git")


def _require_git() -> None:
    if _GIT is None:
        pytest.skip("git not on PATH; code_identity() treats that as the supported 'unknown' state")


def _git(*args: str, cwd) -> None:
    # Suppressions justified: fixed argv, no shell, and `git` from PATH is what a test fixture wants.
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603, S607


@pytest.fixture
def clean_repo(tmp_path):
    _require_git()
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "t@example.com", cwd=tmp_path)
    _git("config", "user.name", "T", cwd=tmp_path)
    (tmp_path / "f.txt").write_text("hello")
    _git("add", "f.txt", cwd=tmp_path)
    _git("commit", "-m", "init", cwd=tmp_path)
    return tmp_path


def test_clean_repo_reports_clean_and_a_sha(clean_repo):
    ident = code_identity(repo_root=clean_repo)
    assert ident["ruthless_git_state"] == "clean"
    assert isinstance(ident["ruthless_git_commit"], str)
    assert len(ident["ruthless_git_commit"]) == 40


def test_modified_tracked_file_reports_dirty(clean_repo):
    (clean_repo / "f.txt").write_text("changed")
    assert code_identity(repo_root=clean_repo)["ruthless_git_state"] == "dirty"


def test_untracked_file_reports_dirty(clean_repo):
    """`git status --porcelain`, not `git diff --quiet` - the latter misses untracked files."""
    (clean_repo / "new.txt").write_text("x")
    assert code_identity(repo_root=clean_repo)["ruthless_git_state"] == "dirty"


def test_non_repo_reports_unknown_and_never_clean(tmp_path):
    ident = code_identity(repo_root=tmp_path)
    assert ident["ruthless_git_state"] == "unknown"
    assert ident["ruthless_git_commit"] is None


def test_version_is_always_present(tmp_path):
    from ruthless import __version__

    assert code_identity(repo_root=tmp_path)["ruthless_version"] == __version__


def test_a_sha_never_appears_without_a_state(clean_repo, tmp_path):
    for root in (clean_repo, tmp_path):
        ident = code_identity(repo_root=root)
        assert "ruthless_git_state" in ident
        if ident["ruthless_git_commit"] is not None:
            assert ident["ruthless_git_state"] in {"clean", "dirty"}


# --- P1 regression: the failing configuration is "installed INSIDE a repo that is not ruthless's" ---


def _repo_with_module(root, module_rel: str, *, track: bool, gitignore: str = "") -> Path:
    """Build a git repo at `root` containing `module_rel`, tracked or not. Returns the module path."""
    _require_git()
    module = root / module_rel
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text("# _provenance\n")
    _git("init", cwd=root)
    _git("config", "user.email", "t@example.com", cwd=root)
    _git("config", "user.name", "T", cwd=root)
    if gitignore:
        (root / ".gitignore").write_text(gitignore)
        _git("add", ".gitignore", cwd=root)
    (root / "README.md").write_text("x\n")
    _git("add", "README.md", cwd=root)
    if track:
        _git("add", "-f", module_rel, cwd=root)
    _git("commit", "-m", "init", cwd=root)
    return module.resolve()


def test_repo_tracks_module_accepts_a_flat_source_checkout(tmp_path):
    module = _repo_with_module(tmp_path, "ruthless/_provenance.py", track=True)
    assert _repo_tracks_module(module) is True


def test_repo_tracks_module_accepts_a_src_layout_checkout(tmp_path):
    """Layout-agnostic by construction. A path comparison against a hardcoded `ruthless/<name>` would
    reject this LEGITIMATE checkout and silently degrade provenance to 'unknown' everywhere."""
    module = _repo_with_module(tmp_path, "src/ruthless/_provenance.py", track=True)
    assert _repo_tracks_module(module) is True


def test_repo_tracks_module_rejects_an_untracked_copy_inside_another_repo(tmp_path):
    """THE measured P1 layout: a wheel in a project-local venv sits inside the CONSUMER's repo, so a bare
    `git rev-parse` succeeds there and returns THEIR commit. Gitignoring the venv does not help."""
    module = _repo_with_module(
        tmp_path, ".venv/Lib/site-packages/ruthless/_provenance.py", track=False, gitignore=".venv/\n"
    )
    assert _repo_tracks_module(module) is False


def test_repo_tracks_module_rejects_a_non_repo(tmp_path):
    module = tmp_path / "ruthless" / "_provenance.py"
    module.parent.mkdir(parents=True)
    module.write_text("")
    assert _repo_tracks_module(module.resolve()) is False


def test_repo_tracks_module_is_cached_per_path(tmp_path, monkeypatch):
    """Whether a repo tracks a given source file is static for the life of a process, so the ls-files
    probe is cached — one fewer git subprocess per `run()`. Cached on the ARGUMENT, so the test seam
    (`repo_root=`) and differing module paths keep their own entries."""
    _repo_tracks_module.cache_clear()
    module = _repo_with_module(tmp_path, "ruthless/_provenance.py", track=True)
    seen: list[str] = []
    real = _provenance._run_git

    def counting(args, root):
        seen.append(args[0])
        return real(args, root)

    monkeypatch.setattr(_provenance, "_run_git", counting)
    assert _repo_tracks_module(module) is True
    assert _repo_tracks_module(module) is True
    assert seen.count("ls-files") == 1, f"ls-files ran {seen.count('ls-files')}x; expected 1 (cached)"


def test_tree_state_is_not_cached(clean_repo):
    """Guards against over-caching. The tracking probe is cached; the tree STATE must not be, or a run
    started clean and finished dirty would keep reporting clean."""
    assert code_identity(repo_root=clean_repo)["ruthless_git_state"] == "clean"
    (clean_repo / "new.txt").write_text("x")
    assert code_identity(repo_root=clean_repo)["ruthless_git_state"] == "dirty"


def test_code_identity_reports_unknown_when_the_module_is_not_tracked(clean_repo, monkeypatch):
    """Integration guard for P1, through the real auto-discovery path. Point `_MODULE` at an 'installed'
    copy inside `clean_repo` — a repo with a perfectly good HEAD — and assert the no-argument call refuses
    to claim that repo's commit as ruthless's. Also covers the case a failed git lookup takes."""
    installed = clean_repo / ".venv" / "Lib" / "site-packages" / "ruthless" / "_provenance.py"
    installed.parent.mkdir(parents=True)
    installed.write_text("")
    monkeypatch.setattr(_provenance, "_MODULE", installed.resolve())
    ident = code_identity()
    assert ident["ruthless_git_commit"] is None
    assert ident["ruthless_git_state"] == "unknown"
    assert ident["ruthless_version"]  # version is the identity in this case
