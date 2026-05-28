# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.x     | :white_check_mark: |

The project is pre-1.0; only the latest `0.x` release receives security fixes.

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public issue**
2. [Create a GitHub Security Advisory](https://github.com/karsten-s-nielsen/ruthless-efficiency/security/advisories/new)
3. Include: description, reproduction steps, and potential impact

We aim to acknowledge reports within 48 hours and provide a fix timeline within 7 days.

## Security Considerations

The pure hexagonal **core** (`ruthless/`, the default install) is a computation library:

- Config is parsed with `yaml.safe_load` — never `yaml.load`, so no arbitrary object construction.
- The CLI objective loader (`ruthless.cli.resolve_objective`) is **trusted-config-only**: it resolves
  `pkg.module:attr` via `importlib.import_module` + `getattr` (**never** `eval`/`exec`) and
  isinstance-checks the result against the `Objective` protocol. Only pass import-strings you control.
- The core does not open network connections, execute subprocesses, or deserialize untrusted data.

Optional extras broaden the surface and are **not** installed by default:

- `[backends]` (Plan 1B) adds SSH / Hugging Face Jobs / Docker compute backends — these open network
  connections and dispatch remote work.
- `[evolve]` (Plan 1B) adds an evolutionary strategy that executes candidate programs.

Treat objective functions and any remote-backend configuration as trusted code paths.
