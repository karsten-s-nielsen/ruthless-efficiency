import json

from ruthless.report import render_json, render_summary_md
from ruthless.result import Candidate, Evaluation, Result


def _result():
    best = Evaluation(Candidate("r7", {"x": 3.01}), {"loss": 0.0001}, ok=True)
    return Result(
        best=best,
        history=[best],
        diagnostics={"n_trials": 200},
        provenance={"strategy": "random", "seed": 42},
    )


def test_render_json_roundtrips():
    p = json.loads(render_json(_result()))
    assert p["best"]["candidate"]["params"]["x"] == 3.01 and p["provenance"]["seed"] == 42 and p["n_history"] == 1


def test_render_summary_md():
    md = render_summary_md(_result())
    assert md.startswith("# ") and "0.0001" in md and "random" in md


def test_summary_md_renders_provenance_one_key_per_line():
    """spec §8.1: a growing one-line dict repr buries `ruthless_git_state`, which is precisely the field
    that must not be buried (a SHA with no state is false provenance). Hyrum's Law is satisfied because
    report.py's own docstring already directs machine consumers to render_json."""
    result = Result(
        best=None,
        history=[],
        provenance={"strategy": "random", "ruthless_git_commit": "a" * 40, "ruthless_git_state": "dirty"},
    )
    md = render_summary_md(result)
    assert "- ruthless_git_state: dirty" in md
    assert f"- ruthless_git_commit: {'a' * 40}" in md
    assert "{'strategy'" not in md  # no bare dict repr


def test_render_json_still_serialises_provenance_as_a_dict():
    """The machine-readable surface is UNCHANGED - that is what makes the Markdown reformat safe."""
    result = Result(best=None, history=[], provenance={"strategy": "random", "ruthless_git_state": "clean"})
    assert json.loads(render_json(result))["provenance"] == {
        "strategy": "random",
        "ruthless_git_state": "clean",
    }


def test_summary_md_handles_empty_provenance():
    assert "- (none)" in render_summary_md(Result(best=None, history=[]))
