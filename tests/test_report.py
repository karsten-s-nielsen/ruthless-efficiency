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
