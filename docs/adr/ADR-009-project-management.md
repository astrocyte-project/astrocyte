# ADR-009: GitHub-native, declarative project management

## Status

Accepted

## Context

By the end of Phase 0, Astrocyte had a ~34-issue backlog but no coherent
project-management (PM) system. It had ad-hoc, flat labels (`agent`, `mcp`, `ci`,
`ui`, `devx`), no milestones, no issue-type taxonomy, and issues that were not
triaged, not on a board, and not linked to any tracking Epic. Meanwhile the
`astrocyte-project` org had already enabled issue types (Epic/Feature/Task/Spike/Bug)
and created an "Astrocyte 1.0" Project board (#11) that nothing in the repo used.

The sibling `uio` project had solved the same problem with a **declarative**
GitHub-native framework, and adopting a comparable model keeps process consistent
across the org's repositories. We need to decide, once, how issues are typed,
labeled, scheduled, boarded, and kept consistent — and how much of that is
codified in the repo versus configured by hand in the GitHub UI.

## Decision

Adopt a **declarative, GitHub-native** PM framework, codified in the repo and
reconciled by automation rather than maintained by hand.

- **Single source of truth**: [`.github/project.yml`](../../.github/project.yml)
  declares labels, the issue-type taxonomy, release milestones, and the Project
  board's custom fields.
- **Reconciler**: [`scripts/project-sync.sh`](../../scripts/project-sync.sh)
  applies the spec **non-destructively** (never deletes entries absent from it),
  runnable locally or via the [`project-sync`](../../.github/workflows/project-sync.yml)
  workflow. Org-level writes require a maintainer PAT (`PROJECT_ADMIN_TOKEN`);
  the script degrades gracefully when it is absent.
- **Issue types**: Epic/Feature/Task/Spike/Bug, surfaced through YAML **issue-form**
  templates that pin the type.
- **Labels**: migrate component labels to a path-routed **`component:*`** scheme,
  auto-applied to PRs by [`.github/labeler.yml`](../../.github/labeler.yml); phase
  labels remain the thematic axis; meta labels cover workflow state.
- **Milestones**: **release-versioned** (v0.2 → v1.0), mapping onto roadmap
  phases; milestones answer *when*, phase labels answer *what*.
- **Board**: every issue is added to Project #11, with `Effort`/`Start Date`/
  `Target Date`/`Order` custom fields.
- **Backlog**: the whole existing backlog is triaged (type + milestone +
  component labels + board) as part of adoption — not merely documented.
- **Decision records**: ADRs remain Astrocyte's decision-record format; a public
  RFC process is deferred to post-1.0.

The full model is documented in
[docs/project-management.md](../project-management.md).

## Consequences

### Positive

- One reviewable, versioned source of truth for PM configuration; changes go
  through PR review like code.
- Consistent, low-effort triage; PRs self-label by component.
- Roadmap phases map cleanly onto release milestones and a live board.
- Parity with the org's other repositories.

### Negative

- Org-level objects (issue types, Project fields) need a maintainer PAT the
  default token can't replace.
- The reconciler and labeler are additional automation to maintain.
- Contributors must learn the type/label/milestone conventions.

### Risks and Mitigations

- **Risk**: label renames orphan associations. **Mitigation**: rename in place
  via `from:` aliases rather than delete+create.
- **Risk**: an unattended sync makes unwanted changes. **Mitigation**:
  non-destructive reconciler; PAT-gated; runs only on spec changes.

## Alternatives Considered

- **Manual GitHub-UI management**: no drift protection, no review trail,
  error-prone at scale. Rejected.
- **Third-party PM tool (Jira/Linear)**: splits the source of truth away from the
  code and adds a SaaS dependency, against the project's self-hosted ethos.
- **Phase-based milestones**: couples *when* to *what*; release-versioned
  milestones with phase labels keep the two axes independent.

## Related Decisions

- ADR-008: Development Tooling & CI/CD (labeler/project-sync join the existing
  Actions pipeline; `.pre-commit-config.yaml` validates the new YAML).

## Notes

Deferred follow-ons are tracked under the "Adopt GitHub-native PM framework"
governance Epic: adding `PROJECT_ADMIN_TOKEN`, board auto-add + saved views, DCO
sign-off, REUSE/SPDX headers, and a formal RFC process (post-1.0).
