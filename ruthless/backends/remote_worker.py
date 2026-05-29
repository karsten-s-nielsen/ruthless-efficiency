"""Generic remote worker — runs a candidate evaluation on a compute node and prints JSON metrics.

Invoked on the node by RemoteSSHBackend::

    python -m ruthless.backends.remote_worker candidate.json cuda:0 5 42 my_pkg.objectives:train_and_evaluate

It loads the candidate config from a JSON file, imports the entrypoint (`module:callable`), runs the
standard `train_and_evaluate(candidate_config, device, epochs, seed, program_path)`, and writes the
resulting metrics dict as a single JSON line to stdout. All other output (logs, warnings) goes to
stderr so it does not interfere with JSON parsing on the caller side.

H1 boundary: the worker runs on the node and cannot raise across the wire, so on an objective crash
it emits a `{combined_score:0, error:1, _error_text}` marker — the single cross-wire failure signal.
The calling backend detects it (`base.is_objective_failure`) and converts it into a FatalEvaluationError.
The worker never decides scoring; it only reports."""

from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import traceback
from typing import Any

from ruthless.wire import ERROR_TEXT_KEY, worst_score_metrics

_log = logging.getLogger(__name__)


def _load_hf_token_from_file() -> None:
    """If ``HF_TOKEN_FILE`` is set (the backend passed the token by file, not on the command line),
    read it into ``HF_TOKEN`` for the objective entrypoint and unlink the file (one-time use)."""
    token_file = os.environ.get("HF_TOKEN_FILE")
    if not token_file or os.environ.get("HF_TOKEN"):
        return
    try:
        with open(token_file) as fh:
            os.environ["HF_TOKEN"] = fh.read().strip()
        os.unlink(token_file)
    except OSError:
        _log.warning("hf_token_file_unreadable")


def _load_candidate_config(candidate_path: str) -> dict[str, Any]:
    with open(candidate_path) as f:
        config: dict[str, Any] = json.load(f)
    return config


def _resolve(entrypoint: str):
    module_path, _, attr = entrypoint.partition(":")
    if not attr:
        raise ValueError(f"entrypoint must be 'module:callable', got {entrypoint!r}")
    return getattr(importlib.import_module(module_path), attr)


def main() -> None:
    if len(sys.argv) < 6:
        msg = (
            "Usage: python -m ruthless.backends.remote_worker <candidate.json> <device> <epochs> <seed> "
            "<module:callable> [--program program.py]"
        )
        print(msg, file=sys.stderr)
        sys.exit(1)

    candidate_path = sys.argv[1]
    device = sys.argv[2]
    epochs = int(sys.argv[3])
    seed = int(sys.argv[4])
    entrypoint = sys.argv[5]

    program_path: str | None = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--program" and i + 1 < len(sys.argv):
            program_path = sys.argv[i + 1]
            break

    # Redirect logging to stderr so stdout stays clean for JSON output.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(message)s")

    _load_hf_token_from_file()  # if the backend passed HF_TOKEN by file rather than inline

    _log.info("Loading candidate config from %s", candidate_path)
    config = _load_candidate_config(candidate_path)

    _log.info("Running %s (device=%s, epochs=%d, seed=%d)", entrypoint, device, epochs, seed)
    fn = _resolve(entrypoint)
    try:
        metrics: dict[str, Any] = fn(
            candidate_config=config,
            device=device,
            epochs=epochs,
            seed=seed,
            program_path=program_path,
        )
    except Exception:  # noqa: BLE001 - on the node we cannot raise across the wire; emit the failure marker
        _log.exception("Remote worker evaluation failed")
        metrics = {**worst_score_metrics(), ERROR_TEXT_KEY: traceback.format_exc()}

    # Single JSON line to stdout — the calling backend parses this.
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
