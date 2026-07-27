# ADR-008: Development Tooling & CI/CD

## Status

Accepted

## Context

With the architecture decided (ADR-001 through ADR-007), Astrocyte needs a
concrete development toolchain and a CI/CD pipeline so the codebase is
regression-protected from the first line of code (issue #5). The repository
previously contained only governance docs and ADRs — no build configuration,
source layout, or automation. We must decide, once, how the project is built,
linted, type-checked, tested, packaged, and released, since every later phase
inherits these conventions.

Requirements:

- Python 3.12+ (ADR-002 / ADR-006) with fast, reproducible dependency
  management and a committed lockfile.
- A single, fast linter/formatter and a strict type checker.
- A test runner with coverage reported on pull requests.
- Linting/formatting for the React UI (ADR: Web UI is React 19 + Vite).
- Docker image builds validated on every PR (ADR-001) and published on release.
- Automated dependency updates and active vulnerability scanning.
- Conventions that scale to multiple subsystems (Ops/RAG/Backup agents, MCP
  servers) without restructuring.

## Decision

Adopt the following toolchain and pipeline.

### Python

- **uv** for environment management, dependency resolution, and a committed
  `uv.lock`. The project uses a `src/` layout with a single installable
  package, `astrocyte`, containing subpackages (`core`, `api`, `agents`, `mcp`,
  `cli`). Phase-specific heavy stacks (LlamaIndex, ChromaDB, FastMCP) are
  declared as optional-dependency groups and populated as each phase lands.
- **ruff** for both linting and formatting (replacing Black + flake8 + isort);
  line length 88, target `py312`.
- **mypy** in `strict` mode for static type checking.
- **pytest** + **pytest-cov** for tests and coverage; coverage is posted to PRs.
  A `--cov-fail-under` floor starts modest and is ratcheted toward 80% as real
  code lands.
- **Dynamic versioning from git tags** (hatchling + hatch-vcs): the latest `v*`
  tag is the single source of truth for the package version; no manual bumps.

### Frontend

- **Vite + React 19 + TypeScript**, linted with ESLint (flat config) and
  formatted with Prettier; tested with Vitest + Testing Library.

### Containers & release

- Multi-stage **Dockerfile** on `python:3.12-slim-bookworm` (Debian 12, ADR-001)
  built with uv; orchestrated via Docker Compose. Built (not pushed) on every PR.
- **GitHub Container Registry (GHCR)** for published images, tagged on `v*`
  releases via `docker/metadata-action`.

### Automation

- **GitHub Actions** `ci.yml` (lint, test+coverage, web checks, docker build,
  security scan) and `release.yml` (build/push image + GitHub Release).
- **pre-commit** mirroring the CI checks for fast local feedback.
- **Dependabot** for uv, npm, Docker, and GitHub Actions.
- **Active security scanning**: `pip-audit`, `npm audit`, and Trivy image scan
  in CI, complementing Dependabot's passive update PRs.
- A **Makefile** is the single source of truth for commands, called by
  CONTRIBUTING, pre-commit, and CI alike.

## Consequences

### Positive

- Fast, reproducible installs (uv) and one tool for lint+format (ruff).
- Strict typing and coverage gates catch regressions early.
- Tag-driven versioning removes a class of release mistakes.
- Conventions are consistent across all future subsystems.

### Negative

- Contributors must learn uv (vs. plain pip) and the flat ESLint config.
- The `--cov-fail-under` floor needs periodic ratcheting.
- A multi-job pipeline is more to maintain than a single script.

### Risks and Mitigations

- **Risk**: tool API/version churn. **Mitigation**: pinned versions + Dependabot.
- **Risk**: VCS versioning fails without tags. **Mitigation**: configured
  fallback version so source-only/Docker builds still succeed.

## Alternatives Considered

### Package manager: pip vs. Poetry vs. uv

- **pip + pyproject**: simplest, but no fast resolver or deterministic lockfile.
- **Poetry**: mature locking, but slower and heavier than uv.
- **uv** (chosen): fastest, deterministic lockfile, manages interpreters, and is
  the de-facto 2026 standard.

### Lint/format: Black + flake8 + isort vs. ruff

Ruff replaces all three with one fast tool and a Black-compatible formatter,
removing multi-tool config drift. (CONTRIBUTING previously referenced Black;
updated accordingly.)

### Coverage reporting: Codecov vs. in-repo action

Codecov is a third-party SaaS requiring a token/account. The in-repo
`py-cov-action/python-coverage-comment-action` posts coverage to PRs using only
`GITHUB_TOKEN`, keeping with the project's self-hosted ethos and avoiding an
external dependency.

## Related Decisions

- ADR-001: Base Platform (Debian 12 / Docker Compose)
- ADR-002: Agent Framework (Python 3.12 / LlamaIndex)
- ADR-006: API Framework (FastAPI)
- ADR-007: MCP-First Architecture (FastMCP)

## Notes

Deferred follow-ons are tracked as separate issues: applying branch protection
to `main` (done, #39) and CI hardening (test matrix + performance monitoring).
The coverage floor was ratcheted 50% → 80% with the v0.3.0 release (#41).
