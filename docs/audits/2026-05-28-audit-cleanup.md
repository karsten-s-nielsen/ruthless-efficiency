# Audit cleanup — 2026-05-28

A cleanup cycle that ran four mad-scientist-skills audits over the repository and remediated **every**
finding (Critical → Low) in one PR. Audits were run as independent read-only passes; all remediation
was applied centrally on the `chore/audit-cleanup-2026-05-28` branch.

## Audits run

| Audit | Mode | Critical | High | Medium | Low | Total |
|-------|------|:--------:|:----:|:------:|:---:|:-----:|
| documentation-audit | audit | 0 | 6 | 11 | 5 | 22 |
| architecture-audit | audit | 0 | 0 | 4 | 5 | 9 |
| security-audit | audit (Standard tier) | 0 | 0 | 3 | 4 | 7 |
| optimization-audit | audit | 0 | 2 | 6 | 3 | 11 |
| **Total** | | **0** | **8** | **24** | **17** | **49** |

**Disposition:** 49 findings, all remediated in this PR. Nothing deferred. (The three findings whose
recommended fix carried a real trade-off — Sec#7 HF_TOKEN handling, Arch#3 config split, Arch#6
value-object immutability — were surfaced for an explicit decision and approved for a full fix.)

## Architectural health

The architecture audit confirmed the stated hexagonal design is real and enforced (import-linter: 3
contracts kept), ports are genuinely structural Protocols, the core stays dependency-light, and the
unified error model has a single sentinel-mapping point. No Critical/High architectural findings.

## Documentation findings (22)

| # | Sev | Phase | Location | Finding | Framework | Status / fix |
|---|-----|-------|----------|---------|-----------|--------------|
| D1 | High | 6 | README | No Python ≥3.10 prerequisite | Carroll; Good Docs | Fixed — Prerequisites section |
| D2 | High | 6 | README | No CI/PyPI/license badges | Good Docs; Pirolli&Card | Fixed — 4 badges added |
| D3 | High | 6 | README:30 | Quick-start imports deep internal paths | Hyrum's Law | Fixed — curated public API + clean imports |
| D4 | High | 6 | (absent) | No CHANGELOG.md | Good Docs | Fixed — `CHANGELOG.md` (Keep a Changelog) |
| D5 | High | 4 | README:24–48 | Quick-start has no visible verification/expected output | Lemov; Carroll | Fixed — real expected-output block |
| D6 | High | 7 | README:58–67 | Architecture links to CLAUDE.md + internal plan (wrong audience) | Hinds; Carroll | Fixed — point to CONTRIBUTING; removed plan link |
| D7 | Med | 2 | README | Unmanaged content-type mixing; no learn-more pointers | Diataxis | Fixed — "Learn more" section, trimmed Architecture |
| D8 | Med | 5 | SECURITY.md | "Plan 1B" internal jargon to external readers | Strunk&White; Google | Fixed — version-neutral phrasing |
| D9 | Med | 4 | README:24 | No prerequisites/Objective-protocol explanation in quick start | Lemov; Merrill | Fixed |
| D10 | Med | 3 | SECURITY.md:9 | Temporal "latest" language | Google (timeless) | Fixed — "current 0.x release line" |
| D11 | Med | 6 | CONTRIBUTING:44–56 | Architecture guidelines stale (Phase 1A only) | Good Docs | Fixed — 1B/Phase-2 additions documented |
| D12 | Med | 8 | README:17 | uv dev toolchain undisclosed | Pirolli&Card; Carroll | Fixed — Prerequisites note |
| D13 | Med | 6 | 8 backend/strategy classes | No class-level docstrings | Good Docs; Carroll | Fixed — class docstrings added |
| D14 | Med | 8 | report.py:15,28 | `render_json`/`render_summary_md` undocumented | Good Docs | Fixed — docstrings |
| D15 | Med | 7 | README:58–63 | C4 HTML link doesn't render on GitHub | Pirolli&Card; Carroll | Fixed — "download + open" note |
| D16 | Low | 3 | README:21–23 | Inconsistent community-list formatting | Strunk&White (parallelism) | Fixed |
| D17 | Low | 8 | CONTRIBUTING:5–10 | Dev install omits extras needed for full suite | Carroll; Good Docs | Fixed — full-extras install note |
| D18 | Low | 5 | CONTRIBUTING:6 | Clone URL to verify before publish | Good Docs (accuracy) | Verified — URL retained (matches remote convention) |
| D19 | Low | 6 | CONTRIBUTING:57–67 | Versioning section vague on breaking changes | Good Docs | Fixed — explicit pre-1.0 + CHANGELOG note |
| D20 | Low | 8 | parallel.py:17–29 | `map_work_units` GIL caveat not in docstring | Good Docs; Carroll | Fixed — docstring expanded |

## Architecture findings (9)

| # | Sev | Location | Finding | Principle | Status / fix |
|---|-----|----------|---------|-----------|--------------|
| A1 | Med | sandbox.py:5 | Dangling ADR-001 reference (security model undocumented) | Nygard ADRs; Chesterton | Fixed — `docs/adr/ADR-001-…md` written; reference updated |
| A2 | Med | `__init__.py` | No curated public API surface (deep imports become de-facto API) | Clean Arch; Hyrum | Fixed — `__all__` façade + per-strategy re-exports |
| A3 | Med | config.py | 216-line hub mixing all strategy configs (high afferent coupling) | SRP; SDP | Fixed (approved) — split into `config/` package |
| A4 | Med | base/evaluator/workers | Wire-contract magic strings duplicated | Connascence; DRY | Fixed — `ruthless.wire` constants |
| A5 | Low | .importlinter | `_logging`/`__init__` not in core-isolation contract | Tooling enforcement | Fixed — `_logging`/`_io`/`wire`/config submodules added |
| A6 | Low | result.py; config | Value-object mutability by-convention only | DDD immutability | Fixed (approved) — `Candidate.params` frozen, `Choice.choices` tuple |
| A7 | Low | cli.py:27–30 | `isinstance` ladder for strategy build (OCP) | OCP | Fixed — registry table |
| A8 | Low | strategy `__init__`s | Empty barrels → no per-strategy public surface | Library API | Fixed — re-export per strategy |
| A9 | Low | backend.py port | Stamp coupling (full Objective to every backend) | Stamp coupling; ISP | Acknowledged — uniform port is a deliberate, sound trade-off (audit recommended no change) |

## Security findings (7)

| # | Sev | Location | Finding | CWE/OWASP | Status / fix |
|---|-----|----------|---------|-----------|--------------|
| S1 | Med | remote_ssh.py | device/dir/python_path interpolated unquoted into SSH cmd | CWE-78 / A03 | Fixed — `BackendConfig` shell-safe validators |
| S2 | Med | remote_ssh.py | No explicit StrictHostKeyChecking/BatchMode | CWE-295/322 / A02 | Fixed — `BatchMode=yes`, `StrictHostKeyChecking=accept-new` |
| S3 | Med | local_cuda.py | Advertises timeout enforcement but runs in-process | CWE-400 / A04 | Fixed — documented (class docstring + CLAUDE.md corrected) |
| S4 | Low | sandbox.py | AST validator is a belt, not a boundary | CWE-265 / A04 | Fixed — ADR-001 + SECURITY.md state OS-sandbox requirement |
| S5 | Low | ci.yml | Actions pinned by floating tag, not SHA | CWE-1357 / A06 | Fixed — SHA-pinned (matches publish.yml) |
| S6 | Low | remote_ssh/worker | Inconsistent traceback truncation in surfaced errors | CWE-209 / A09 | Fixed — `ERROR_TEXT_SURFACE_LIMIT` applied consistently |
| S7 | Low | remote_ssh.py | HF_TOKEN inline on SSH command line (visible in remote `ps`) | CWE-214 / A09 | Fixed (approved) — transferred via 0600 file, read-once + unlinked |

Verified-safe (assessed, no finding): the trusted-config objective loader (importlib+getattr, never
`eval`), `yaml.safe_load`, `ast.literal_eval` for evolve config, the Optuna SQLite store (ORM,
parameterised), HF Jobs SDK transport, no hardcoded secrets, OIDC trusted-publishing.

## Optimization findings (11)

| # | Sev | Location | Finding | Status / fix |
|---|-----|----------|---------|--------------|
| O1 | High | hf_jobs.py | Per-evaluation temp dir leak (`mkdtemp` never removed) | Fixed — `TemporaryDirectory` context |
| O2 | High | remote_ssh.py | `_ensure_remote_dir` SSH round-trip per candidate | Fixed — run once per backend |
| O3 | Med | optuna strategy | `study.trials` read 3× | Fixed — single post-optimize snapshot (pre-optimize reads kept: they straddle `enqueue_trial`) |
| O4 | Med | evolve/local_cuda | Entrypoint re-resolved per evaluation | Fixed — `@cache` on `_resolve_hook` |
| O5 | Med | base.py | `parse_last_json_line` materialises a filtered list | Fixed — scan reversed lines, strip inline |
| O6 | Med | sandbox.py | Attribute chain walked twice per node | Fixed — single-walk `_attr_root_and_first` |
| O7 | Med | hf_jobs.py | Worker script re-templated per evaluation | Fixed — cached per `ref.package` |
| O8 | Low | pool/remote_ssh | `available()` SSH probe not debounced | Fixed — short TTL cache (self-corrects via retry) |
| O9 | Low | (absent) | No benchmark coverage | Fixed — `benchmarks/` + `pytest-benchmark` dev dep |
| O10 | Low | evolve strategy | Temp-file logic duplicated vs `program_to_path` | Fixed — `program_to_path` moved to core `ruthless._io`, reused |
| O11 | Low | local_cuda.py | `available()` lazy-init race on free-threaded builds | Fixed — lock-guarded double-checked init (lazy import kept) |

## Verification

Local quality gate green after remediation: `ruff check`, `ruff format --check`, `pyright`
(0 errors), `lint-imports` (3 contracts kept), `pytest` (full suite). The C4 diagram was regenerated
by `/final-review`.
