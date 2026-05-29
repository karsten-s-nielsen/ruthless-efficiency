import json
import os
import sys
import types

from ruthless.backends import remote_worker


def _write_candidate(tmp_path, cfg):
    p = tmp_path / "candidate.json"
    p.write_text(json.dumps(cfg))
    return str(p)


def test_remote_worker_success(tmp_path, monkeypatch, capsys):
    def train_and_evaluate(*, candidate_config, device, epochs, seed, program_path):
        return {"combined_score": candidate_config["x"] + epochs}

    monkeypatch.setitem(sys.modules, "ep_ok", types.SimpleNamespace(train_and_evaluate=train_and_evaluate))

    cpath = _write_candidate(tmp_path, {"x": 1.0})
    monkeypatch.setattr(sys, "argv", ["prog", cpath, "cpu", "5", "42", "ep_ok:train_and_evaluate"])
    remote_worker.main()
    out = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(out) == {"combined_score": 6.0}


def test_remote_worker_captures_objective_crash(tmp_path, monkeypatch, capsys):
    def train_and_evaluate(**kw):
        raise RuntimeError("boom")

    monkeypatch.setitem(sys.modules, "ep_boom", types.SimpleNamespace(train_and_evaluate=train_and_evaluate))

    cpath = _write_candidate(tmp_path, {"x": 1.0})
    monkeypatch.setattr(sys, "argv", ["prog", cpath, "cpu", "5", "42", "ep_boom:train_and_evaluate"])
    remote_worker.main()
    out = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(out)
    assert payload["combined_score"] == 0.0 and payload["error"] == 1.0 and "_error_text" in payload


def test_remote_worker_reads_hf_token_file(tmp_path, monkeypatch, capsys):
    token_file = tmp_path / "tok"
    token_file.write_text("filetoken")
    seen: dict = {}

    def train_and_evaluate(*, candidate_config, device, epochs, seed, program_path):
        seen["token"] = os.environ.get("HF_TOKEN")
        return {"combined_score": 1.0}

    monkeypatch.setitem(sys.modules, "ep_tok", types.SimpleNamespace(train_and_evaluate=train_and_evaluate))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("HF_TOKEN_FILE", str(token_file))
    cpath = _write_candidate(tmp_path, {"x": 1.0})
    monkeypatch.setattr(sys, "argv", ["prog", cpath, "cpu", "5", "42", "ep_tok:train_and_evaluate"])
    remote_worker.main()
    assert seen["token"] == "filetoken"  # noqa: S105 - test value, not a real secret
    assert not token_file.exists()  # one-time use: the secret file is removed after reading
