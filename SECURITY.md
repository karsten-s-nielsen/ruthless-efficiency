# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.x     | :white_check_mark: |

The project is pre-1.0; security fixes are issued against the current `0.x` release line.

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

- The `[backends]` extra adds SSH / Hugging Face Jobs / Docker compute backends — these open network
  connections and dispatch remote work. SSH calls use key-based auth (`BatchMode=yes`,
  `StrictHostKeyChecking=accept-new`); secrets (e.g. `HF_TOKEN`) are passed to the node by a 0600
  file, not on the command line.
- The `[evolve]` extra adds an evolutionary strategy that executes candidate programs. LLM-generated
  code is screened by an AST allowlist (a defense-in-depth belt, not a sandbox boundary — see
  [docs/adr/ADR-001-ast-sandbox-security-model.md](docs/adr/ADR-001-ast-sandbox-security-model.md));
  run untrusted code only inside an OS-level sandbox (container/VM).

Treat objective functions and any remote-backend configuration as trusted code paths.
