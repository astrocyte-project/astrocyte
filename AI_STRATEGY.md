# AI Strategy — governance for AI-assisted development

This document governs how AI automation is used **in the development of
Astrocyte**. It is deliberately minimal and honest: it describes what is adopted
*now* and names what is deferred, rather than documenting aspirational machinery
that does not yet exist.

For the practical repo map (architecture, commands, conventions) see
[`CLAUDE.md`](CLAUDE.md).

## Scope

This document covers **development-time** AI automation only — the agents and
prompts used to build, review, and maintain this repository. It does **not**
govern the Astrocyte product's runtime AI features; those are product concerns
governed by their own ADRs.

## Dev personas vs. runtime agents

Astrocyte contains AI agents at two entirely separate levels. Keep them
straight:

| | Development personas | Runtime product agents |
|---|---|---|
| **Live in** | `.github/agents/` (+ `.github/prompts/`) | `src/astrocyte/agents/` (e.g. `coach.py`) |
| **Are** | Instructions for Claude Code / coding assistants | LlamaIndex FunctionAgents shipped in the product |
| **Governed by** | This document | Product ADRs + the [ADR-014](docs/adr/ADR-014-actuation-safety-policy.md) policy engine |
| **Run** | At development time, invoked by a human maintainer | At product runtime, on a deployed node |

**Nothing in `.github/agents/` executes at product runtime.** A persona file is a
prompt for a coding assistant; it is not imported, shipped, or run by the
Astrocyte application.

## Principles

- **Agent-as-code.** Useful, reusable agent behavior is committed to the repo
  and reviewed like any other change — no private, unversioned prompts driving
  the codebase.
- **Human-in-the-loop.** Every AI-authored change goes through the normal PR
  flow and is **reviewed by a human before squash-merge**. There is no
  auto-merge. Enforcement is the existing branch protection and required checks,
  not prose in this file.
- **Tool parity.** `.github/agents/` and `.github/prompts/` are the canonical
  source; `.claude/agents` and `.claude/commands` are symlinks into them, so
  Claude Code and GitHub-native tooling see the same definitions.

## The development loop

### Adopted now (interactive)

A maintainer drives the loop by hand:

1. **Pick up an issue** — `/pickup-issue <N>` invokes the **finisher** persona,
   which claims the issue, branches, posts an implementation-plan comment,
   implements, runs `make check`, updates the CHANGELOG, and opens a PR that
   `Closes #N`.
2. **Scan on demand** — the **scanner** persona runs the quality/security gates
   (`make lint`, `make typecheck`, `make test`, `make security`) read-only and
   reports findings. It never edits code and never opens issues.
3. **Human review** — the maintainer reviews and merges.

### Deferred (aspirational — not built)

The following are intentionally **not** adopted yet, because the repo has no
scheduled-automation infrastructure and a single maintainer, and pretending
otherwise would be theater:

- Scheduled / nightly autonomous scans.
- A "Manager" step that records findings as `ai-fix-requested` issues.
- Unattended fix pickup.

The `ai-fix-requested` label is therefore **not** created yet. This machinery,
along with runtime-facing personas and a skill library, is tracked as a
follow-up (see below).

## Index of personas and prompts

| File | Kind | Purpose |
|------|------|---------|
| [`.github/agents/finisher.md`](.github/agents/finisher.md) | Persona | Implement a GitHub issue end-to-end and open a PR |
| [`.github/agents/scanner.md`](.github/agents/scanner.md) | Persona | Read-only quality/security scan; reports, never fixes |
| [`.github/prompts/pickup-issue.md`](.github/prompts/pickup-issue.md) | Command `/pickup-issue` | Invoke the finisher on an issue |
| [`.github/prompts/triage-issue.md`](.github/prompts/triage-issue.md) | Command `/triage-issue` | Apply the ADR-009 triage checklist to an issue |
| [`.github/prompts/explain-strategy.md`](.github/prompts/explain-strategy.md) | Command `/explain-strategy` | Explain this governance model |

## Deferred roadmap

Runtime-facing personas (gated on their subsystems existing), a skill library,
and the automated scan→record→fix loop are deferred to
[**#127 — AI governance phase 2**](https://github.com/astrocyte-project/astrocyte/issues/127).
Each deferred persona must reference a real, shipped subsystem before it is
added.
