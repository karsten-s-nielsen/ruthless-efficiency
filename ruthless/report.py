"""Standardized rendering of a Result → machine JSON + human Markdown SUMMARY. Strategy-specific
artifacts (checkpoint dirs, best_program.py) stay strategy-owned (spec L5)."""

from __future__ import annotations

import json

from ruthless.result import Evaluation, Result


def _eval_dict(ev: Evaluation) -> dict:
    return {
        "candidate": {"id": ev.candidate.id, "params": dict(ev.candidate.params)},
        "metrics": ev.metrics,
        "ok": ev.ok,
    }


def render_json(result: Result) -> str:
    """Serialize a ``Result`` to a 2-space-indented JSON **string** (machine-readable).

    Includes the best evaluation (or ``null``), the history length, diagnostics, and provenance.
    Non-JSON values are stringified (``default=str``). Returns a string, not a dict."""
    return json.dumps(
        {
            "best": _eval_dict(result.best) if result.best else None,
            "n_history": len(result.history),
            "diagnostics": result.diagnostics,
            "provenance": result.provenance,
        },
        indent=2,
        default=str,
    )


def render_summary_md(result: Result) -> str:
    """Render a ``Result`` as a human-readable Markdown summary **string**.

    Produces a top-level heading plus the best metrics/params (when present), the trial count, and
    provenance. For the full machine-readable surface use :func:`render_json`."""
    lines = ["# Ruthless Efficiency — Run Summary", ""]
    if result.best:
        lines += [
            f"**Best metrics:** `{result.best.metrics}`",
            f"**Best params:** `{dict(result.best.candidate.params)}`",
            "",
        ]
    lines += [f"**Trials:** {len(result.history)}", f"**Provenance:** `{result.provenance}`"]
    return "\n".join(lines)
