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
    provenance rendered as one ``- key: value`` line per entry. A single-line dict repr grows past
    terminal width as keys are added and buries ``ruthless_git_state`` — precisely the field that must
    not be buried, since a commit with no tree state is false provenance. For the full machine-readable
    surface use :func:`render_json`, which is unchanged and serialises the dict faithfully."""
    lines = ["# Ruthless Efficiency — Run Summary", ""]
    if result.best:
        lines += [
            f"**Best metrics:** `{result.best.metrics}`",
            f"**Best params:** `{dict(result.best.candidate.params)}`",
            "",
        ]
    lines += [f"**Trials:** {len(result.history)}", "", "**Provenance:**"]
    lines += [f"- {k}: {v}" for k, v in result.provenance.items()] or ["- (none)"]
    return "\n".join(lines)
