"""Single source of truth for the package version, in its own module so the PURE CORE can read it.

`ruthless/__init__.py` is the curated public API and therefore imports a strategy
(`RandomSearchStrategy`). Any core module doing `from ruthless import __version__` would thus
transitively import `ruthless.strategies`, breaking the `core-isolation` import-linter contract — caught
by `lint-imports` when `_provenance` first needed the version. Keeping the literal here lets both the
package root and core modules read it with no cycle and no contract violation.

Release note: this is the ONLY place the version is written. `pyproject.toml` declares
`dynamic = ["version"]` and hatchling reads it from here (`[tool.hatch.version] path`), and
`__init__.py` re-exports it — so bumping this line is the whole source change for a release."""

from __future__ import annotations

__version__ = "0.3.0"
