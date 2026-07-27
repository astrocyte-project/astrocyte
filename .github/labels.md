# Label taxonomy

Canonical reference for Astrocyte's issue/PR labels. The authoritative,
machine-readable source is [`.github/project.yml`](project.yml), reconciled by
[`scripts/project-sync.sh`](../scripts/project-sync.sh). See
[docs/project-management.md](../docs/project-management.md) for how labels fit the
wider PM model.

**Labels describe *where/what*; issue *types* (Epic/Feature/Task/Spike/Bug)
describe the *kind* of work.** Don't encode the kind of work as a label.

## `component:*` — area of the codebase

Applied to PRs **automatically** by [`.github/labeler.yml`](labeler.yml) based on
changed paths; set manually on issues during triage. All share the color
`#1d76db` so they read as a group.

| Label | Area / path |
|-------|-------------|
| `component:api` | `src/astrocyte/api/**` |
| `component:cli` | `src/astrocyte/cli/**` |
| `component:core` | `src/astrocyte/core/**` |
| `component:agent` | `src/astrocyte/agents/**` |
| `component:mcp` | `src/astrocyte/mcp/**` |
| `component:rvc` | `src/astrocyte/rvc/**` (RV-C CAN bridge & decoder) |
| `component:ha` | `src/astrocyte/ha/**` (Home Assistant integration) |
| `component:web` | `web/**` |
| `component:docker` | `docker/**`, `docker-compose*.yml`, `deploy/**` |
| `component:ci` | `.github/**`, `Makefile`, `.pre-commit-config.yaml` |
| `component:docs` | `docs/**`, `**/*.md` |
| `component:rag` | RAG layer & vector store (no path yet) |
| `component:backup` | Atomic backup & restore (no path yet) |
| `component:network` | Zero-trust networking (no path yet) |

## `phase-*` — roadmap phase (thematic)

`phase-0` Foundation & governance · `phase-1` Ops Agent & curated apps ·
`phase-2` RAG layer & unified search · `phase-3` Atomic backup & polish.

## Meta labels

| Label | Meaning |
|-------|---------|
| `architecture` | Core design & ADRs |
| `epic` | Tracks a multi-issue initiative via sub-issues |
| `backlog` | Not yet scheduled to a milestone |
| `needs-triage` | Awaiting triage (type/milestone/component) |
| `blocked` | Blocked by another issue or external factor |
| `rv-deployment` | RV reference deployment initiative (ADR-010) |

GitHub defaults (`good first issue`, `help wanted`, `documentation`,
`duplicate`, `invalid`, `question`, `wontfix`) are retained as-is.

## Dependabot labels (do not manage manually)

`dependencies`, `docker`, `github_actions`, `python:uv`, `javascript` are applied
by Dependabot to its update PRs. They are intentionally **not** `component:*`
labels and are left out of the declarative spec so the sync never touches them.
