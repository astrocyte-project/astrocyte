# CLAUDE.md — Claude Code context for Astrocyte

This file orients Claude Code (and any AI coding assistant) working in this
repo. AI-assisted development is *governed* by [`AI_STRATEGY.md`](AI_STRATEGY.md);
this file is the practical map — architecture, commands, and conventions.

## What Astrocyte is

Astrocyte is a **Self-Hosted AI Operating System** (AGPL-3.0): Docker-based apps
managed by AI agents, MCP-first, with a local LLM (Ollama), zero-trust
networking, and atomic backups. The long-form vision is in [`README.md`](README.md).

**The reference deployment is an RV.** Per [ADR-010](docs/adr/ADR-010-rv-reference-deployment.md)
the reference coach became the 1.0 reference deployment
mid-development, and the milestones were re-sequenced around it:

- **v0.3** (shipped, `v0.3.0`/`v0.3.1`) — the RV coach node: RV-C telemetry, Home
  Assistant integration, safe actuation, observability.
- **v0.4** (current) — Ops Agent & curated apps (the original "Phase 1").
- **v0.5** — RAG layer & unified search (original "Phase 2").
- **v1.0** — atomic backup, RV validation, polish (original "Phase 3").

Note the split between **milestones** (the *when* — release-versioned) and
**`phase-*` labels** (the *what* — thematic and unchanged since the pivot). Code,
issues, and ADRs after ADR-010 assume this deployment reality: nothing
coach-specific lives outside `deploy/coach/` and config; the core stays generic.

## Architecture map

Single installable package `astrocyte` (`src/` layout, [ADR-008](docs/adr/ADR-008-dev-tooling-cicd.md)):

| Path | Purpose |
|------|---------|
| `src/astrocyte/core/` | Shared primitives: `config.py` (`AstrocyteSettings`, `ASTROCYTE_` env prefix), `policy.py` (tiered actuation policy engine + two-phase approvals + JSONL audit, [ADR-014](docs/adr/ADR-014-actuation-safety-policy.md)), `connector.py` (`DataConnector` ABC), `llm/router.py` (`ModelRouter`, [ADR-013](docs/adr/ADR-013-multi-node-topology.md)) |
| `src/astrocyte/api/` | FastAPI app factory (`create_app()`): `/health` `/ready` `/metrics`, `/v1` router (approvals), conditional `/mcp/*` mounts + bearer middleware |
| `src/astrocyte/agents/` | **Runtime product agents** (LlamaIndex FunctionAgents), e.g. `coach.py`. Distinct from the dev personas in `.github/agents/` — see `AI_STRATEGY.md` |
| `src/astrocyte/mcp/` | `AstrocyteMCP` base class (FastMCP + policy enforcement), [ADR-007](docs/adr/ADR-007-mcp-architecture.md) |
| `src/astrocyte/ha/` | Home Assistant client + MCP server (`/mcp/ha`); HA is the hardware abstraction layer, [ADR-011](docs/adr/ADR-011-home-assistant-hardware-layer.md) |
| `src/astrocyte/rvc/` | RV-C CAN telemetry: typed decoder + `astro-rvc-bridge` (SocketCAN↔MQTT), [ADR-012](docs/adr/ADR-012-rvc-telemetry-architecture.md) |
| `src/astrocyte/cli/` | The `aios` CLI (argparse; talks to the API over HTTP) |
| `web/` | React 19 + Vite + TypeScript + Zustand SPA (Node 24) |
| `deploy/{coach,gpu,vps}/` | Per-node Compose stacks (the coach is the reference deployment) |
| `docs/adr/`, `docs/runbooks/` | Decision records and operator runbooks |

## Everyday commands

All commands live in the [`Makefile`](Makefile) so local and CI never drift
(full guide: [`docs/development.md`](docs/development.md)).

| Command | What it does |
|---------|--------------|
| `make install` | `uv sync --all-extras` + `npm ci` + pre-commit install |
| `make check` | All gates: lint + type-check + tests (run before every push) |
| `make lint` | ruff (Python) + ESLint/Prettier (web) |
| `make typecheck` | mypy **strict** + `tsc --noEmit` |
| `make test` | pytest (+coverage, 80% floor) + Vitest |
| `make fmt` | Auto-format Python and web |
| `make security` | `pip-audit` + `npm audit` |
| `make docker-build` | Build the API image via compose |

Run the API: `uv run uvicorn astrocyte.api.app:create_app --factory`.
Run the CLI: `uv run aios --version`.

## Conventions

- **Commits:** [Conventional Commits](CONTRIBUTING.md) — `type(scope): summary`
  (e.g. `feat(ops): …`, `fix(coach): …`). Scopes track components.
- **Branches:** one branch and one PR per issue — `feat/`, `fix/`, `docs/`,
  `chore/`, `refactor/`, `test/` prefixes.
- **PRs:** target `main`, conventional title, fill the PR template, link the
  tracking issue (`Closes #N`). `main` is protected: **squash-merge**, linear
  history, all required checks green. Required CI jobs: `python-lint`,
  `python-test` (80% coverage), `rvc-vcan`, `web-lint`, `docker-build`,
  `security`.
- **CHANGELOG:** update `[Unreleased]` in the **same PR** (Keep a Changelog).
  Release notes are extracted from it. **Never hand-edit a version** — versions
  derive from `v*` git tags (hatch-vcs).
- **Heavy dependencies** go in a per-phase optional-dependency **extra** in
  `pyproject.toml`, not the base install.
- **Multi-arch:** images build for `linux/amd64` **and** `linux/arm64` (the
  coach is a Pi 5) — don't break arm64.

## Decision records & project management

- **ADRs** (`docs/adr/`) are the decision-record format for significant
  architectural changes. Copy `docs/adr/template.md`, use the next free number
  (**check the directory** — currently the next free is ADR-015), and land the
  ADR **inside the implementation PR** that realizes it (repo precedent).
  *Amend* an accepted ADR (as ADR-012 was) rather than rewriting it.
- **Project management** ([ADR-009](docs/adr/ADR-009-project-management.md),
  [`docs/project-management.md`](docs/project-management.md)):
  [`.github/project.yml`](.github/project.yml) is the declarative source of truth
  for labels, issue types, milestones, and board fields, reconciled by
  `scripts/project-sync.sh`. Triage checklist: issue type + milestone (or
  `backlog`) + `component:*` + `phase-*` + parent Epic + board (#11). The
  labeler auto-applies `component:*` to PRs by path.

## AI governance

Development-time AI automation is governed by [`AI_STRATEGY.md`](AI_STRATEGY.md).
Dev personas live in [`.github/agents/`](.github/agents/) and slash-command
prompts in [`.github/prompts/`](.github/prompts/) (mirrored into `.claude/` by
symlink). Nothing in `.github/agents/` executes at product runtime — the runtime
agents are the Python ones in `src/astrocyte/agents/`.
